import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_TOKEN = "PROJECT"

# ---------------- I/O utils ----------------

def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(obj: Any, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------- path helpers ----------------

def is_external_id(sym_id: str) -> bool:
    return isinstance(sym_id, str) and (sym_id.startswith("/") or sym_id.startswith("external:/"))

def resolve_file_path(repo_root: Path, file_field: Optional[str], sym_id: Optional[str]) -> Optional[Path]:
    """
    Resolve the real file path for this symbol.
    Priority:
      1) If 'file' is a relative path, join with repo_root.
      2) If 'file' starts with PROJECT/, replace with repo_root.
      3) If symbol id looks like '<abs>:name', use the absolute part.
    """
    if isinstance(file_field, str) and file_field:
        if file_field.startswith(PROJECT_TOKEN + "/"):
            return Path(file_field.replace(PROJECT_TOKEN, str(repo_root), 1)).resolve()
        p = Path(file_field)
        if not p.is_absolute():
            return (repo_root / p).resolve()
        return p.resolve()

    # Fallback: parse from id "<abs-or-project-path>:<name>"
    if isinstance(sym_id, str) and ":" in sym_id:
        left = sym_id.rsplit(":", 1)[0]
        if left.startswith(PROJECT_TOKEN + "/"):
            return Path(left.replace(PROJECT_TOKEN, str(repo_root), 1)).resolve()
        p = Path(left)
        return p if p.is_absolute() else (repo_root / p).resolve()

    return None

# ---------------- range helpers ----------------

def extract_by_lsp_range(text: str, rng: Dict[str, Any]) -> str:
    """
    Extract code for an LSP Range. LSP ranges are half-open: [start, end).
    We support multi-line and character-precise slicing.
    """
    lines = text.splitlines(keepends=True)  # preserve EOLs
    s = rng.get("start", {})
    e = rng.get("end", {})
    sl, sc = int(s.get("line", 0)), int(s.get("character", 0))
    el, ec = int(e.get("line", 0)), int(e.get("character", 0))

    if sl < 0 or el < 0 or sl >= len(lines):
        return ""
    if el >= len(lines):
        el = len(lines) - 1
        ec = len(lines[el])

    if sl == el:
        return lines[sl][sc:ec]

    parts: List[str] = []
    parts.append(lines[sl][sc:])
    for i in range(sl + 1, el):
        parts.append(lines[i])
    parts.append(lines[el][:ec])
    return "".join(parts)

def extend_upwards_for_decorators(full_text: str, rng: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expand the range upwards to include contiguous decorators/comments/blank lines
    immediately above the function definition line.
    """
    lines = full_text.splitlines()
    s = dict(rng.get("start", {}))
    el = int(rng.get("end", {}).get("line", s.get("line", 0)))

    sl = int(s.get("line", 0))
    while sl - 1 >= 0:
        prev = lines[sl - 1].lstrip()
        if prev.startswith("@") or prev.startswith("#") or prev == "":
            sl -= 1
        else:
            break
    s["line"] = sl
    new_rng = dict(rng)
    new_rng["start"] = s
    return new_rng

def pad_range_by_lines(full_text: str, rng: Dict[str, Any], pad: int) -> Dict[str, Any]:
    """
    Extend the range up/down by N full lines (not character-precise), bounded by file size.
    """
    if pad <= 0:
        return rng
    lines = full_text.splitlines()
    s = dict(rng.get("start", {}))
    e = dict(rng.get("end", {}))
    sl = max(0, int(s.get("line", 0)) - pad)
    el = min(len(lines) - 1, int(e.get("line", 0)) + pad)
    s["line"] = sl
    e["line"] = el
    s["character"] = 0
    e["character"] = len(lines[el]) if el < len(lines) else 0
    out = dict(rng)
    out["start"] = s
    out["end"] = e
    return out

# ---------------- selection helpers ----------------

def parse_ids_arg(arg: Optional[str]) -> Optional[List[str]]:
    """
    Parse --only-ids which can be:
      - None
      - a comma-separated list of ids
      - a file path to a text file with one id per line
    """
    if not arg:
        return None
    p = Path(arg)
    if p.exists() and p.is_file():
        content = p.read_text(encoding="utf-8").splitlines()
        return [x.strip() for x in content if x.strip()]
    # else treat as comma-separated
    return [x.strip() for x in arg.split(",") if x.strip()]

# ---------------- main logic ----------------

def main():
    ap = argparse.ArgumentParser(description="Create LLM snippets by slicing source code using LSP ranges.")
    ap.add_argument("--input-file", required=True, help="Path to final_integrated.json (or pruned JSON).")
    ap.add_argument("--output-file", required=True, help="Where to write snippets JSON.")
    ap.add_argument("--only-ids", help="Comma list or file path of symbol IDs to include.")
    ap.add_argument("--include-externals", action="store_true", help="Also slice external symbols (ids starting with '/').")
    ap.add_argument("--include-decorators", action="store_true", help="Expand range upward to include decorators/comments.")
    ap.add_argument("--pad-lines", type=int, default=0, help="Pad the range with N lines above and below.")
    ap.add_argument("--emit-files", help="If set, additionally write each snippet to this directory as a .py file.")
    args = ap.parse_args()

    data = load_json(Path(args.input_file))
    repo_root = Path(data.get("repoRoot") or ".").resolve()
    symbols = data.get("symbols", [])
    want_ids = parse_ids_arg(args.only_ids)

    out_snippets: List[Dict[str, Any]] = []
    emit_dir = Path(args.emit_files).resolve() if args.emit_files else None
    if emit_dir:
        emit_dir.mkdir(parents=True, exist_ok=True)

    for sym in symbols:
        sid = sym.get("id")
        if not isinstance(sid, str):
            continue
        if want_ids is not None and sid not in want_ids:
            continue
        if (not args.include_externals) and is_external_id(sid):
            continue

        file_path = resolve_file_path(repo_root, sym.get("file"), sid)
        rng = sym.get("range")
        if not file_path or not isinstance(rng, dict):
            continue
        if not file_path.exists():
            # Still emit a record with an error string (useful for debugging externals)
            out_snippets.append({
                "id": sid,
                "name": sym.get("name"),
                "file": str(sym.get("file") or ""),
                "fileAbs": str(file_path),
                "range": rng,
                "code_snippet": f"# [ERROR] File not found: {file_path}"
            })
            continue

        text = file_path.read_text(encoding="utf-8", errors="ignore")

        # Optionally expand upwards for decorators/comments
        eff_range = dict(rng)
        if args.include_decorators:
            eff_range = extend_upwards_for_decorators(text, eff_range)

        # Optional pad
        if args.pad_lines and args.pad_lines > 0:
            eff_range = pad_range_by_lines(text, eff_range, args.pad_lines)

        code = extract_by_lsp_range(text, eff_range)

        rec = {
            "id": sid,
            "name": sym.get("name"),
            "file": str(sym.get("file") or ""),
            "fileAbs": str(file_path),
            "range": rng,              # original range
            "effectiveRange": eff_range,  # after decorator/pad adjustments
            "code_snippet": code
        }
        out_snippets.append(rec)

        # Optionally emit .py files for each snippet
        if emit_dir:
            safe_name = sid.replace("/", "_").replace(":", "__")
            (emit_dir / f"{safe_name}.py").write_text(code, encoding="utf-8")

    save_json(out_snippets, Path(args.output_file))
    print(f"[INFO] Wrote {len(out_snippets)} snippets → {args.output_file}")

if __name__ == "__main__":
    main()
