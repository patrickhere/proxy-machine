import os
import json
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "proxy-machine", "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "plugins.json")
PLUGINS_DIR = SCRIPT_DIR  # proxy-machine/plugins/


def _load_config() -> Dict[str, Any]:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        cfg = {"enabled": [], "disabled": [], "settings": {}}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"enabled": [], "disabled": [], "settings": {}}


essential_fields = {"name", "version", "description"}


def _discover_local_plugins() -> List[Tuple[str, Dict[str, Any]]]:
    plugins: List[Tuple[str, Dict[str, Any]]] = []
    for child in sorted(Path(PLUGINS_DIR).iterdir()):
        if not child.is_dir():
            continue
        # Look for a module file exposing PLUGIN metadata
        candidate = child / "__init__.py"
        if not candidate.exists():
            continue
        spec = importlib.util.spec_from_file_location(
            f"plugins.{child.name}", str(candidate)
        )
        if not spec or not spec.loader:
            continue
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        except Exception:
            continue
        meta = getattr(mod, "PLUGIN", None)
        if not isinstance(meta, dict):
            continue
        if not essential_fields.issubset(meta.keys()):
            continue
        plugins.append((child.name, meta))
    return plugins


def list_plugins() -> None:
    cfg = _load_config()
    discovered = _discover_local_plugins()
    if not discovered:
        print("No local plugins found in proxy-machine/plugins/.")
        return
    print("Discovered plugins:")
    for folder, meta in discovered:
        status = "enabled" if meta.get("name") in cfg.get("enabled", []) else "disabled"
        print(
            f"- {meta.get('name')} ({meta.get('version')}) [{status}] — {meta.get('description')}"
        )


def list_plugins_payload() -> list[dict]:
    cfg = _load_config()
    discovered = _discover_local_plugins()
    payload: list[dict] = []
    for folder, meta in discovered:
        payload.append(
            {
                "folder": folder,
                "name": meta.get("name"),
                "version": meta.get("version"),
                "description": meta.get("description"),
                "enabled": bool(meta.get("name") in cfg.get("enabled", [])),
            }
        )
    return payload


def enable_plugin(name: str) -> None:
    cfg = _load_config()
    if name in cfg.get("enabled", []):
        print(f"Plugin '{name}' is already enabled.")
        return
    # Verify exists
    available = {meta.get("name"): folder for folder, meta in _discover_local_plugins()}
    if name not in available:
        print(
            f"Plugin '{name}' not found. Run 'plugins-list' to see available plugins."
        )
        return
    cfg.setdefault("enabled", []).append(name)
    cfg["disabled"] = [n for n in cfg.get("disabled", []) if n != name]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"Enabled '{name}'.")


def disable_plugin(name: str) -> None:
    cfg = _load_config()
    if name in cfg.get("disabled", []):
        print(f"Plugin '{name}' is already disabled.")
        return
    cfg["enabled"] = [n for n in cfg.get("enabled", []) if n != name]
    cfg.setdefault("disabled", []).append(name)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"Disabled '{name}'.")


def new_plugin(name: str) -> None:
    safe = name.strip().lower().replace(" ", "_")
    if not safe:
        print("Plugin name is required.")
        return
    dest = Path(PLUGINS_DIR) / safe
    if dest.exists():
        print(f"Plugin folder '{dest}' already exists.")
        return
    dest.mkdir(parents=True, exist_ok=True)
    init_path = dest / "__init__.py"
    meta = {
        "name": name,
        "version": "0.1.0",
        "description": f"Custom plugin '{name}'",
    }
    boilerplate = f"""# Auto-generated plugin skeleton\n\nPLUGIN = {json.dumps(meta, indent=2)}\n\n# Optional: hook examples\n# def register_menu():\n#     return [{{'label': 'Example', 'action': 'example_action'}}]\n"""
    init_path.write_text(boilerplate, encoding="utf-8")
    print(f"Created plugin skeleton at {init_path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Plugin manager")
    sub = parser.add_subparsers(dest="cmd")

    lp = sub.add_parser("list", help="List discovered plugins and enabled status")
    lp.add_argument(
        "--json", action="store_true", help="Emit JSON instead of text table"
    )
    en = sub.add_parser("enable", help="Enable a plugin by name")
    en.add_argument("name")
    dis = sub.add_parser("disable", help="Disable a plugin by name")
    dis.add_argument("name")
    nw = sub.add_parser("new", help="Create a new plugin skeleton")
    nw.add_argument("name")

    args = parser.parse_args()

    if args.cmd == "list":
        if getattr(args, "json", False):
            print(json.dumps(list_plugins_payload(), indent=2))
        else:
            list_plugins()
    elif args.cmd == "enable":
        enable_plugin(args.name)
    elif args.cmd == "disable":
        disable_plugin(args.name)
    elif args.cmd == "new":
        new_plugin(args.name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
