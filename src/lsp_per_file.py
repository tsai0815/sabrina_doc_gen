import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


def open_file_text(path: Path) -> str:
    """Safely read file content as UTF-8 text."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def find_symbol_positions(src: str, name: str) -> List[Tuple[int, int]]:
    """
    A simple name locator: search each line for the first occurrence of 'name'.
    Returns a list of (line, col) tuples.
    Note: This is a lightweight demo, not a precise AST-based locator.
    """
    hits = []
    for i, line in enumerate(src.splitlines()):
        col = line.find(name)
        if col >= 0:
            hits.append((i, col))
    return hits


def flatten_symbols(symbols: Any) -> List[Dict[str, Any]]:
    """Flatten a possibly nested LSP symbol tree into a flat list of dicts."""
    flat: List[Dict[str, Any]] = []
    stack: List[Any] = list(symbols or [])
    while stack:
        node = stack.pop(0)
        if node is None:
            continue
        if isinstance(node, dict):
            flat.append(node)
            children = node.get("children") or []
            if isinstance(children, list) and children:
                stack = list(children) + stack
        elif isinstance(node, list):
            if node:
                stack = list(node) + stack
        else:
            continue
    return flat


def lsp_scan_repo(repo_root: Path, code_language: str = "python") -> Dict[str, Any]:
    """
    Scan a project directory and emit compact JSON:
      {
        "repo_root": ..., "language": ..., "files": [
          {"file": "relative/path.py", "symbols": [
             {"name": str, "kind": int, "range": {...}, "selectionRange": {...},
              "detail": str|None, "references": [...], "definitions": [...], "hover": {...}|None}
          ]}
        ]
      }
    """
    logger = MultilspyLogger()
    config = MultilspyConfig.from_dict({"code_language": code_language})
    lsp = SyncLanguageServer.create(config, logger, str(repo_root))

    results: List[Dict[str, Any]] = []
    py_files = list(repo_root.rglob("*.py"))
    if not py_files:
        print(f"[WARN] No .py files found under: {repo_root}")

    with lsp.start_server():
        for f in py_files:
            rel_path = str(f.relative_to(repo_root))
            file_text = open_file_text(f)

            # Request document symbols for this file
            try:
                symbols_tree = lsp.request_document_symbols(rel_path)
            except Exception as e:
                print(f"[WARN] document_symbols failed on {rel_path}: {e}")
                symbols_tree = []

            flat_syms = flatten_symbols(symbols_tree)
            seen_positions: set[Tuple[str, int, int, str]] = set()
            packed_symbols: List[Dict[str, Any]] = []

            # For each symbol, collect references/definitions/hover and attach to the symbol object
            for s in flat_syms:
                name = s.get("name")
                if not isinstance(name, str) or not name:
                    continue

                positions = find_symbol_positions(file_text, name)
                if not positions:
                    continue

                line, col = positions[0]
                key = (rel_path, line, col, name)
                if key in seen_positions:
                    continue
                seen_positions.add(key)

                sym_obj: Dict[str, Any] = {
                    "name": name,
                    "kind": s.get("kind"),
                    "range": s.get("range"),
                    "selectionRange": s.get("selectionRange"),
                    "detail": s.get("detail"),
                    "references": [],
                    "definitions": [],
                    "hover": None,
                }

                # References
                try:
                    refs = lsp.request_references(rel_path, line, col) or []
                    sym_obj["references"] = refs
                except Exception:
                    pass

                # Definitions
                try:
                    defs = lsp.request_definition(rel_path, line, col) or []
                    sym_obj["definitions"] = defs
                except Exception:
                    pass

                # Hover
                try:
                    hv = lsp.request_hover(rel_path, line, col)
                    sym_obj["hover"] = hv
                except Exception:
                    pass

                packed_symbols.append(sym_obj)

            results.append({
                "file": rel_path,
                "symbols": packed_symbols
            })

    return {
        "repo_root": str(repo_root),
        "language": code_language,
        "files": results
    }


def main():
    """Main entry: scan the test project and save results."""
    repo_root = Path("data/test_project").resolve()
    out_dir = Path("data/lsp_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = lsp_scan_repo(repo_root, code_language="python")

    out_file = out_dir / "python_multilspy_output.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Saved: {out_file}")


if __name__ == "__main__":
    main()
