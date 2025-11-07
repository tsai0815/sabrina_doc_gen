import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

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


def lsp_scan_repo(repo_root: Path, code_language: str = "python") -> Dict[str, Any]:
    """
    Use multilspy's SyncLanguageServer to scan an entire project directory:
      - Retrieve document symbols (functions, classes, variables)
      - Optionally query references, definitions, and hover info
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

            # 1) Retrieve document symbols
            try:
                symbols = lsp.request_document_symbols(rel_path)
            except Exception as e:
                print(f"[WARN] document_symbols failed on {rel_path}: {e}")
                symbols = []

            file_entry = {
                "file": rel_path,
                "symbols": symbols,
                "references": [],
                "definitions": [],
                "hovers": []
            }

            # 2) Flatten symbol tree for convenience
            def flatten(nodes):
                stack = list(nodes or [])
                out = []
                while stack:
                    s = stack.pop(0)
                    # node can be a dict (symbol) or a nested list
                    if isinstance(s, dict):
                        out.append(s)
                        children = s.get("children") or []
                        if isinstance(children, list) and children:
                            # prepend so traversal preserves source order
                            stack = list(children) + stack
                    elif isinstance(s, list):
                        # expand nested list nodes preserving order
                        if s:
                            stack = list(s) + stack
                    else:
                        # ignore unexpected types
                        continue
                return out

            flat_symbols = flatten(symbols)
            seen_positions = set()

            # 3) For each symbol, request references / definitions / hover
            for s in flat_symbols:
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

                # References
                try:
                    refs = lsp.request_references(rel_path, line, col)
                    file_entry["references"].append({
                        "symbol": name,
                        "at": {"line": line, "col": col},
                        "items": refs
                    })
                except Exception:
                    pass

                # Definitions
                try:
                    defs = lsp.request_definition(rel_path, line, col)
                    if defs:
                        file_entry["definitions"].append({
                            "symbol": name,
                            "at": {"line": line, "col": col},
                            "items": defs
                        })
                except Exception:
                    pass

                # Hover information (signature, docstring, etc.)
                try:
                    hv = lsp.request_hover(rel_path, line, col)
                    if hv:
                        file_entry["hovers"].append({
                            "symbol": name,
                            "at": {"line": line, "col": col},
                            "info": hv
                        })
                except Exception:
                    pass

            results.append(file_entry)

    return {
        "repo_root": str(repo_root),
        "language": code_language,
        "files": results
    }


def main():
    """Main entry: scan the test project and save results."""
    repo_root = Path("data/test_proj").resolve()
    out_dir = Path("data/lsp_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = lsp_scan_repo(repo_root, code_language="python")

    out_file = out_dir / "python_multilspy_output.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Saved: {out_file}")


if __name__ == "__main__":
    main()
