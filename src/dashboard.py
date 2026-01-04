import argparse
import hashlib
import hmac
import io
import os
import threading
import uuid
import time
from datetime import datetime, timezone

from flask import (
    Flask,
    redirect,
    render_template_string,
    render_template,
    request,
    url_for,
    send_file,
    abort,
    jsonify,
    Response,
    session,
)

# Security imports
try:
    from flask_wtf.csrf import CSRFProtect
    CSRF_AVAILABLE = True
except ImportError:
    CSRF_AVAILABLE = False

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False

import create_pdf
import scryfall_enrich

try:
    # Optional DB helper for UA counts
    from db.bulk_index import count_unique_artworks as db_count_unique_artworks  # type: ignore
except Exception:  # pragma: no cover

    def db_count_unique_artworks(*args, **kwargs) -> int:  # type: ignore
        return 0


app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

# CSRF Protection
if CSRF_AVAILABLE:
    csrf = CSRFProtect(app)
else:
    csrf = None

# Rate Limiting
if LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
else:
    limiter = None

# Admin authentication
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# Login attempt tracking for rate limiting
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_ATTEMPT_LOCK = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300  # 5 minutes


def _check_login_rate_limit(ip: str) -> tuple[bool, int]:
    """Check if IP is rate limited. Returns (is_allowed, seconds_remaining)."""
    now = time.time()
    with LOGIN_ATTEMPT_LOCK:
        if ip not in LOGIN_ATTEMPTS:
            return True, 0
        # Clean old attempts
        LOGIN_ATTEMPTS[ip] = [t for t in LOGIN_ATTEMPTS[ip] if now - t < LOGIN_LOCKOUT_SECONDS]
        if len(LOGIN_ATTEMPTS[ip]) >= MAX_LOGIN_ATTEMPTS:
            oldest = min(LOGIN_ATTEMPTS[ip])
            remaining = int(LOGIN_LOCKOUT_SECONDS - (now - oldest))
            return False, max(0, remaining)
        return True, 0


def _record_login_attempt(ip: str) -> None:
    """Record a failed login attempt."""
    with LOGIN_ATTEMPT_LOCK:
        if ip not in LOGIN_ATTEMPTS:
            LOGIN_ATTEMPTS[ip] = []
        LOGIN_ATTEMPTS[ip].append(time.time())


def _clear_login_attempts(ip: str) -> None:
    """Clear login attempts after successful login."""
    with LOGIN_ATTEMPT_LOCK:
        LOGIN_ATTEMPTS.pop(ip, None)


def _secure_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())

TASKS: list[dict] = []
TASK_LOCK = threading.Lock()


def admin_required(f):
    """Decorator to require admin authentication."""
    from functools import wraps
    from flask import session

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return (
                render_template_string(
                    "<h1>Admin Disabled</h1><p>Set ADMIN_PASSWORD environment variable to enable admin features.</p>"
                    "<p><a href='/'>Back to Dashboard</a></p>"
                ),
                403,
            )
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def _resolve_oracle_ids(name: str, set_code: str | None = None) -> list[str]:
    oracle_ids: list[str] = []
    name = (name or "").strip()
    if not name:
        return oracle_ids

    set_norm = set_code.lower() if set_code else None

    if create_pdf._db_index_available():
        try:
            rows = create_pdf.db_query_cards(
                name_filter=name,
                set_filter=set_norm,
                limit=None,
            )
            for row in rows:
                oid = row.get("oracle_id")
                if oid and oid not in oracle_ids:
                    oracle_ids.append(oid)
        except Exception:
            oracle_ids = []

    if oracle_ids:
        return oracle_ids

    index = create_pdf._load_bulk_index()
    entries = index.get("entries", {}) if isinstance(index, dict) else {}
    if not entries:
        return oracle_ids

    slug = create_pdf._slugify(name)
    for entry in entries.values():
        if slug and slug not in (entry.get("name_slug") or ""):
            continue
        if set_norm and (entry.get("set") or "").lower() != set_norm:
            continue
        oid = entry.get("oracle_id")
        if oid and oid not in oracle_ids:
            oracle_ids.append(oid)
    return oracle_ids


def _token_pack_task(
    buffer: io.StringIO, manifest_bytes: bytes, pack_name: str | None
) -> None:
    tmp_dir = os.path.join(
        create_pdf.project_root_directory, "archived", "token-pack-cache"
    )
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"manifest_{uuid.uuid4().hex}.json")
    with open(tmp_path, "wb") as f:
        f.write(manifest_bytes)

    # Build the pack
    create_pdf._build_token_pack(tmp_path, pack_name)

    # Attempt to locate the resulting zip for convenience
    pack_root = os.path.join(
        create_pdf.project_root_directory,
        "magic-the-gathering",
        "shared",
        "token-packs",
    )
    candidates = []
    label = pack_name or os.path.splitext(os.path.basename(tmp_path))[0]
    for entry in os.scandir(pack_root):
        if not entry.is_file():
            continue
        if not entry.name.lower().endswith(".zip"):
            continue
        if entry.name.startswith(label + "_"):
            candidates.append(entry)
    archive_path = None
    if candidates:
        candidates.sort(key=lambda e: e.stat().st_mtime, reverse=True)
        archive_path = candidates[0].path

    if archive_path:
        buffer.write(f"Token pack archive: {archive_path}\n")
        buffer.write(f"Download: {url_for('download', path=archive_path)}\n")
    create_pdf._notify(
        "Token Pack Ready", f"Pack '{label}' built via dashboard.", event="token_pack"
    )


def _land_coverage_task(
    buffer: io.StringIO, kind: str, set_code: str | None, out_dir: str | None
) -> None:
    import importlib.util

    cov_path = os.path.join(os.path.dirname(__file__), "coverage.py")
    spec = importlib.util.spec_from_file_location("pm_coverage", cov_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load coverage tool module.")
    assert spec is not None and spec.loader is not None
    pm_cov = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(pm_cov)  # type: ignore[attr-defined]

    rows, summary = pm_cov.compute_coverage(kind, set_code)
    # Write outputs using coverage helper (land-coverage category)
    csv_path, json_path = pm_cov._write_common_outputs(
        rows, summary, out_dir, "land-coverage"
    )
    buffer.write(
        f"Coverage: {summary.get('covered', 0)}/{summary.get('total', 0)} ({summary.get('coverage_pct', 0.0):.1f}%) kind={summary.get('kind')} set={summary.get('set_filter') or 'ALL'}\n"
    )
    buffer.write(f"CSV: {csv_path}\nJSON: {json_path}\n")
    buffer.write(f"Download JSON: {url_for('download', path=str(json_path))}\n")
    create_pdf._notify(
        "Land Coverage Ready",
        f"Coverage computed for kind={kind} set={set_code or 'ALL'}.",
        event="land_coverage",
    )


def _rules_delta_task(buffer: io.StringIO) -> None:
    import importlib.util

    rd_path = os.path.join(os.path.dirname(__file__), "rules_delta.py")
    spec = importlib.util.spec_from_file_location("pm_rules_delta", rd_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load rules delta module.")
    pm_rd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_rd)  # type: ignore[attr-defined]

    result = pm_rd.generate_reports()
    out_dir = result.get("out_dir")
    csv_path = result.get("csv")
    json_path = result.get("json")
    buffer.write("Rules delta report complete.\n")
    if out_dir:
        buffer.write(f"Output directory: {out_dir}\n")
    if csv_path:
        buffer.write(f"CSV: {csv_path}\n")
        buffer.write(f"Download CSV: {url_for('download', path=str(csv_path))}\n")
    if json_path:
        buffer.write(f"JSON: {json_path}\n")
        buffer.write(f"Download JSON: {url_for('download', path=str(json_path))}\n")
    create_pdf._notify(
        "Rules Delta Ready",
        "Oracle text delta report generated.",
        event="rules_delta",
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _append_task(entry: dict) -> None:
    with TASK_LOCK:
        TASKS.insert(0, entry)
        if len(TASKS) > 25:
            TASKS.pop()


def run_task(name: str, func, *args, **kwargs) -> None:
    task_id = str(uuid.uuid4())
    task_entry = {
        "id": task_id,
        "name": name,
        "status": "running",
        "started": _timestamp(),
        "log": "",
    }
    _append_task(task_entry)

    def worker():
        buffer = io.StringIO()
        try:
            func(buffer, *args, **kwargs)
            task_entry["status"] = "completed"
        except Exception as exc:  # pragma: no cover
            task_entry["status"] = "failed"
            task_entry["error"] = str(exc)
        finally:
            task_entry["finished"] = _timestamp()
            task_entry["log"] = buffer.getvalue()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def _fetch_basics_task(buffer: io.StringIO) -> None:
    saved, skipped, total, skipped_details = (
        create_pdf._fetch_all_basic_lands_from_scryfall()
    )
    warnings = create_pdf._ensure_basic_land_symlinks()
    buffer.write(
        f"Fetched {total} basic land entries. Downloaded {saved}, skipped {skipped}.\n"
    )
    if skipped_details:
        buffer.write("Skipped entries:\n")
        for detail in skipped_details[:20]:
            buffer.write(f"  - {detail}\n")
        if len(skipped_details) > 20:
            buffer.write(f"  ... {len(skipped_details) - 20} more skipped entries\n")
    if warnings:
        buffer.write("Warnings:\n")
        for warning in warnings:
            buffer.write(f"  - {warning}\n")
    create_pdf._notify(
        "Basic Land Sync Complete",
        f"Saved {saved}, skipped {skipped} entries.",
        event="fetch_basics",
    )


def _fetch_non_basics_task(buffer: io.StringIO) -> None:
    saved, skipped, total, skipped_details = create_pdf._fetch_all_non_basic_lands()
    buffer.write(
        f"Fetched {total} non-basic land entries. Downloaded {saved}, skipped {skipped}.\n"
    )
    if skipped_details:
        buffer.write("Skipped entries:\n")
        for detail in skipped_details[:20]:
            buffer.write(f"  - {detail}\n")
        if len(skipped_details) > 20:
            buffer.write(f"  ... {len(skipped_details) - 20} more skipped entries\n")
    create_pdf._notify(
        "Non-Basic Land Sync Complete",
        f"Saved {saved}, skipped {skipped} entries.",
        event="fetch_nonbasics",
    )


def _deck_report_task(
    buffer: io.StringIO, deck_text: str, deck_name: str | None, profile: str | None
) -> None:
    temp_dir = os.path.join(create_pdf.project_root_directory, "archived", "deck-cache")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"dashboard_{uuid.uuid4().hex}.txt")
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(deck_text)

    output_dir = os.path.join(
        create_pdf.DECK_REPORT_ROOT
        if not profile
        else os.path.join(create_pdf._profile_root(profile), "deck-reports")
    )
    os.makedirs(output_dir, exist_ok=True)

    create_pdf._process_deck_list(temp_path, deck_name, None, profile)
    buffer.write(f"Deck report generated (source: {temp_path}).\n")
    create_pdf._notify(
        "Deck Report Ready",
        f"Deck '{deck_name or 'Unnamed'}' processed via dashboard.",
        event="deck_report",
    )


def _render_tokens(
    name: str | None = None,
    subtype: str | None = None,
    set_code: str | None = None,
    colors: str | None = None,
):
    entries = create_pdf._bulk_iter_tokens(
        name_filter=name,
        subtype_filter=subtype,
        set_filter=set_code,
        colors_filter=colors,
    )
    results = []
    for entry in entries[:50]:
        local_path, has_local = create_pdf._token_entry_local_path(entry)
        results.append(
            {
                "name": entry.get("name"),
                "set": (entry.get("set") or "").upper(),
                "collector": entry.get("collector_number"),
                "subtype": entry.get("token_subtype") or "—",
                "keywords": entry.get("oracle_keywords") or [],
                "oracle_text": entry.get("oracle_text"),
                "image_url": entry.get("image_url"),
                "local_path": str(local_path),
                "has_local": has_local,
            }
        )
    return results


def _search_tokens_by_keyword(
    keyword: str, set_code: str | None, limit: int
) -> list[dict]:
    entries = create_pdf._bulk_iter_tokens(set_filter=set_code or None)
    keyword_norm = (keyword or "").lower().strip()
    results: list[dict] = []
    for entry in entries:
        kws = [kw.lower() for kw in entry.get("oracle_keywords") or []]
        oracle_text = (entry.get("oracle_text") or "").lower()
        if keyword_norm in kws or keyword_norm in oracle_text:
            local_path, has_local = create_pdf._token_entry_local_path(entry)
            results.append(
                {
                    "name": entry.get("name"),
                    "set": (entry.get("set") or "").upper(),
                    "collector": entry.get("collector_number"),
                    "subtype": entry.get("token_subtype") or "—",
                    "keywords": entry.get("oracle_keywords") or [],
                    "oracle_text": entry.get("oracle_text"),
                    "image_url": entry.get("image_url"),
                    "local_path": str(local_path),
                    "has_local": has_local,
                }
            )
            if len(results) >= max(0, limit or 0) and limit and limit > 0:
                break
    return results


def _search_cards_by_oracle(
    query: str, set_code: str | None, limit: int, include_tokens: bool
) -> list[dict]:
    # Prefer DB FTS when available, with graceful fallback
    results: list[dict] = []
    try:
        if create_pdf._db_index_available():
            set_norm = set_code.lower() if set_code else None
            rows = create_pdf.db_query_oracle_fts(
                query=query,
                set_filter=set_norm,
                include_tokens=include_tokens,
                limit=limit,
            )
            if not rows:
                rows = create_pdf.db_query_oracle_text(
                    query=(query or "").lower(),
                    set_filter=set_norm,
                    include_tokens=include_tokens,
                    limit=limit,
                )
            for entry in rows:
                rec = {
                    "name": entry.get("name"),
                    "set": (entry.get("set") or "").upper(),
                    "collector": entry.get("collector_number"),
                    "type_line": entry.get("type_line"),
                    "keywords": entry.get("oracle_keywords")
                    or entry.get("keywords")
                    or [],
                    "oracle_text": entry.get("oracle_text"),
                    "image_url": entry.get("image_url") or "n/a",
                    "oracle_id": entry.get("oracle_id"),
                }
                if entry.get("is_token"):
                    local_path, has_local = create_pdf._token_entry_local_path(entry)
                    rec["local"] = "yes" if has_local else "no"
                    rec["local_path"] = str(local_path)
                results.append(rec)
            if results:
                return (
                    results[: max(0, limit or 0)] if (limit and limit > 0) else results
                )
    except Exception:
        # Fall through to in-memory scan
        pass

    # Fallback: in-memory scan of bulk index
    index = create_pdf._load_bulk_index()
    entries = index.get("entries", {})
    q = (query or "").lower().strip()
    set_norm = set_code.lower() if set_code else None
    for entry in entries.values():
        if not include_tokens and entry.get("is_token"):
            continue
        if set_norm and entry.get("set") != set_norm:
            continue
        oracle_text = (entry.get("oracle_text") or "").lower()
        type_line = (entry.get("type_line") or "").lower()
        if q in oracle_text or q in type_line:
            rec = {
                "name": entry.get("name"),
                "set": (entry.get("set") or "").upper(),
                "collector": entry.get("collector_number"),
                "type_line": entry.get("type_line"),
                "keywords": entry.get("oracle_keywords") or [],
                "oracle_text": entry.get("oracle_text"),
                "image_url": entry.get("image_url") or "n/a",
                "oracle_id": entry.get("oracle_id"),
            }
            if entry.get("is_token"):
                local_path, has_local = create_pdf._token_entry_local_path(entry)
                rec["local"] = "yes" if has_local else "no"
                rec["local_path"] = str(local_path)
            results.append(rec)
            if len(results) >= max(0, limit or 0) and limit and limit > 0:
                break
    return results


INDEX_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Proxy Machine Dashboard</title>
<style>
  body { font-family: Arial, sans-serif; margin: 20px; }
  h1 { color: #333; }
  h2 { color: #666; border-bottom: 2px solid #ddd; padding-bottom: 5px; }
  h3 { color: #888; }
  .section { margin-bottom: 30px; }
  button { padding: 8px 12px; margin: 5px; cursor: pointer; }
  input[type="text"], select { padding: 5px; margin: 5px; }
  .deck-item { padding: 10px; margin: 5px 0; background: #f5f5f5; border-radius: 4px; }
  .deck-item:hover { background: #e8e8e8; }
  #deckList { margin-top: 10px; }
  .success { color: green; }
  .error { color: red; }
  #message { margin: 10px 0; padding: 10px; display: none; }
  #message.success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; display: block; }
  #message.error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; display: block; }
</style>
<script>
function loadProfiles() {
  fetch('/api/profiles')
    .then(r => r.json())
    .then(data => {
      const select = document.getElementById('profileSelect');
      select.innerHTML = '<option value="">Select profile...</option>';
      data.profiles.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.name;
        select.appendChild(opt);
      });
    });
}

function loadDecks() {
  const profile = document.getElementById('profileSelect').value;
  if (!profile) {
    document.getElementById('deckList').innerHTML = '';
    return;
  }

  fetch(`/api/profiles/${profile}/decks`)
    .then(r => r.json())
    .then(data => {
      const list = document.getElementById('deckList');
      if (data.decks.length === 0) {
        list.innerHTML = '<p>No deck subfolders found. Create one below!</p>';
      } else {
        list.innerHTML = '<h4>Available Decks:</h4>';
        data.decks.forEach(deck => {
          list.innerHTML += `<div class="deck-item">${deck.name} <small>(${deck.card_count} cards)</small></div>`;
        });
      }

      // Populate deck select for PDF generation
      const deckSelect = document.getElementById('deckSelect');
      deckSelect.innerHTML = '<option value="">All cards (no deck filter)</option>';
      data.decks.forEach(deck => {
        const opt = document.createElement('option');
        opt.value = deck.name;
        opt.textContent = `${deck.name} (${deck.card_count} cards)`;
        deckSelect.appendChild(opt);
      });

      // Populate deck select for file upload
      const uploadDeckSelect = document.getElementById('uploadDeckSelect');
      uploadDeckSelect.innerHTML = '<option value="">Root folder (no deck)</option>';
      data.decks.forEach(deck => {
        const opt = document.createElement('option');
        opt.value = deck.name;
        opt.textContent = deck.name;
        uploadDeckSelect.appendChild(opt);
      });
    });
}

function createDeck() {
  const profile = document.getElementById('profileSelect').value;
  const deckName = document.getElementById('newDeckName').value.trim();

  if (!profile) {
    showMessage('Please select a profile first', 'error');
    return;
  }

  if (!deckName) {
    showMessage('Please enter a deck name', 'error');
    return;
  }

  fetch(`/api/profiles/${profile}/decks`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({deck_name: deckName})
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showMessage(data.error, 'error');
    } else {
      showMessage(`Deck "${deckName}" created successfully!`, 'success');
      document.getElementById('newDeckName').value = '';
      loadDecks();
    }
  })
  .catch(e => showMessage('Error creating deck: ' + e, 'error'));
}

function generatePDF() {
  const profile = document.getElementById('profileSelect').value;
  const deck = document.getElementById('deckSelect').value;
  const pdfName = document.getElementById('pdfName').value.trim();

  // Advanced options
  const cardSize = document.getElementById('cardSize').value;
  const paperSize = document.getElementById('paperSize').value;
  const crop = parseFloat(document.getElementById('crop').value);
  const ppi = parseInt(document.getElementById('ppi').value);
  const quality = parseInt(document.getElementById('quality').value);
  const onlyFronts = document.getElementById('onlyFronts').checked;

  if (!profile) {
    showMessage('Please select a profile first', 'error');
    return;
  }

  const payload = {
    deck: deck || null,
    pdf_name: pdfName || null,
    card_size: cardSize,
    paper_size: paperSize,
    crop: crop,
    ppi: ppi,
    quality: quality,
    only_fronts: onlyFronts
  };

  fetch(`/api/profiles/${profile}/pdf`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showMessage(data.error, 'error');
    } else {
      showMessage('PDF generation started! It will be ready for download when complete.', 'success');

      // Show download button after a delay (assume 10 seconds for generation)
      setTimeout(() => {
        const downloadBtn = document.getElementById('downloadPdfBtn');
        if (downloadBtn) {
          downloadBtn.style.display = 'inline-block';
        }
      }, 10000);
    }
  })
  .catch(e => showMessage('Error starting PDF generation: ' + e, 'error'));
}

function downloadLatestPDF() {
  const profile = document.getElementById('profileSelect').value;
  if (!profile) {
    showMessage('Please select a profile first', 'error');
    return;
  }

  window.location.href = `/api/profiles/${profile}/download-latest-pdf`;
}

function showMessage(msg, type) {
  const msgDiv = document.getElementById('message');
  msgDiv.textContent = msg;
  msgDiv.className = type;
  setTimeout(() => {msgDiv.style.display = 'none';}, 5000);
}

function uploadImages() {
  const profile = document.getElementById('profileSelect').value;
  const deck = document.getElementById('uploadDeckSelect').value;
  const face = document.getElementById('uploadFaceSelect').value;
  const files = document.getElementById('uploadFiles').files;

  if (!profile) {
    showMessage('Please select a profile first', 'error');
    return;
  }

  if (files.length === 0) {
    showMessage('Please select files to upload', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('deck', deck);
  formData.append('face', face);
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }

  const progressDiv = document.getElementById('uploadProgress');
  progressDiv.style.display = 'block';
  progressDiv.innerHTML = `Uploading ${files.length} file(s)...`;

  fetch(`/api/profiles/${profile}/upload`, {
    method: 'POST',
    body: formData
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showMessage(data.error, 'error');
      progressDiv.innerHTML = `Error: ${data.error}`;
    } else {
      showMessage(`Successfully uploaded ${data.uploaded} file(s)!`, 'success');
      progressDiv.innerHTML = `Uploaded ${data.uploaded} file(s) to ${data.destination}`;
      document.getElementById('uploadFiles').value = '';
      loadDecks();  // Refresh deck card counts
    }
  })
  .catch(e => {
    showMessage('Error uploading files: ' + e, 'error');
    progressDiv.innerHTML = 'Upload failed';
  });
}

function importDeckList() {
  const profile = document.getElementById('profileSelect').value;
  const deckList = document.getElementById('deckListInput').value.trim();
  const deckName = document.getElementById('deckListName').value.trim();

  if (!profile) {
    showMessage('Please select a profile first', 'error');
    return;
  }

  if (!deckList) {
    showMessage('Please enter a deck list or URL', 'error');
    return;
  }

  const progressDiv = document.getElementById('deckListProgress');
  progressDiv.style.display = 'block';
  progressDiv.innerHTML = 'Analyzing deck list...';

  fetch(`/api/profiles/${profile}/import-deck`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      deck_list: deckList,
      deck_name: deckName
    })
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showMessage(data.error, 'error');
      progressDiv.innerHTML = `Error: ${data.error}`;
    } else {
      showMessage('Deck analysis started! Check results below.', 'success');
      progressDiv.innerHTML = `Processing deck: ${data.total_cards} unique cards found. Fetching images...`;
      setTimeout(() => window.location.reload(), 3000);
    }
  })
  .catch(e => {
    showMessage('Error importing deck: ' + e, 'error');
    progressDiv.innerHTML = 'Import failed';
  });
}

window.onload = loadProfiles;
</script>
</head>
<body>
<h1>Proxy Machine Dashboard</h1>

<div id="message"></div>

<div class="section">
<h2>Profile & PDF Generation</h2>

<h3>1. Select Profile</h3>
<select id="profileSelect" onchange="loadDecks()">
  <option value="">Loading profiles...</option>
</select>

<div id="deckList"></div>

<h3>2. Create New Deck (Optional)</h3>
<input type="text" id="newDeckName" placeholder="Enter deck name (e.g., commander)">
<button onclick="createDeck()">Create Deck Subfolder</button>
<br><small>Creates front/, back/, and double_sided/ subfolders for organizing cards</small>

<h3>3. Upload Card Images</h3>
<div style="margin: 10px 0; padding: 10px; background: #f9f9f9; border-radius: 4px;">
  <label>Select Deck: </label>
  <select id="uploadDeckSelect">
    <option value="">Root folder (no deck)</option>
  </select>
  <br>

  <label>Card Face: </label>
  <select id="uploadFaceSelect">
    <option value="front">Front</option>
    <option value="back">Back</option>
    <option value="double_sided">Double-Sided</option>
  </select>
  <br>

  <label>Files: </label>
  <input type="file" id="uploadFiles" multiple accept="image/*">
  <br>

  <button onclick="uploadImages()">Upload Images</button>
  <div id="uploadProgress" style="display: none; margin-top: 10px;"></div>
  <br><small>Upload PNG/JPG images to your profile's card folders</small>
</div>

<h3>4. Import Deck List</h3>
<div style="margin: 10px 0; padding: 10px; background: #f9f9f9; border-radius: 4px;">
  <label>Deck List or URL: </label><br>
  <textarea id="deckListInput" rows="8" cols="60" placeholder="Paste Moxfield/Archidekt URL or deck list:
1x Lightning Bolt
4x Counterspell
..."></textarea>
  <br>

  <label>Deck Name: </label>
  <input type="text" id="deckListName" placeholder="my-imported-deck">
  <br>

  <button onclick="importDeckList()">Analyze & Fetch Cards</button>
  <div id="deckListProgress" style="display: none; margin-top: 10px;"></div>
  <br><small>Analyzes deck and helps fetch missing cards from Scryfall</small>
</div>

<h3>5. Generate PDF</h3>
<label>Deck: </label>
<select id="deckSelect">
  <option value="">All cards (no deck filter)</option>
</select>
<br>

<label>PDF Name (optional): </label>
<input type="text" id="pdfName" placeholder="my-deck">
<br>

<details>
  <summary><strong>Advanced Options</strong> (click to expand)</summary>
  <div style="margin-left: 20px; margin-top: 10px;">
    <label>Card Size: </label>
    <select id="cardSize">
      <option value="standard" selected>Standard (63×88mm - MTG, Pokemon)</option>
      <option value="japanese">Japanese (59×86mm - Yu-Gi-Oh!)</option>
      <option value="poker">Poker (63.5×88.9mm)</option>
      <option value="bridge">Bridge (56×87mm)</option>
      <option value="tarot">Tarot (70×120mm)</option>
      <option value="domino">Domino (44×88mm)</option>
    </select>
    <br>

    <label>Paper Size: </label>
    <select id="paperSize">
      <option value="letter" selected>Letter (8.5×11")</option>
      <option value="a4">A4 (210×297mm)</option>
      <option value="tabloid">Tabloid (11×17")</option>
      <option value="a3">A3 (297×420mm)</option>
    </select>
    <br>

    <label>Crop: </label>
    <input type="number" id="crop" value="3" min="0" max="10" step="0.5" style="width: 60px;">
    <label> mm</label>
    <br>

    <label>PPI: </label>
    <select id="ppi">
      <option value="300">300 (Draft)</option>
      <option value="600" selected>600 (Standard)</option>
      <option value="800">800 (High)</option>
      <option value="1200">1200 (Premium)</option>
    </select>
    <br>

    <label>Quality: </label>
    <select id="quality">
      <option value="85">85 (Good)</option>
      <option value="95">95 (Better)</option>
      <option value="100" selected>100 (Best)</option>
    </select>
    <br>

    <label>
      <input type="checkbox" id="onlyFronts">
      Only fronts (no backs)
    </label>
  </div>
</details>
<br>

<button onclick="generatePDF()">Generate PDF</button>
<button id="downloadPdfBtn" onclick="downloadLatestPDF()" style="display: none; margin-left: 10px; background: #28a745; color: white;">Download Latest PDF</button>
</div>

<hr>

<div class="section">
<h2>Quick Actions</h2>
<form method="post" action="{{ url_for('run_action') }}">
  <button name="action" value="fetch_basics">Fetch Basic Lands</button>
  <button name="action" value="fetch_nonbasics">Fetch Non-Basic Lands</button>
  <button name="action" value="rules_delta">Rules Delta</button>
</form>
</div>

<h3>Set Info</h3>
<form method="get" action="{{ url_for('set_view') }}">
  Set code: <input type="text" name="code" value="{{ request.args.get('code','') }}">
  <button type="submit">Show</button>
  <small>e.g., mh3</small>
</form>

<h3>Build Token Pack</h3>
<form method="post" action="{{ url_for('run_action') }}" enctype="multipart/form-data">
  Manifest JSON: <input type="file" name="manifest" accept="application/json">
  Pack name (optional): <input type="text" name="pack_name">
  <button name="action" value="token_pack">Build Pack</button>
  <small>Output: shared/token-packs/&lt;name&gt;_&lt;timestamp&gt;.zip</small>
</form>

<p><a href="{{ url_for('notifications') }}">Notification Settings</a></p>

<h3>Quick Open (Finder)</h3>
<p>
  <a href="{{ url_for('open_path', path=shared_token_packs) }}">Open shared/token-packs</a> |
  <a href="{{ url_for('open_path', path=reports_land) }}">Open shared/reports/land-coverage</a> |
  <a href="{{ url_for('open_path', path=reports_token) }}">Open shared/reports/token-coverage</a>
</p>
<form method="get" action="{{ url_for('open_path') }}">
  Path: <input type="text" name="path" size="60" placeholder="/full/path/within/project">
  <button type="submit">Open</button>
  <small>Server will only open paths within the project directory.</small>
</form>

<h3>Deck Report</h3>
<form method="post" action="{{ url_for('run_action') }}">
  <textarea name="deck_text" rows="10" cols="80" placeholder="Paste deck list or enter Moxfield/Archidekt URL"></textarea><br>
  Deck Name: <input type="text" name="deck_name">
  Profile (optional): <input type="text" name="profile">
  <button name="action" value="deck_report">Analyze Deck</button>
</form>

<h3>Land Coverage Report</h3>
<form method="post" action="{{ url_for('run_action') }}">
  Type: <select name="cov_type">
    <option value="nonbasic">nonbasic</option>
    <option value="basic">basic</option>
    <option value="all">all</option>
  </select>
  Set (optional): <input type="text" name="cov_set" placeholder="mh3">
  Output dir (optional): <input type="text" name="cov_out" size="40">
  <button name="action" value="land_coverage">Run Coverage</button>
  <small>Results: shared/reports/land-coverage/&lt;timestamp&gt;/</small>
  <br>
</form>

<h3>Token Search</h3>
<form method="get" action="{{ url_for('index') }}">
  Name: <input type="text" name="token_name" value="{{ request.args.get('token_name','') }}">
  Subtype: <input type="text" name="token_subtype" value="{{ request.args.get('token_subtype','') }}">
  Set: <input type="text" name="token_set" value="{{ request.args.get('token_set','') }}">
  Colors: <input type="text" name="token_colors" value="{{ request.args.get('token_colors','') }}">
  <button type="submit">Search Tokens</button>
</form>

{% if tokens %}
  <h4>Token Results (max 50)</h4>
  <ul>
  {% for token in tokens %}
    <li><strong>{{ token.name }}</strong> ({{ token.set }} #{{ token.collector }})
      <br>Subtype: {{ token.subtype }}
      <br>Keywords: {{ token.keywords|join(', ') }}
      <br>Oracle: {{ token.oracle_text or '—' }}
      <br>Image: <a href="{{ token.image_url }}" target="_blank">link</a>
      <br>Local art: {{ 'yes' if token.has_local else 'no' }} ({{ token.local_path }})
    </li>
  {% endfor %}
  </ul>
{% endif %}

<h3>Unique Artwork</h3>
<form method="get" action="{{ url_for('unique_art_view') }}">
  Name (resolve oracle_id): <input type="text" name="name" value="{{ request.args.get('name','') }}">
  Oracle ID: <input type="text" name="oracle_id" value="{{ request.args.get('oracle_id','') }}">
  Illustration ID: <input type="text" name="illustration_id" value="{{ request.args.get('illustration_id','') }}">
  Set: <input type="text" name="set" value="{{ request.args.get('set','') }}">
  <br>
  Art name contains: <input type="text" name="name_contains" value="{{ request.args.get('name_contains','') }}">
  Artist contains: <input type="text" name="artist" value="{{ request.args.get('artist','') }}">
  Frame: <input type="text" name="frame" value="{{ request.args.get('frame','') }}">
  Effect contains: <input type="text" name="effect" value="{{ request.args.get('effect','') }}">
  Full-art:
  <select name="full_art">
    <option value="" {% if not request.args.get('full_art') %}selected{% endif %}>any</option>
    <option value="1" {% if request.args.get('full_art')=='1' %}selected{% endif %}>yes</option>
    <option value="0" {% if request.args.get('full_art')=='0' %}selected{% endif %}>no</option>
  </select>
  Limit: <input type="number" name="limit" min="0" value="{{ request.args.get('limit','50') }}">
  <button type="submit">Search Unique Art</button>
  <small>0 = show all</small>
  <a href="{{ url_for('index') }}">Reset</a>
</form>

<h3>Search Tokens by Keyword</h3>
<form method="get" action="{{ url_for('index') }}">
  Keyword: <input type="text" name="token_kw" value="{{ request.args.get('token_kw','') }}">
  Set (optional): <input type="text" name="token_kw_set" value="{{ request.args.get('token_kw_set','') }}">
  Limit: <input type="number" name="token_kw_limit" min="0" value="{{ request.args.get('token_kw_limit','25') }}">
  <button type="submit">Search</button>
  <small>0 = show all</small>
</form>
{% if tokens_kw %}
  <h4>Keyword Results</h4>
  <ul>
  {% for t in tokens_kw %}
    <li><strong>{{ t.name }}</strong> ({{ t.set }} #{{ t.collector }}) — {{ t.subtype }}
      <br>Keywords: {{ t.keywords|join(', ') }}
      <br>Oracle: {{ t.oracle_text or '—' }}
      <br>Image: <a href="{{ t.image_url }}" target="_blank">link</a>
      <br>Local art: {{ 'yes' if t.has_local else 'no' }} ({{ t.local_path }})
    </li>
  {% endfor %}
  </ul>
{% endif %}

<h3>Search Cards by Oracle Text/Type</h3>
<form method="get" action="{{ url_for('index') }}">
  Query: <input type="text" name="card_query" value="{{ request.args.get('card_query','') }}">
  Set (optional): <input type="text" name="card_set" value="{{ request.args.get('card_set','') }}">
  Limit: <input type="number" name="card_limit" min="0" value="{{ request.args.get('card_limit','25') }}">
  Include tokens? <input type="checkbox" name="card_include" value="1" {% if request.args.get('card_include') %}checked{% endif %}>
  <button type="submit">Search</button>
  <small>0 = show all</small>
</form>
{% if cards %}
  <h4>Card Results</h4>
  <ul>
  {% for c in cards %}
    <li><strong>{{ c.name }}</strong> ({{ c.set }} #{{ c.collector }})
      <br>Type: {{ c.type_line }}
      <br>Keywords: {{ c.keywords|join(', ') }}
      <br>Oracle: {{ c.oracle_text or '—' }}
      <br>Image: <a href="{{ c.image_url }}" target="_blank">link</a>
      {% if c.oracle_id %}<br>Rulings: <a href="{{ url_for('rulings_view', oracle_id=c.oracle_id) }}" target="_blank">view</a>{% endif %}
      {% if c.set %} &nbsp; Set: <a href="{{ url_for('set_view', code=c.set|lower) }}" target="_blank">info</a>{% endif %}
      {% if c.local %}<br>Local token art: {{ c.local }} ({{ c.local_path }}){% endif %}
    </li>
  {% endfor %}
  </ul>
{% endif %}

<hr>

<div class="section">
<h3>API Quick Copy</h3>
<p>These examples reflect your current inputs where applicable.</p>
<pre><code>curl '{{ api_base }}/api/search?query={{ card_query or "destroy%20all%20creatures" }}&set={{ (card_set or '')|lower }}&include_tokens={{ '1' if card_include else '0' }}&limit={{ c_limit or 25 }}'</code></pre>
<pre><code>curl '{{ api_base }}/api/unique_art?name={{ (token_name or name or '')|replace(' ', '%20') }}&set={{ (token_set or set_code or '')|lower }}&limit={{ limit or 25 }}'</code></pre>
<pre><code>curl '{{ api_base }}/api/coverage?kind=nonbasic&set={{ (set_code or '')|lower }}&missing_only=0'</code></pre>
</div>

<hr>

<div class="section">
<h2>Recent Tasks</h2>
<table border="1" cellpadding="4" style="width:100%">
  <tr><th>ID</th><th>Name</th><th>Status</th><th>Started</th><th>Finished</th><th>Log</th></tr>
  {% for task in tasks %}
    <tr>
      <td>{{ task.id[:8] }}</td>
      <td>{{ task.name }}</td>
      <td>{{ task.status }}</td>
      <td>{{ task.started }}</td>
      <td>{{ task.finished or '' }}</td>
      <td><pre style="max-width:600px; overflow:auto;">{{ task.log }}</pre>{% if task.error %}<br><strong>Error:</strong> {{ task.error }}{% endif %}</td>
    </tr>
  {% endfor %}
</table>
</div>

</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    token_name = request.args.get("token_name")
    token_subtype = request.args.get("token_subtype")
    token_set = request.args.get("token_set")
    token_colors = request.args.get("token_colors")
    tokens = None
    if any([token_name, token_subtype, token_set]):
        tokens = _render_tokens(
            token_name or None,
            token_subtype or None,
            token_set.lower() if token_set else None,
            token_colors or None,
        )
    # Token keyword search
    tokens_kw = None
    token_kw = request.args.get("token_kw")
    token_kw_set = request.args.get("token_kw_set")
    token_kw_limit = request.args.get("token_kw_limit")
    try:
        kw_limit = int(token_kw_limit) if token_kw_limit is not None else 25
    except ValueError:
        kw_limit = 25
    if token_kw:
        tokens_kw = _search_tokens_by_keyword(
            token_kw, token_kw_set.lower() if token_kw_set else None, kw_limit
        )

    # Card oracle-text search
    cards = None
    card_query = request.args.get("card_query")
    card_set = request.args.get("card_set")
    card_limit = request.args.get("card_limit")
    card_include = request.args.get("card_include") == "1"
    try:
        c_limit = int(card_limit) if card_limit is not None else 25
    except ValueError:
        c_limit = 25
    if card_query:
        cards = _search_cards_by_oracle(
            card_query, card_set.lower() if card_set else None, c_limit, card_include
        )

    # Try to use new template file, fall back to inline template if it doesn't exist
    try:
        return render_template(
            "index.html",
            tasks=TASKS,
            tokens=tokens,
            tokens_kw=tokens_kw,
            cards=cards,
            api_base=f"http://{request.host}",
            card_query=card_query,
            card_set=card_set,
            c_limit=c_limit,
            card_include=card_include,
            token_name=token_name,
            token_set=token_set,
            name=request.args.get("name"),
            limit=request.args.get("limit"),
            set_code=request.args.get("set"),
        )
    except Exception:
        # Fallback to old inline template for backward compatibility
        base = os.path.join(
            create_pdf.project_root_directory, "magic-the-gathering", "shared"
        )
        return render_template_string(
            INDEX_TEMPLATE,
            tasks=TASKS,
            tokens=tokens,
            tokens_kw=tokens_kw,
            cards=cards,
            api_base=f"http://{request.host}",
            card_query=card_query,
            card_set=card_set,
            c_limit=c_limit,
            card_include=card_include,
            token_name=token_name,
            token_set=token_set,
            name=request.args.get("name"),
            limit=request.args.get("limit"),
            set_code=request.args.get("set"),
            shared_token_packs=os.path.join(base, "token-packs"),
            reports_land=os.path.join(base, "reports", "land-coverage"),
            reports_token=os.path.join(base, "reports", "token-coverage"),
        )


@app.route("/run", methods=["POST"])
def run_action():
    action = request.form.get("action")
    if action == "fetch_basics":
        run_task("Fetch Basic Lands", _fetch_basics_task)
    elif action == "fetch_nonbasics":
        run_task("Fetch Non-Basic Lands", _fetch_non_basics_task)
    elif action == "rules_delta":
        run_task("Rules Delta", _rules_delta_task)
    elif action == "deck_report":
        deck_text = request.form.get("deck_text", "").strip()
        if not deck_text:
            return redirect(url_for("index"))
        deck_name = request.form.get("deck_name") or None
        profile = request.form.get("profile") or None
        run_task("Deck Report", _deck_report_task, deck_text, deck_name, profile)
    elif action == "land_coverage":
        cov_type = request.form.get("cov_type", "nonbasic")
        cov_set = request.form.get("cov_set") or None
        cov_out = request.form.get("cov_out") or None
        run_task("Land Coverage", _land_coverage_task, cov_type, cov_set, cov_out)
    elif action == "token_pack":
        file = request.files.get("manifest")
        if not file:
            return redirect(url_for("index"))
        pack_name = request.form.get("pack_name") or None
        run_task("Token Pack", _token_pack_task, file.read(), pack_name)
    return redirect(url_for("index"))


# ==================== Profile & Deck Management APIs ====================


@app.route("/api/profiles", methods=["GET"])
def api_profiles():
    """List all available profiles."""
    try:
        profiles_path = os.path.join(
            create_pdf.project_root_directory,
            "proxy-machine",
            "assets",
            "profiles.json",
        )
        if not os.path.exists(profiles_path):
            return jsonify({"profiles": []})

        import json

        with open(profiles_path, "r") as f:
            profiles_data = json.load(f)

        profile_list = []
        for name in profiles_data.keys():
            profile_list.append({"name": name})

        return jsonify({"profiles": profile_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<profile>/decks", methods=["GET"])
def api_profile_decks(profile):
    """List all deck subfolders for a profile."""
    try:
        profile_paths = create_pdf.build_profile_directories(profile, {})
        front_dir = profile_paths.get("front_dir_path")
        back_dir = profile_paths.get("back_dir_path")
        double_dir = profile_paths.get("double_sided_dir_path")

        if not front_dir or not os.path.exists(front_dir):
            return jsonify({"decks": []})

        deck_names = create_pdf._deck_subfolders(front_dir, back_dir, double_dir)

        decks = []
        for deck_name in deck_names:
            deck_front = os.path.join(front_dir, deck_name)
            card_count = 0
            if os.path.isdir(deck_front):
                card_count = len(create_pdf._list_image_files(deck_front))
            decks.append({"name": deck_name, "card_count": card_count})

        return jsonify({"profile": profile, "decks": decks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<profile>/decks", methods=["POST"])
def api_create_deck(profile):
    """Create a new deck subfolder for a profile."""
    try:
        data = request.get_json()
        deck_name = data.get("deck_name")

        if not deck_name:
            return jsonify({"error": "deck_name is required"}), 400

        # Validate deck name
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]+", deck_name):
            return (
                jsonify(
                    {
                        "error": "Deck name must contain only letters, numbers, underscores, and dashes"
                    }
                ),
                400,
            )

        profile_paths = create_pdf.build_profile_directories(profile, {})
        front_dir = profile_paths.get("front_dir_path")
        back_dir = profile_paths.get("back_dir_path")
        double_dir = profile_paths.get("double_sided_dir_path")

        # Check if deck already exists
        existing_decks = create_pdf._deck_subfolders(front_dir, back_dir, double_dir)
        if deck_name in existing_decks:
            return jsonify({"error": f"Deck '{deck_name}' already exists"}), 409

        # Create the subdirectories
        deck_front = os.path.join(front_dir, deck_name)
        deck_back = os.path.join(back_dir, deck_name)
        deck_double = os.path.join(double_dir, deck_name)

        os.makedirs(deck_front, exist_ok=True)
        os.makedirs(deck_back, exist_ok=True)
        os.makedirs(deck_double, exist_ok=True)

        return jsonify(
            {
                "success": True,
                "deck_name": deck_name,
                "paths": {
                    "front": os.path.relpath(
                        deck_front, create_pdf.project_root_directory
                    ),
                    "back": os.path.relpath(
                        deck_back, create_pdf.project_root_directory
                    ),
                    "double_sided": os.path.relpath(
                        deck_double, create_pdf.project_root_directory
                    ),
                },
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _pdf_generation_task(
    buffer: io.StringIO,
    profile: str,
    deck: str | None,
    pdf_name: str | None,
    card_size: str = "standard",
    paper_size: str = "letter",
    crop: float = 3.0,
    ppi: int = 600,
    quality: int = 100,
    only_fronts: bool = False,
) -> None:
    """Background task for PDF generation with configurable options."""
    try:
        profile_paths = create_pdf.build_profile_directories(profile, {})
        front_dir = profile_paths.get("front_dir_path")
        back_dir = profile_paths.get("back_dir_path")
        double_dir = profile_paths.get("double_sided_dir_path")
        output_path = profile_paths.get("output_path")

        # Apply deck selection if specified
        if deck:
            front_dir, back_dir, double_dir = create_pdf._apply_deck_to_paths(
                front_dir, back_dir, double_dir, deck
            )

        # Override output path if pdf_name provided
        if pdf_name:
            import re

            if not re.fullmatch(r"[A-Za-z0-9-]+", pdf_name):
                buffer.write(
                    "Error: PDF name must contain only letters, numbers, and dashes\n"
                )
                return
            base_dir = os.path.dirname(output_path) or create_pdf.project_root_directory
            output_path = os.path.join(base_dir, f"{pdf_name}.pdf")

        # Ensure output directory exists
        output_directory_path = os.path.dirname(output_path)
        if output_directory_path:
            os.makedirs(output_directory_path, exist_ok=True)

        # Ensure fronts are multiple of 8
        create_pdf._ensure_front_multiple_of_eight(front_dir)

        # Ensure backs exist
        create_pdf._ensure_back_image(
            front_dir, back_dir, double_dir, only_fronts=only_fronts
        )

        # Ensure unique output path
        unique_output = create_pdf._ensure_unique_pdf_path(output_path)
        if unique_output != output_path:
            buffer.write(f"Output exists; using unique file: {unique_output}\n")
            output_path = unique_output

        buffer.write(
            f"Settings: {card_size} cards, {paper_size} paper, {crop}mm crop, {ppi} PPI, quality {quality}\n"
        )

        # Generate PDF
        create_pdf.generate_pdf(
            front_dir,
            back_dir,
            double_dir,
            output_path,
            card_size=card_size,
            paper_size=paper_size,
            crop=crop,
            extend_corners=False,
            ppi=ppi,
            quality=quality,
            skip=0,
            load_offset=0,
            output_images=False,
            only_fronts=only_fronts,
        )

        rel_path = os.path.relpath(output_path, create_pdf.project_root_directory)
        buffer.write(f"\nPDF created successfully: {rel_path}\n")
    except Exception as e:
        buffer.write(f"Error generating PDF: {str(e)}\n")


@app.route("/api/profiles/<profile>/pdf", methods=["POST"])
def api_generate_pdf(profile):
    """Generate a PDF for a profile (with optional deck selection and advanced options)."""
    try:
        data = request.get_json()
        deck = data.get("deck")  # Optional deck name
        pdf_name = data.get("pdf_name")  # Optional custom PDF filename

        # Advanced PDF generation options
        card_size = data.get("card_size", "standard")
        paper_size = data.get("paper_size", "letter")
        crop = data.get("crop", 3.0)
        ppi = data.get("ppi", 600)
        quality = data.get("quality", 100)
        only_fronts = data.get("only_fronts", False)

        run_task(
            f"Generate PDF - {profile}" + (f" ({deck})" if deck else ""),
            _pdf_generation_task,
            profile,
            deck,
            pdf_name,
            card_size,
            paper_size,
            crop,
            ppi,
            quality,
            only_fronts,
        )

        return jsonify({"success": True, "message": "PDF generation started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# File upload validation constants
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
MAX_FILE_SIZE_MB = 50  # 50MB per file
MAX_TOTAL_UPLOAD_MB = 500  # 500MB total per request


def _validate_upload_file(file) -> tuple[bool, str]:
    """Validate an uploaded file. Returns (is_valid, error_message)."""
    if not file or not file.filename:
        return False, "Empty file"

    # Check extension
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f"Invalid file type: {ext}. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"

    # Check file size (seek to end and back)
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Seek back to start

    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return False, f"File too large: {size / 1024 / 1024:.1f}MB (max {MAX_FILE_SIZE_MB}MB)"

    return True, ""


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and other issues."""
    # Get just the filename without any path components
    filename = os.path.basename(filename)
    # Remove any null bytes or special characters
    filename = filename.replace('\x00', '').replace('/', '').replace('\\', '')
    # Limit length
    name, ext = os.path.splitext(filename)
    if len(name) > 200:
        name = name[:200]
    return name + ext


@app.route("/api/profiles/<profile>/upload", methods=["POST"])
def api_upload_images(profile):
    """Upload card images to a profile's folders."""
    try:
        profile_paths = create_pdf.build_profile_directories(profile, {})
        base_dir = profile_paths.get("base_directory")
        front_dir = profile_paths.get("front_dir_path")
        back_dir = profile_paths.get("back_dir_path")
        double_dir = profile_paths.get("double_sided_dir_path")

        if not base_dir or not os.path.exists(base_dir):
            return jsonify({"error": f"Profile '{profile}' not found"}), 404

        # Get parameters
        deck = request.form.get("deck", "").strip()
        face = request.form.get("face", "front")
        files = request.files.getlist("files")

        if not files:
            return jsonify({"error": "No files provided"}), 400

        # Validate total upload size
        total_size = 0
        for file in files:
            file.seek(0, 2)
            total_size += file.tell()
            file.seek(0)

        if total_size > MAX_TOTAL_UPLOAD_MB * 1024 * 1024:
            return jsonify({
                "error": f"Total upload too large: {total_size / 1024 / 1024:.1f}MB (max {MAX_TOTAL_UPLOAD_MB}MB)"
            }), 400

        # Determine target directory
        if face == "front":
            target_dir = front_dir
        elif face == "back":
            target_dir = back_dir
        elif face == "double_sided":
            target_dir = double_dir
        else:
            return jsonify({"error": f"Invalid face type: {face}"}), 400

        # Apply deck subdirectory if specified
        if deck:
            # Sanitize deck name
            safe_deck = "".join(c for c in deck if c.isalnum() or c in "-_").lower()
            if not safe_deck:
                return jsonify({"error": "Invalid deck name"}), 400
            target_dir = os.path.join(target_dir, safe_deck)

        # Create directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)

        # Validate and save files
        uploaded_count = 0
        errors = []
        for file in files:
            is_valid, error = _validate_upload_file(file)
            if not is_valid:
                errors.append(f"{file.filename}: {error}")
                continue

            # Sanitize filename
            filename = _sanitize_filename(file.filename)
            filepath = os.path.join(target_dir, filename)
            file.save(filepath)
            uploaded_count += 1

        rel_path = os.path.relpath(target_dir, create_pdf.project_root_directory)
        result = {"success": True, "uploaded": uploaded_count, "destination": rel_path}
        if errors:
            result["errors"] = errors
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<profile>/import-deck", methods=["POST"])
def api_import_deck(profile):
    """Import and analyze a deck list, fetching card images."""
    try:
        data = request.get_json()
        deck_list = data.get("deck_list", "").strip()
        deck_name = data.get("deck_name", "").strip()

        if not deck_list:
            return jsonify({"error": "No deck list provided"}), 400

        profile_paths = create_pdf.build_profile_directories(profile, {})
        front_dir = profile_paths.get("front_dir_path")

        if not front_dir or not os.path.exists(front_dir):
            return jsonify({"error": f"Profile '{profile}' not found"}), 404

        # Create deck subfolder if deck_name provided
        if deck_name:
            deck_front = os.path.join(front_dir, deck_name)
            deck_back = os.path.join(profile_paths.get("back_dir_path"), deck_name)
            deck_double = os.path.join(
                profile_paths.get("double_sided_dir_path"), deck_name
            )
            os.makedirs(deck_front, exist_ok=True)
            os.makedirs(deck_back, exist_ok=True)
            os.makedirs(deck_double, exist_ok=True)
            target_dir = deck_front
        else:
            target_dir = front_dir

        # Launch background task to analyze and fetch
        run_task(
            f"Import Deck - {profile}" + (f" ({deck_name})" if deck_name else ""),
            _import_deck_task,
            deck_list,
            target_dir,
            profile,
        )

        # Quick parse to get card count for immediate response
        import re

        lines = deck_list.split("\n")
        card_count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            # Match lines like "4x Lightning Bolt" or "4 Lightning Bolt"
            match = re.match(r"^(\d+)x?\s+(.+)$", line, re.IGNORECASE)
            if match:
                card_count += int(match.group(1))

        return jsonify(
            {
                "success": True,
                "message": "Deck import started",
                "total_cards": card_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _import_deck_task(
    buffer: io.StringIO, deck_list: str, target_dir: str, profile: str
) -> None:
    """Background task for deck import and card fetching."""
    try:
        buffer.write(f"Analyzing deck list for profile '{profile}'...\n")

        # Use existing deck report functionality to parse the deck
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(deck_list)
            temp_deck_path = f.name

        try:
            # Parse the deck list
            buffer.write("Parsing deck list...\n")
            from deck import parser

            # Try to detect if it's a URL
            if deck_list.startswith("http"):
                buffer.write(f"Detected URL: {deck_list}\n")
                parsed = parser.parse_deck_from_url(deck_list)
            else:
                parsed = parser.parse_deck_from_file(temp_deck_path)

            if not parsed:
                buffer.write("Error: Could not parse deck list\n")
                return

            buffer.write(f"Found {len(parsed)} unique cards\n")

            # For each card, try to fetch image from Scryfall
            buffer.write("Fetching card images from Scryfall...\n")
            from db import bulk_index

            fetched = 0
            skipped = 0
            for card_name, quantity in parsed.items():
                # Search for card in database
                results = bulk_index.query_cards_optimized(
                    name_filter=card_name, limit=1
                )

                if results:
                    card = results[0]
                    image_url = card.get("image_uris", {}).get("png") or card.get(
                        "image_uris", {}
                    ).get("large")

                    if image_url:
                        # Download image
                        import urllib.request

                        filename = f"{card_name.lower().replace(' ', '-')}.png"
                        filepath = os.path.join(target_dir, filename)

                        if not os.path.exists(filepath):
                            try:
                                urllib.request.urlretrieve(image_url, filepath)
                                buffer.write(f"  Fetched: {card_name} ({quantity}x)\n")
                                fetched += 1
                            except Exception as e:
                                buffer.write(f"  Failed to fetch {card_name}: {e}\n")
                                skipped += 1
                        else:
                            buffer.write(f"  Skipped (exists): {card_name}\n")
                            skipped += 1
                else:
                    buffer.write(f"  Not found: {card_name}\n")
                    skipped += 1

            buffer.write(f"\nImport complete: {fetched} fetched, {skipped} skipped\n")
            buffer.write(
                f"Images saved to: {os.path.relpath(target_dir, create_pdf.project_root_directory)}\n"
            )

        finally:
            os.unlink(temp_deck_path)

    except Exception as e:
        buffer.write(f"Error importing deck: {str(e)}\n")


@app.route("/api/profiles/<profile>/download-latest-pdf", methods=["GET"])
def api_download_latest_pdf(profile):
    """Download the most recently generated PDF for a profile."""
    try:
        profile_paths = create_pdf.build_profile_directories(profile, {})
        pdf_dir = os.path.dirname(profile_paths.get("output_path"))

        if not os.path.exists(pdf_dir):
            return jsonify({"error": "PDF directory not found"}), 404

        # Find most recent PDF
        pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
        if not pdf_files:
            return jsonify({"error": "No PDFs found"}), 404

        pdf_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(pdf_dir, f)), reverse=True
        )
        latest_pdf = pdf_files[0]
        pdf_path = os.path.join(pdf_dir, latest_pdf)

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=latest_pdf,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main():
    parser = argparse.ArgumentParser(description="Proxy Machine dashboard server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=False)


@app.route("/open")
def open_path():
    path = request.args.get("path")
    if not path:
        return redirect(url_for("index"))
    abs_path = os.path.abspath(path)
    project = os.path.abspath(create_pdf.project_root_directory)
    if not abs_path.startswith(project + os.sep):
        return abort(403)
    try:
        if os.path.isdir(abs_path):
            import subprocess

            subprocess.run(["open", abs_path], check=False)
        else:
            import subprocess

            subprocess.run(["open", "-R", abs_path], check=False)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/download")
def download():
    path = request.args.get("path")
    if not path:
        return redirect(url_for("index"))
    abs_path = os.path.abspath(path)
    # Security: restrict to project directory tree
    project = os.path.abspath(create_pdf.project_root_directory)
    if not abs_path.startswith(project + os.sep):
        return abort(403)
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        return abort(404)
    return send_file(abs_path, as_attachment=True)


@app.route("/coverage", methods=["GET"])
def coverage_view():
    kind = (request.args.get("kind") or "nonbasic").lower()
    set_code = request.args.get("set")
    missing_only = request.args.get("missing_only") == "1"
    # Pagination
    try:
        page = max(1, int(request.args.get("page") or "1"))
    except ValueError:
        page = 1
    try:
        page_size = max(1, int(request.args.get("page_size") or "50"))
    except ValueError:
        page_size = 50

    # Load coverage module dynamically
    import importlib.util

    cov_path = os.path.join(os.path.dirname(__file__), "coverage.py")
    spec = importlib.util.spec_from_file_location("pm_cov", cov_path)
    if spec is None or spec.loader is None:
        abort(500)
    assert spec is not None and spec.loader is not None
    pm_cov = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(pm_cov)  # type: ignore[attr-defined]

    rows, summary = pm_cov.compute_coverage(kind, set_code)
    if missing_only:
        rows = [r for r in rows if not r.has_art]
    total_rows = len(rows)
    total_pages = (total_rows + page_size - 1) // page_size if page_size else 1
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]

    # Simple inline template for drilldown
    tmpl = """
    <!doctype html>
    <title>Coverage Drilldown</title>
    <h1>Coverage Drilldown</h1>
    <form method="get">
      Kind: <select name="kind">
        <option value="nonbasic" {% if kind=='nonbasic' %}selected{% endif %}>nonbasic</option>
        <option value="basic" {% if kind=='basic' %}selected{% endif %}>basic</option>
        <option value="all" {% if kind=='all' %}selected{% endif %}>all</option>
      </select>
      Set: <input type="text" name="set" value="{{ set_code or '' }}">
      Missing only? <input type="checkbox" name="missing_only" value="1" {% if missing_only %}checked{% endif %}>
      Page: <input type="number" name="page" min="1" value="{{ page }}">
      Page size: <input type="number" name="page_size" min="1" value="{{ page_size }}">
      <button type="submit">Run</button>
      <a href="{{ url_for('index') }}">Back</a>
    </form>
    <p>Coverage: {{ summary.covered }}/{{ summary.total }} ({{ '%.1f' % summary.coverage_pct }}%) kind={{ summary.kind }} set={{ summary.set_filter or 'ALL' }}</p>
    <p>
      Download: <a href="{{ url_for('api_coverage', kind=kind, set=set_code or '', missing_only='1' if missing_only else '0') }}" target="_blank">JSON</a>
      |
      <a href="{{ url_for('coverage_csv', kind=kind, set=set_code or '', missing_only='1' if missing_only else '0') }}" target="_blank">CSV</a>
    </p>
    <p>Showing {{ page }} / {{ total_pages }} pages ({{ page_size }} per page), total rows: {{ total_rows }}</p>
    <table border="1" cellpadding="4">
      <tr><th>Name</th><th>Set</th><th>Collector</th><th>Kind</th><th>Has Art</th><th>UA (all)</th><th>UA (set)</th><th>Local Paths</th></tr>
      {% for r in page_rows %}
      <tr>
        <td>{{ r.name }}{% if r.oracle_id %} — <a href="{{ url_for('unique_art_view', oracle_id=r.oracle_id, set=set_code) }}" target="_blank">unique art</a>{% endif %}</td>
        <td>{{ r.set.upper() }}</td>
        <td>{{ r.collector_number }}</td>
        <td>{{ r.kind }}</td>
        <td>{{ 'yes' if r.has_art else 'no' }}</td>
        <td>{{ r.ua_all }}</td>
        <td>{{ r.ua_in_set }}</td>
        <td>{{ ' '.join(r.local_paths) }}</td>
      </tr>
      {% endfor %}
    </table>
    <p>
      {% if page > 1 %}
        <a href="{{ url_for('coverage_view', kind=kind, set=set_code or '', missing_only='1' if missing_only else '0', page=page-1, page_size=page_size) }}">&laquo; Prev</a>
      {% endif %}
      {% if page < total_pages %}
        <a href="{{ url_for('coverage_view', kind=kind, set=set_code or '', missing_only='1' if missing_only else '0', page=page+1, page_size=page_size) }}">Next &raquo;</a>
      {% endif %}
    </p>
    """

    # Provide attribute-like dict for summary
    class Obj(dict):
        __getattr__ = dict.get

    return render_template_string(
        tmpl,
        rows=rows,
        page_rows=page_rows,
        summary=Obj(summary),
        kind=kind,
        set_code=set_code,
        missing_only=missing_only,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_rows=total_rows,
    )


@app.route("/api/coverage", methods=["GET"])
def api_coverage():
    kind = (request.args.get("kind") or "nonbasic").lower()
    set_code = request.args.get("set") or None
    missing_only = request.args.get("missing_only") in {"1", "true", "yes"}
    # Load coverage module dynamically
    import importlib.util

    cov_path = os.path.join(os.path.dirname(__file__), "coverage.py")
    spec = importlib.util.spec_from_file_location("pm_cov", cov_path)
    if spec is None or spec.loader is None:
        return jsonify({"error": "module_load_failed"}), 500
    assert spec is not None and spec.loader is not None
    pm_cov = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(pm_cov)  # type: ignore[attr-defined]
    rows, summary = pm_cov.compute_coverage(kind, set_code)
    if missing_only:
        rows = [r for r in rows if not r.has_art]
    # Serialize rows
    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "name": r.name,
                "set": r.set,
                "collector_number": r.collector_number,
                "kind": r.kind,
                "has_art": r.has_art,
                "local_paths": r.local_paths,
                "oracle_id": r.oracle_id,
                "ua_all": r.ua_all,
                "ua_in_set": r.ua_in_set,
            }
        )
    return jsonify({"summary": summary, "rows": items})


@app.route("/coverage_csv", methods=["GET"])
def coverage_csv():
    kind = (request.args.get("kind") or "nonbasic").lower()
    set_code = request.args.get("set") or None
    missing_only = request.args.get("missing_only") in {"1", "true", "yes"}
    # Load coverage module dynamically
    import importlib.util

    cov_path = os.path.join(os.path.dirname(__file__), "coverage.py")
    spec = importlib.util.spec_from_file_location("pm_cov", cov_path)
    if spec is None or spec.loader is None:
        return jsonify({"error": "module_load_failed"}), 500
    pm_cov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm_cov)  # type: ignore[attr-defined]
    rows, summary = pm_cov.compute_coverage(kind, set_code)
    if missing_only:
        rows = [r for r in rows if not r.has_art]
    # Build CSV in-memory
    import csv as _csv
    import io as _io

    output = _io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(
        [
            "name",
            "set",
            "collector",
            "oracle_id",
            "ua_all",
            "ua_in_set",
            "kind",
            "has_art",
            "local_paths",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.name,
                r.set.upper(),
                r.collector_number,
                r.oracle_id or "",
                r.ua_all,
                r.ua_in_set,
                r.kind,
                "yes" if r.has_art else "no",
                " ".join(r.local_paths),
            ]
        )
    csv_bytes = output.getvalue().encode("utf-8")
    headers = {
        "Content-Disposition": f"attachment; filename=coverage_{kind}_{(set_code or 'ALL').upper()}.csv"
    }
    return Response(csv_bytes, mimetype="text/csv", headers=headers)


@app.route("/unique_art", methods=["GET"])
def unique_art_view():
    name = (request.args.get("name") or "").strip()
    oracle_id = (request.args.get("oracle_id") or "").strip() or None
    illustration_id = (request.args.get("illustration_id") or "").strip() or None
    set_code = (request.args.get("set") or "").strip().lower() or None
    name_contains = (request.args.get("name_contains") or "").strip() or None
    artist = (request.args.get("artist") or "").strip() or None
    frame = (request.args.get("frame") or "").strip() or None
    effect = (request.args.get("effect") or "").strip() or None
    fa_param = request.args.get("full_art")
    full_art = None
    if fa_param == "1":
        full_art = True
    elif fa_param == "0":
        full_art = False
    try:
        limit = int(request.args.get("limit") or "50")
    except ValueError:
        limit = 50

    # Resolve oracle_id(s) from name if provided and oracle_id missing
    oracle_ids: list[str] = []
    if not oracle_id and name:
        oracle_ids = _resolve_oracle_ids(name, set_code)
    elif oracle_id:
        oracle_ids = [oracle_id]

    # Query unique artworks (prefers oracle_id; falls back to illustration_id/name filter)
    rows: list[dict] = []
    try:
        if oracle_ids:
            for oid in oracle_ids:
                arts = create_pdf.db_query_unique_artworks(
                    oracle_id=oid,
                    illustration_id=illustration_id,
                    set_filter=set_code,
                    limit=limit,
                    name_filter=name_contains,
                    artist_filter=artist,
                    frame_filter=frame,
                    frame_effect_contains=effect,
                    full_art=full_art,
                )
                for a in arts:
                    rows.append(a)
        else:
            # Fallback: if name provided but no oracle_id resolved, use name as name_filter
            fallback_name_filter = name_contains or (name if name else None)
            arts = create_pdf.db_query_unique_artworks(
                oracle_id=None,
                illustration_id=illustration_id,
                set_filter=set_code,
                limit=limit,
                name_filter=fallback_name_filter,
                artist_filter=artist,
                frame_filter=frame,
                frame_effect_contains=effect,
                full_art=full_art,
            )
            rows.extend(arts)
    except Exception:
        rows = []

    # Inline template for unique artworks
    tmpl = """
    <!doctype html>
    <title>Unique Artwork</title>
    <h1>Unique Artwork</h1>
    <form method=\"get\">
      Name: <input type=\"text\" name=\"name\" value=\"{{ name or '' }}\">\n
      Oracle ID: <input type=\"text\" name=\"oracle_id\" value=\"{{ oracle_id or '' }}\">\n
      Illustration ID: <input type=\"text\" name=\"illustration_id\" value=\"{{ illustration_id or '' }}\">\n
      Set: <input type=\"text\" name=\"set\" value=\"{{ set_code or '' }}\">\n
      Limit: <input type=\"number\" name=\"limit\" min=\"0\" value=\"{{ limit }}\">\n
      <button type=\"submit\">Search</button>
      <a href=\"{{ url_for('index') }}\">Back</a>
    </form>
    <p>Results: {{ rows|length }}</p>
    <table border=\"1\" cellpadding=\"4\">
      <tr><th>Name</th><th>Set</th><th>Collector</th><th>Artist</th><th>Illustration ID</th><th>Full Art</th><th>Image</th></tr>
      {% for r in rows %}
      <tr>
        <td>{{ r.name }}</td>
        <td>{{ (r.set or '')|upper }}</td>
        <td>{{ r.collector_number }}</td>
        <td>{{ r.artist or '—' }}</td>
        <td>{{ r.illustration_id or '—' }}</td>
        <td>{{ 'yes' if r.full_art else 'no' }}</td>
        <td>{% if r.image_url %}<a href=\"{{ r.image_url }}\" target=\"_blank\">link</a>{% else %}—{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
    """
    return render_template_string(
        tmpl,
        rows=rows,
        name=name,
        oracle_id=oracle_id,
        illustration_id=illustration_id,
        set_code=set_code,
        limit=limit,
    )


@app.route("/api/search", methods=["GET"])
def api_search():
    query = request.args.get("query") or ""
    set_code = (request.args.get("set") or "").strip().lower() or None
    limit_str = request.args.get("limit")
    include_tokens = request.args.get("include_tokens") in {"1", "true", "yes"}
    try:
        limit = int(limit_str) if limit_str is not None else 25
    except ValueError:
        limit = 25
    items = _search_cards_by_oracle(query, set_code, limit, include_tokens)
    return jsonify({"count": len(items), "items": items})


@app.route("/api/unique_art", methods=["GET"])
def api_unique_art():
    name = (request.args.get("name") or "").strip()
    oracle_id = (request.args.get("oracle_id") or "").strip() or None
    illustration_id = (request.args.get("illustration_id") or "").strip() or None
    set_code = (request.args.get("set") or "").strip().lower() or None
    name_contains = (request.args.get("name_contains") or "").strip() or None
    artist = (request.args.get("artist") or "").strip() or None
    frame = (request.args.get("frame") or "").strip() or None
    effect = (request.args.get("effect") or "").strip() or None
    fa_param = request.args.get("full_art")
    full_art = True if fa_param == "1" else False if fa_param == "0" else None
    try:
        limit = int(request.args.get("limit") or "50")
    except ValueError:
        limit = 50

    oracle_ids: list[str] = []
    if not oracle_id and name:
        oracle_ids = _resolve_oracle_ids(name, set_code)
    elif oracle_id:
        oracle_ids = [oracle_id]

    rows: list[dict] = []
    try:
        if oracle_ids:
            for oid in oracle_ids:
                arts = create_pdf.db_query_unique_artworks(
                    oracle_id=oid,
                    illustration_id=illustration_id,
                    set_filter=set_code,
                    limit=limit,
                    name_filter=name_contains,
                    artist_filter=artist,
                    frame_filter=frame,
                    frame_effect_contains=effect,
                    full_art=full_art,
                )
                rows.extend(arts)
        else:
            # Fallback: if name provided but no oracle_id resolved, use name as name_filter
            fallback_name_filter = name_contains or (name if name else None)
            rows = create_pdf.db_query_unique_artworks(
                oracle_id=None,
                illustration_id=illustration_id,
                set_filter=set_code,
                limit=limit,
                name_filter=fallback_name_filter,
                artist_filter=artist,
                frame_filter=frame,
                frame_effect_contains=effect,
                full_art=full_art,
            )
    except Exception:
        rows = []
    return jsonify({"count": len(rows), "items": rows})


@app.route("/api/unique_art/counts", methods=["GET"])
def api_unique_art_counts():
    name = (request.args.get("name") or "").strip()
    oracle_id = (request.args.get("oracle_id") or "").strip() or None
    set_code = (request.args.get("set") or "").strip().lower() or None

    oracle_ids: list[str] = []
    if not oracle_id and name:
        oracle_ids = _resolve_oracle_ids(name, set_code)
    elif oracle_id:
        oracle_ids = [oracle_id]

    per_oracle: list[dict] = []
    total_all = 0
    total_in_set = 0
    for oid in oracle_ids:
        try:
            c_all = int(db_count_unique_artworks(oracle_id=oid))
        except Exception:
            c_all = 0
        try:
            c_set = (
                int(db_count_unique_artworks(oracle_id=oid, set_filter=set_code))
                if set_code
                else None
            )
        except Exception:
            c_set = 0 if set_code else None
        per_oracle.append({"oracle_id": oid, "all": c_all, "in_set": c_set})
        total_all += c_all
        if set_code and isinstance(c_set, int):
            total_in_set += c_set

    payload = {
        "oracle_ids": oracle_ids,
        "set_filter": set_code,
        "totals": {"all": total_all, "in_set": total_in_set if set_code else None},
        "per_oracle": per_oracle,
    }
    return jsonify(payload)


@app.route("/set", methods=["GET"])
def set_view():
    code = (request.args.get("code") or "").strip().lower()
    if not code:
        return redirect(url_for("index"))
    try:
        data = scryfall_enrich.get_set_info(code)
    except Exception:
        data = {}
    tmpl = """
    <!doctype html>
    <title>Set Info</title>
    <h1>Set: {{ (data.code or '')|upper }}</h1>
    {% if data %}
      <p><strong>Name:</strong> {{ data.name }}</p>
      {% if data.icon_svg_uri %}
        <p><img src="{{ data.icon_svg_uri }}" alt="set symbol" height="32"></p>
      {% endif %}
      <p><strong>Released:</strong> {{ data.released_at or '—' }}</p>
      <p><strong>Type:</strong> {{ data.set_type or '—' }}</p>
      <p><strong>Card count:</strong> {{ data.card_count or '—' }}</p>
      <p><strong>Parent set:</strong> {{ data.parent_set_code or '—' }}</p>
      {% if data.scryfall_uri %}<p><strong>Scryfall:</strong> <a href="{{ data.scryfall_uri }}" target="_blank">link</a></p>{% endif %}
    {% else %}
      <p>No data.</p>
    {% endif %}
    <p><a href="{{ url_for('index') }}">Back</a></p>
    """
    return render_template_string(tmpl, data=data)


@app.route("/rulings", methods=["GET"])
def rulings_view():
    oracle_id = (request.args.get("oracle_id") or "").strip() or None
    name = (request.args.get("name") or "").strip()
    set_code = (request.args.get("set") or "").strip().lower() or None
    resolved_oid = oracle_id
    if not resolved_oid and name:
        oids = _resolve_oracle_ids(name, set_code)
        resolved_oid = oids[0] if oids else None
    rulings = []
    if resolved_oid:
        rulings = scryfall_enrich.get_rulings_for_oracle(resolved_oid)
    tmpl = """
    <!doctype html>
    <title>Rulings</title>
    <h1>Rulings</h1>
    <form method="get">
      Oracle ID: <input type="text" name="oracle_id" value="{{ oracle_id or '' }}">
      or Name: <input type="text" name="name" value="{{ name or '' }}">
      Set (opt): <input type="text" name="set" value="{{ set_code or '' }}">
      <button type="submit">Load</button>
      <a href="{{ url_for('index') }}">Back</a>
    </form>
    {% if resolved_oid %}<p><strong>Resolved oracle_id:</strong> {{ resolved_oid }}</p>{% endif %}
    {% if rulings %}
    <ul>
      {% for r in rulings %}
        <li><strong>{{ r.published_at }}</strong>: {{ r.comment }}</li>
      {% endfor %}
    </ul>
    {% else %}
      <p>No rulings found.</p>
    {% endif %}
    """
    return render_template_string(
        tmpl,
        rulings=rulings,
        oracle_id=oracle_id,
        resolved_oid=resolved_oid,
        name=name,
        set_code=set_code,
    )


# --- Phase 3: Rules Delta routes ---
@app.route("/rules_delta", methods=["GET"])
def rules_delta_page():
    # Dynamic import to avoid heavy imports at module load
    import importlib.util

    rd_path = os.path.join(os.path.dirname(__file__), "rules_delta.py")
    spec = importlib.util.spec_from_file_location("pm_rules_delta", rd_path)
    if spec is None or spec.loader is None:
        abort(500)
    assert spec is not None and spec.loader is not None
    pm_rd = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(pm_rd)  # type: ignore[attr-defined]

    result = pm_rd.generate_reports()
    tmpl = """
    <!doctype html>
    <title>Rules Delta</title>
    <h1>Rules Delta</h1>
    <p>Rows: {{ result.count }}</p>
    {% if result.csv %}<p>CSV: <a href="{{ url_for('download', path=result.csv) }}">download</a></p>{% endif %}
    {% if result.json %}<p>JSON: <a href="{{ url_for('download', path=result.json) }}">download</a></p>{% endif %}
    <p><a href="{{ url_for('index') }}">Back</a></p>
    """

    # Dict-like attribute access
    class Obj(dict):
        __getattr__ = dict.get

    return render_template_string(tmpl, result=Obj(result))


@app.route("/api/rules_delta", methods=["GET"])
def api_rules_delta():
    import importlib.util

    rd_path = os.path.join(os.path.dirname(__file__), "rules_delta.py")
    spec = importlib.util.spec_from_file_location("pm_rules_delta", rd_path)
    if spec is None or spec.loader is None:
        return jsonify({"error": "module_load_failed"}), 500
    assert spec is not None and spec.loader is not None
    pm_rd = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(pm_rd)  # type: ignore[attr-defined]
    result = pm_rd.generate_reports()
    return jsonify(result)


# --- Phase 3: DB info and maintenance ---
def _bulk_db_info() -> dict:
    info = {
        "db_path": None,
        "prints": 0,
        "unique_artworks": 0,
        "schema_version": None,
        "fts5": False,
    }
    try:
        import sqlite3
        from db.bulk_index import DB_PATH as BULK_DB_PATH  # type: ignore

        info["db_path"] = BULK_DB_PATH
        if os.path.exists(BULK_DB_PATH):
            conn = sqlite3.connect(BULK_DB_PATH)
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM prints")
                info["prints"] = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM unique_artworks")
                info["unique_artworks"] = int(cur.fetchone()[0])
                # Schema version (stored in meta table if present)
                try:
                    cur.execute("SELECT value FROM meta WHERE key='schema_version'")
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        info["schema_version"] = int(row[0])
                except Exception:
                    info["schema_version"] = None
                # FTS5 present?
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='oracle_fts'"
                )
                info["fts5"] = bool(cur.fetchone())
            finally:
                conn.close()
        # Cache/TTL/last-updated details from bulk files
        info["now"] = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        try:
            # Bulk metadata
            bmeta = create_pdf._read_json_file(create_pdf.BULK_METADATA_PATH)
        except Exception:
            bmeta = {}
        try:
            ometa = create_pdf._read_json_file(create_pdf.ORACLE_METADATA_PATH)
        except Exception:
            ometa = {}
        # Index metadata
        imeta = {}
        try:
            if os.path.exists(create_pdf.BULK_INDEX_PATH):
                idx = create_pdf._read_json_file(create_pdf.BULK_INDEX_PATH)
                imeta = idx.get("metadata", {})
        except Exception:
            imeta = {}

        # Compose
        def _age_secs(epoch: float | None) -> float | None:
            try:
                return float(time.time() - float(epoch)) if epoch is not None else None
            except Exception:
                return None

        info["bulk_meta"] = {
            "bulk_updated_at": bmeta.get("bulk_updated_at"),
            "downloaded_at": bmeta.get("downloaded_at"),
            "downloaded_at_epoch": bmeta.get("downloaded_at_epoch"),
            "age_seconds": _age_secs(bmeta.get("downloaded_at_epoch")),
            "refresh_seconds": getattr(create_pdf, "BULK_REFRESH_SECONDS", None),
        }
        info["oracle_meta"] = {
            "bulk_updated_at": ometa.get("bulk_updated_at"),
            "downloaded_at": ometa.get("downloaded_at"),
            "downloaded_at_epoch": ometa.get("downloaded_at_epoch"),
            "age_seconds": _age_secs(ometa.get("downloaded_at_epoch")),
        }
        info["index_meta"] = {
            "generated_at": imeta.get("generated_at"),
            "bulk_updated_at": imeta.get("bulk_updated_at"),
            "oracle_attached": imeta.get("oracle_attached"),
            "schema_version": imeta.get("schema_version"),
        }
    except Exception:
        pass
    return info


@app.route("/api/db_info", methods=["GET"])
def api_db_info():
    return jsonify(_bulk_db_info())


@app.route("/admin/db_maintenance", methods=["GET"])  # GET to avoid CSRF for now
def admin_db_maintenance():
    # Avoid accidental downloads by default; require allow_download=1 to permit network
    allow_dl = request.args.get("allow_download") in {"1", "true", "yes"}
    orig_offline = os.environ.get("PM_OFFLINE")
    try:
        if not allow_dl:
            os.environ["PM_OFFLINE"] = "1"
        # Force refresh of bulk index; respects PM_OFFLINE
        _ = create_pdf._load_bulk_index(force_refresh=True)
    finally:
        # Restore env var
        if orig_offline is None:
            os.environ.pop("PM_OFFLINE", None)
        else:
            os.environ["PM_OFFLINE"] = orig_offline

    info = _bulk_db_info()
    tmpl = """
    <!doctype html>
    <title>DB Maintenance</title>
    <h1>DB Maintenance</h1>
    <p>prints={{ info.prints }}, unique_artworks={{ info.unique_artworks }}, schema_version={{ info.schema_version or '—' }}, fts5={{ 'yes' if info.fts5 else 'no' }}</p>
    <p><a href="{{ url_for('index') }}">Back</a></p>
    <p>Tip: pass allow_download=1 to permit network downloads when not offline.</p>
    """

    class Obj(dict):
        __getattr__ = dict.get

    return render_template_string(tmpl, info=Obj(info))


# --- Phase 3: Additional JSON endpoints ---
@app.route("/api/set", methods=["GET"])
def api_set():
    code = (request.args.get("code") or "").strip().lower()
    if not code:
        return jsonify({"error": "missing_code"}), 400
    try:
        data = scryfall_enrich.get_set_info(code)
    except Exception as e:
        return jsonify({"error": "fetch_failed", "message": str(e)}), 502
    return jsonify(data)


@app.route("/api/rulings", methods=["GET"])
def api_rulings():
    oracle_id = (request.args.get("oracle_id") or "").strip() or None
    name = (request.args.get("name") or "").strip()
    set_code = (request.args.get("set") or "").strip().lower() or None
    resolved_oid = oracle_id
    if not resolved_oid and name:
        ids = _resolve_oracle_ids(name, set_code)
        resolved_oid = ids[0] if ids else None
    if not resolved_oid:
        return jsonify({"count": 0, "items": [], "resolved_oracle_id": None})
    try:
        items = scryfall_enrich.get_rulings_for_oracle(resolved_oid)
    except Exception:
        items = []
    return jsonify(
        {"count": len(items), "items": items, "resolved_oracle_id": resolved_oid}
    )


NOTIFICATIONS_TEMPLATE = """
<!doctype html>
<title>Notification Settings</title>
<h1>Notification Settings</h1>

<form method="post">
  <h3>General</h3>
  Enabled: <input type="checkbox" name="enabled" value="1" {% if cfg.enabled %}checked{% endif %}><br>

  <h3>macOS</h3>
  Enabled: <input type="checkbox" name="macos_enabled" value="1" {% if cfg.macos.enabled %}checked{% endif %}><br>

  <h3>Webhook</h3>
  Enabled: <input type="checkbox" name="webhook_enabled" value="1" {% if cfg.webhook.enabled %}checked{% endif %}><br>
  URL: <input type="text" size="60" name="webhook_url" value="{{ cfg.webhook.url }}"><br>

  <br><button type="submit">Save</button>
  <a href="{{ url_for('index') }}">Back</a>
</form>
"""


@app.route("/notifications", methods=["GET", "POST"])
def notifications():
    cfg = create_pdf._load_notification_config()
    if request.method == "POST":
        enabled = request.form.get("enabled") == "1"
        macos_enabled = request.form.get("macos_enabled") == "1"
        webhook_enabled = request.form.get("webhook_enabled") == "1"
        webhook_url = (request.form.get("webhook_url") or "").strip()
        new_cfg = {
            "enabled": enabled,
            "macos": {"enabled": macos_enabled},
            "webhook": {"enabled": webhook_enabled, "url": webhook_url},
        }
        create_pdf._save_notification_config(new_cfg)
        return redirect(url_for("notifications"))

    # Render
    # Provide attribute-like access for template
    class Obj(dict):
        __getattr__ = dict.get

    return render_template_string(
        NOTIFICATIONS_TEMPLATE,
        cfg=Obj(
            {
                "enabled": cfg.get("enabled", False),
                "macos": Obj({"enabled": cfg.get("macos", {}).get("enabled", False)}),
                "webhook": Obj(
                    {
                        "enabled": cfg.get("webhook", {}).get("enabled", False),
                        "url": cfg.get("webhook", {}).get("url", ""),
                    }
                ),
            }
        ),
    )


# ============================================================
# ADMIN SECTION
# ============================================================

ADMIN_LOGIN_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Admin Login</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; max-width: 400px; margin: 100px auto; padding: 20px; }
        .login-box { background: #f5f5f5; padding: 30px; border-radius: 8px; }
        h1 { margin-top: 0; }
        input[type="password"] { width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; }
        button:hover { background: #0056b3; }
        .error { color: red; margin-bottom: 10px; }
        a { color: #007bff; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Admin Login</h1>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="post">
            <input type="password" name="password" placeholder="Admin Password" required autofocus>
            <input type="hidden" name="next" value="{{ next_url }}">
            <button type="submit">Login</button>
        </form>
        <p><a href="/">Back to Dashboard</a></p>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Admin Dashboard</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }
        h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }
        .section { background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }
        .section h2 { margin-top: 0; }
        .btn { display: inline-block; background: #007bff; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; text-decoration: none; margin: 5px 5px 5px 0; }
        .btn:hover { background: #0056b3; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .btn-success { background: #28a745; }
        .btn-success:hover { background: #218838; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
        th { background: #e9ecef; }
        .status { padding: 3px 8px; border-radius: 3px; font-size: 0.9em; }
        .status-ok { background: #d4edda; color: #155724; }
        .status-warn { background: #fff3cd; color: #856404; }
        .logout { float: right; }
        .message { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .message-success { background: #d4edda; color: #155724; }
        .message-error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>Admin Dashboard <a href="{{ url_for('admin_logout') }}" class="btn btn-danger logout">Logout</a></h1>

    {% if message %}
    <div class="message message-{{ message_type or 'success' }}">{{ message }}</div>
    {% endif %}

    <div class="section">
        <h2>Database</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Prints</td><td>{{ db_info.prints or 0 }}</td></tr>
            <tr><td>Unique Artworks</td><td>{{ db_info.unique_artworks or 0 }}</td></tr>
            <tr><td>Schema Version</td><td>{{ db_info.schema_version or 'N/A' }}</td></tr>
            <tr><td>FTS5 Enabled</td><td><span class="status {{ 'status-ok' if db_info.fts5 else 'status-warn' }}">{{ 'Yes' if db_info.fts5 else 'No' }}</span></td></tr>
        </table>
        <form method="post" action="{{ url_for('admin_sync_db') }}" style="display:inline;">
            <button type="submit" class="btn btn-success">Sync Database</button>
        </form>
        <a href="{{ url_for('admin_db_maintenance_protected') }}?allow_download=1" class="btn">Refresh Index (with download)</a>
    </div>

    <div class="section">
        <h2>Profiles</h2>
        <table>
            <tr><th>Profile</th><th>Decks</th><th>Actions</th></tr>
            {% for profile in profiles %}
            <tr>
                <td>{{ profile.name }}</td>
                <td>{{ profile.deck_count }}</td>
                <td>
                    <a href="{{ url_for('admin_view_profile', name=profile.name) }}" class="btn" style="padding: 5px 10px;">View</a>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="3">No profiles found</td></tr>
            {% endfor %}
        </table>
        <h3>Create New Profile</h3>
        <form method="post" action="{{ url_for('admin_create_profile') }}">
            <input type="text" name="profile_name" placeholder="Profile name" required>
            <button type="submit" class="btn btn-success">Create Profile</button>
        </form>
    </div>

    <div class="section">
        <h2>System Info</h2>
        <table>
            <tr><th>Setting</th><th>Value</th></tr>
            <tr><td>Tailscale</td><td><span class="status {{ 'status-ok' if tailscale_enabled else 'status-warn' }}">{{ 'Enabled' if tailscale_enabled else 'Disabled' }}</span></td></tr>
            <tr><td>Shared Root</td><td>{{ shared_root }}</td></tr>
            <tr><td>Profiles Root</td><td>{{ profiles_root }}</td></tr>
            <tr><td>Bulk Data Dir</td><td>{{ bulk_data_dir }}</td></tr>
        </table>
    </div>

    <p><a href="/">Back to Dashboard</a></p>
</body>
</html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not ADMIN_PASSWORD:
        return (
            render_template_string(
                "<h1>Admin Disabled</h1><p>Set ADMIN_PASSWORD environment variable to enable.</p>"
                "<p><a href='/'>Back</a></p>"
            ),
            403,
        )

    error = None
    next_url = request.args.get("next", url_for("admin_dashboard"))
    client_ip = request.remote_addr or "unknown"

    # Check rate limit
    is_allowed, seconds_remaining = _check_login_rate_limit(client_ip)
    if not is_allowed:
        error = f"Too many login attempts. Please try again in {seconds_remaining} seconds."
        return render_template_string(ADMIN_LOGIN_TEMPLATE, error=error, next_url=next_url), 429

    if request.method == "POST":
        password = request.form.get("password", "")
        next_url = request.form.get("next", url_for("admin_dashboard"))
        # Use timing-safe comparison to prevent timing attacks
        if _secure_compare(password, ADMIN_PASSWORD):
            session["admin_authenticated"] = True
            session.permanent = True  # Session persists
            _clear_login_attempts(client_ip)
            return redirect(next_url)
        else:
            _record_login_attempt(client_ip)
            attempts_left = MAX_LOGIN_ATTEMPTS - len(LOGIN_ATTEMPTS.get(client_ip, []))
            if attempts_left > 0:
                error = f"Invalid password. {attempts_left} attempts remaining."
            else:
                error = f"Too many failed attempts. Locked out for {LOGIN_LOCKOUT_SECONDS // 60} minutes."

    return render_template_string(ADMIN_LOGIN_TEMPLATE, error=error, next_url=next_url)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    message = request.args.get("message")
    message_type = request.args.get("message_type", "success")

    # Get database info
    db_info = _bulk_db_info()

    # Get profiles
    profiles = []
    profiles_root = os.environ.get(
        "PROFILES_ROOT",
        os.path.join(
            create_pdf.project_root_directory, "magic-the-gathering", "proxied-decks"
        ),
    )
    if os.path.isdir(profiles_root):
        for entry in os.scandir(profiles_root):
            if entry.is_dir() and not entry.name.startswith("."):
                deck_count = 0
                decks_dir = os.path.join(entry.path, "decklist")
                if os.path.isdir(decks_dir):
                    deck_count = len(
                        [f for f in os.listdir(decks_dir) if f.endswith(".txt")]
                    )
                profiles.append({"name": entry.name, "deck_count": deck_count})

    return render_template_string(
        ADMIN_DASHBOARD_TEMPLATE,
        db_info=db_info,
        profiles=profiles,
        message=message,
        message_type=message_type,
        tailscale_enabled=os.environ.get("TAILSCALE_ENABLED", "").lower() == "true",
        shared_root=os.environ.get("SHARED_ROOT", "N/A"),
        profiles_root=os.environ.get("PROFILES_ROOT", "N/A"),
        bulk_data_dir=os.environ.get("BULK_DATA_DIR", "N/A"),
    )


@app.route("/admin/sync_db", methods=["POST"])
@admin_required
def admin_sync_db():
    try:
        # Force refresh bulk index with network downloads allowed
        orig_offline = os.environ.get("PM_OFFLINE")
        os.environ.pop("PM_OFFLINE", None)
        try:
            create_pdf._load_bulk_index(force_refresh=True)
        finally:
            if orig_offline is not None:
                os.environ["PM_OFFLINE"] = orig_offline
        return redirect(
            url_for(
                "admin_dashboard",
                message="Database synced successfully",
                message_type="success",
            )
        )
    except Exception as e:
        return redirect(
            url_for(
                "admin_dashboard", message=f"Sync failed: {e}", message_type="error"
            )
        )


@app.route("/admin/create_profile", methods=["POST"])
@admin_required
def admin_create_profile():
    profile_name = request.form.get("profile_name", "").strip()
    if not profile_name:
        return redirect(
            url_for(
                "admin_dashboard", message="Profile name required", message_type="error"
            )
        )

    # Sanitize profile name
    safe_name = "".join(c for c in profile_name if c.isalnum() or c in "-_").lower()
    if not safe_name:
        return redirect(
            url_for(
                "admin_dashboard", message="Invalid profile name", message_type="error"
            )
        )

    profiles_root = os.environ.get(
        "PROFILES_ROOT",
        os.path.join(
            create_pdf.project_root_directory, "magic-the-gathering", "proxied-decks"
        ),
    )
    profile_path = os.path.join(profiles_root, safe_name)

    if os.path.exists(profile_path):
        return redirect(
            url_for(
                "admin_dashboard",
                message=f"Profile '{safe_name}' already exists",
                message_type="error",
            )
        )

    try:
        os.makedirs(os.path.join(profile_path, "decklist"), exist_ok=True)
        os.makedirs(os.path.join(profile_path, "output"), exist_ok=True)
        return redirect(
            url_for(
                "admin_dashboard",
                message=f"Profile '{safe_name}' created",
                message_type="success",
            )
        )
    except Exception as e:
        return redirect(
            url_for(
                "admin_dashboard",
                message=f"Failed to create profile: {e}",
                message_type="error",
            )
        )


@app.route("/admin/profile/<name>")
@admin_required
def admin_view_profile(name):
    profiles_root = os.environ.get(
        "PROFILES_ROOT",
        os.path.join(
            create_pdf.project_root_directory, "magic-the-gathering", "proxied-decks"
        ),
    )
    profile_path = os.path.join(profiles_root, name)

    if not os.path.isdir(profile_path):
        return redirect(
            url_for(
                "admin_dashboard",
                message=f"Profile '{name}' not found",
                message_type="error",
            )
        )

    decks = []
    decks_dir = os.path.join(profile_path, "decklist")
    if os.path.isdir(decks_dir):
        for f in os.listdir(decks_dir):
            if f.endswith(".txt"):
                decks.append(f[:-4])

    tmpl = """
    <!doctype html>
    <html>
    <head>
        <title>Profile: {{ name }}</title>
        <style>
            body { font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .btn { display: inline-block; background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; margin: 2px; }
            ul { list-style: none; padding: 0; }
            li { padding: 8px; background: #f5f5f5; margin: 5px 0; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Profile: {{ name }}</h1>
        <h2>Decks ({{ decks|length }})</h2>
        <ul>
        {% for deck in decks %}
            <li>{{ deck }}</li>
        {% else %}
            <li>No decks found</li>
        {% endfor %}
        </ul>
        <p><a href="{{ url_for('admin_dashboard') }}" class="btn">Back to Admin</a></p>
    </body>
    </html>
    """
    return render_template_string(tmpl, name=name, decks=decks)


@app.route("/admin/db_maintenance_protected", methods=["GET"])
@admin_required
def admin_db_maintenance_protected():
    """Protected version of db_maintenance that requires admin auth."""
    allow_dl = request.args.get("allow_download") in {"1", "true", "yes"}
    orig_offline = os.environ.get("PM_OFFLINE")
    try:
        if not allow_dl:
            os.environ["PM_OFFLINE"] = "1"
        _ = create_pdf._load_bulk_index(force_refresh=True)
    finally:
        if orig_offline is None:
            os.environ.pop("PM_OFFLINE", None)
        else:
            os.environ["PM_OFFLINE"] = orig_offline

    return redirect(
        url_for(
            "admin_dashboard",
            message="Database index refreshed",
            message_type="success",
        )
    )


if __name__ == "__main__":
    main()
