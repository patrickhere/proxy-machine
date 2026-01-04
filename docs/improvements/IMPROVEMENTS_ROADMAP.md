# The Proxy Machine: Improvements Roadmap

**Created:** 2025-11-19
**Status:** Implementation in progress

This document tracks major architectural improvements to The Proxy Machine, transitioning from a functional monolith to a well-structured, maintainable, and testable application.

---

## Goals

1. **Maintainability**: Break 10K line monolith into cohesive modules
2. **Testability**: Achieve 60%+ test coverage with comprehensive unit/integration tests
3. **Performance**: Add caching layers for database queries and HTTP requests
4. **Observability**: Structured logging, metrics, and monitoring
5. **Developer Experience**: Better tooling, documentation, and contribution workflow
6. **Extensibility**: Plugin system, API server, background jobs

---

## Phase 1: Infrastructure (COMPLETED ✓)

### 1.1 Editor Configuration ✓
- [x] `.editorconfig` - Consistent formatting across editors
- [x] `.gitattributes` - Proper line ending handling
- [x] Pre-commit hooks already exist and configured

### 1.2 Configuration Management ✓
- [x] `config/settings.py` - Type-safe Pydantic settings
- [x] Environment variable support (PM_* prefix)
- [x] Centralized defaults for threading, paths, PDF generation
- [x] Validation at startup

### 1.3 Logging Framework ✓
- [x] `core/logging.py` - Loguru-based structured logging
- [x] Console output with colors and formatting
- [x] File output with rotation and retention
- [x] Async logging for performance
- [x] Context managers for operation timing

**Files Created:**
- `.editorconfig`
- `.gitattributes`
- `config/settings.py`
- `core/__init__.py`
- `core/logging.py`

---

## Phase 2: Module Extraction (IN PROGRESS)

### 2.1 Target Modules

Extract from `create_pdf.py` (10,910 lines) into:

```
core/
├── __init__.py               ✓ Created
├── logging.py                ✓ Created
├── classification.py         [ ] Land/token type classification
├── naming.py                 [ ] File naming conventions
├── art_types.py              [ ] Art type derivation
├── card_fetch.py             [ ] Universal card fetching
├── land_fetch.py             [ ] Land-specific fetching
├── token_fetch.py            [ ] Token-specific fetching
├── relationship_expansion.py [ ] MDFC, tokens, meld partners
├── prompts.py                [ ] User interaction helpers
├── profiles.py               [ ] Profile management
└── download.py               [ ] Image download with retry
```

### 2.2 Priority Functions to Extract

**High Priority** (complex, testable, reusable):
1. `_classify_land_type()` → `core/classification.py`
2. `_derive_art_type()` → `core/art_types.py`
3. `_land_base_stem()`, `_token_base_stem()` → `core/naming.py`
4. `_fetch_cards_universal()` → `core/card_fetch.py`
5. `_download_image_with_retry()` → `core/download.py`

**Medium Priority** (domain logic):
6. Token detection and expansion
7. Relationship resolution
8. Profile initialization
9. Library health checks

**Low Priority** (keep in CLI):
- Click command definitions
- Menu system
- User prompts for interactive mode

### 2.3 Extraction Strategy

1. **Copy function to new module** (don't move yet)
2. **Add comprehensive tests** for extracted function
3. **Update imports** in `create_pdf.py`
4. **Verify all tests pass**
5. **Remove original function** from `create_pdf.py`
6. **Update documentation**

---

## Phase 3: Test Coverage (NEXT)

### 3.1 Test Structure

```
tests/
├── unit/
│   ├── test_classification.py  [ ] Land type classification
│   ├── test_art_types.py        [ ] Art type derivation
│   ├── test_naming.py           [ ] File naming conventions
│   ├── test_download.py         [ ] Download retry logic
│   ├── test_query_builders.py   [ ] SQL query generation
│   └── test_relationship.py     [ ] Relationship expansion
├── integration/
│   ├── test_fetch_workflow.py   [ ] End-to-end fetch
│   ├── test_pdf_generation.py   [ ] End-to-end PDF
│   └── test_deck_parsing.py     ✓ Exists (17 tests)
└── fixtures/
    ├── manifest.json             ✓ Exists
    ├── sample_cards.json         [ ] Card data samples
    └── sample_lands.json          [ ] Land data samples
```

### 3.2 Coverage Goals

- **Current**: ~20% (estimated)
- **Target Phase 3**: 60%
- **Target Phase 6**: 75%

### 3.3 Priority Test Areas

1. **Classification logic** (edge cases, special lands)
2. **Art type taxonomy** (15+ types, modifiers)
3. **File naming** (consistency critical)
4. **Database queries** (SQL correctness)
5. **Download retry** (network resilience)

---

## Phase 4: Caching & Performance (PLANNED)

### 4.1 Query Caching

```python
# Add to requirements.txt:
# diskcache==5.6.3

from diskcache import Cache

query_cache = Cache("./cache/db_queries", size_limit=100_000_000)

@query_cache.memoize(expire=3600)
def query_cards_optimized(...):
    # Existing implementation
```

### 4.2 HTTP Caching

```python
http_cache = Cache("./cache/http", size_limit=500_000_000)

def download_with_cache(url):
    if url in http_cache:
        return http_cache[url]
    data = urlopen(url).read()
    http_cache[url] = data
    return data
```

### 4.3 Performance Targets

- **Query cache hit ratio**: >80%
- **HTTP cache hit ratio**: >60%
- **Average query time**: <50ms (cached)
- **Download threads**: Configurable 1-32

---

## Phase 5: API Server & Background Jobs (FUTURE)

### 5.1 REST API Server

```python
# api_server.py
from flask import Flask, jsonify
from core.card_fetch import fetch_cards
from core.logging import get_logger

app = Flask(__name__)
logger = get_logger(__name__)

@app.route('/api/cards/search')
def search_cards():
    query = request.args.get('q')
    cards = db_query_oracle_fts(query)
    return jsonify(cards)

@app.route('/api/profile/<name>/pdf', methods=['POST'])
def generate_pdf(name):
    task_id = enqueue_pdf_generation(name)
    return jsonify({'task_id': task_id, 'status': 'queued'})
```

### 5.2 Background Job Queue

```python
# Use RQ (Redis Queue) for simplicity
from rq import Queue
from redis import Redis

redis_conn = Redis()
queue = Queue(connection=redis_conn)

# Enqueue long-running operation
job = queue.enqueue(fetch_entire_set, set_code="mh3")
```

### 5.3 Celery Integration (Alternative)

For more complex workflows, distributed tasks.

---

## Phase 6: Web UI & Observability (FUTURE)

### 6.1 Enhanced Dashboard

Expand existing `dashboard.py`:
- Card browser with advanced search
- Deck builder (drag & drop)
- PDF preview before generation
- Profile management UI
- Collection statistics and graphs

Technology: Alpine.js + Tailwind CSS (lightweight, no build step)

### 6.2 Metrics & Monitoring

```python
# metrics.py
from prometheus_client import Counter, Histogram, start_http_server

cards_fetched = Counter('cards_fetched_total', 'Total cards fetched', ['set_code'])
download_duration = Histogram('download_duration_seconds', 'Image download time')
pdf_generation_duration = Histogram('pdf_generation_seconds', 'PDF generation time')

# In code:
with download_duration.time():
    download_image(url)
cards_fetched.labels(set_code=set_code).inc()

# Start metrics server:
start_http_server(settings.metrics_port)  # :9090/metrics
```

### 6.3 Observability Stack

- **Metrics**: Prometheus + Grafana
- **Logs**: Loguru → Loki (optional)
- **Tracing**: OpenTelemetry (optional)

---

## Quick Wins (COMPLETED / IN PROGRESS)

- [x] `.editorconfig` - Consistent formatting
- [x] `.gitattributes` - Line ending handling
- [x] Configuration management (`config/settings.py`)
- [x] Structured logging (`core/logging.py`)
- [x] Pre-commit hooks (already existed)
- [ ] Extract 5 core modules
- [ ] Add 30+ unit tests
- [ ] Add caching layer
- [ ] Update requirements.txt
- [ ] Add CONTRIBUTING.md
- [ ] Add issue templates
- [ ] Set up GitHub Actions

---

## Implementation Timeline

### Week 1-2: Infrastructure & Module Extraction
- [x] Configuration and logging setup
- [ ] Extract classification, naming, art_types modules
- [ ] Add unit tests for extracted modules
- [ ] Update create_pdf.py imports

### Week 3-4: Testing & Caching
- [ ] Expand test coverage to 40%
- [ ] Add caching layer (database + HTTP)
- [ ] Performance benchmarking
- [ ] Documentation updates

### Month 2: API & Background Jobs
- [ ] REST API server
- [ ] Background job queue
- [ ] API authentication
- [ ] API documentation (OpenAPI)

### Month 3-6: Web UI & Polish
- [ ] Enhanced dashboard
- [ ] Metrics and monitoring
- [ ] Plugin hot reloading
- [ ] Performance optimizations
- [ ] Final documentation pass

---

## Success Metrics

### Code Quality
- [ ] Test coverage: 60%+
- [ ] Type coverage: 90%+ (pyright)
- [ ] No critical security issues (bandit)
- [ ] All linters pass (ruff, black)

### Performance
- [ ] Average query time: <100ms
- [ ] Cache hit ratio: >70%
- [ ] PDF generation: <10s for 100 cards
- [ ] Download throughput: >100 cards/min

### Developer Experience
- [ ] Setup time: <15 minutes
- [ ] Test run time: <60 seconds
- [ ] Documentation completeness: 90%
- [ ] Issue resolution time: <7 days average

### User Experience
- [ ] Error messages: Clear and actionable
- [ ] Response times: <5s for common operations
- [ ] Uptime: >99% (if running as server)
- [ ] User-reported bugs: <5 per month

---

## Next Steps

1. **Extract classification.py module** (today)
2. **Add 10 unit tests** for classification (today)
3. **Extract naming.py module** (tomorrow)
4. **Extract art_types.py module** (tomorrow)
5. **Add caching layer** (this week)

---

## Notes

- Maintain backwards compatibility throughout
- Keep CLI interface unchanged
- Document all breaking changes
- Update CLAUDE.md with architectural changes
- Keep Makefile targets working

---

**Last Updated:** 2025-11-19
**Status:** Phase 1 complete, Phase 2 in progress
