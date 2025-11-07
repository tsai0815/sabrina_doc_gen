import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Set

IN_PATH = Path("data/lsp_output/python_multilspy_output.json")
OUT_PATH = Path("data/lsp_output/dependencies.json")


# ---------------------------
# Helpers for range handling
# ---------------------------

def pos_in_range(line: int, ch: int, rng: Dict[str, Any]) -> bool:
    """Return True if (line, ch) is inside the given LSP range [start, end)."""
    if not isinstance(rng, dict):
        return False
    s = rng.get("start") or {}
    e = rng.get("end") or {}
    sl, sc = int(s.get("line", 10**9)), int(s.get("character", 10**9))
    el, ec = int(e.get("line", -1)), int(e.get("character", -1))
    if (line < sl) or (line > el):
        return False
    if line == sl and ch < sc:
        return False
    if line == el and ch >= ec:
        return False
    return True


def symbol_span(sym: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """Return (sl, sc, el, ec) for a symbol's range; defaults to zeros if missing."""
    rng = sym.get("range") or {}
    s = rng.get("start") or {}
    e = rng.get("end") or {}
    return int(s.get("line", 0)), int(s.get("character", 0)), int(e.get("line", 0)), int(e.get("character", 0))


# ---------------------------
# Indexing and file helpers
# ---------------------------

def build_symbol_index(files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Map file (relative path key) -> list of symbols (keeps ranges for caller locating)."""
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for fe in files:
        fname = fe.get("file")
        if isinstance(fname, str):
            idx[fname] = fe.get("symbols", [])
    return idx


def normalize_ref_file(ref_file: str, index_keys: List[str]) -> Optional[str]:
    """
    Try to map a reference file path (relative or absolute) to an index key (relative path).
    Heuristics: exact match -> endswith match -> basename match.
    """
    if ref_file in index_keys:
        return ref_file
    for k in index_keys:
        if k.endswith(ref_file) or ref_file.endswith(k):
            return k
    # As a last resort, try basename match
    ref_base = Path(ref_file).name
    for k in index_keys:
        if Path(k).name == ref_base:
            return k
    return None


def get_line_text(abs_path: Optional[str], line: int) -> Optional[str]:
    """Best-effort read one line (0-based) from abs_path; return None if not available."""
    if not isinstance(abs_path, str):
        return None
    p = Path(abs_path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            for i, l in enumerate(f):
                if i == line:
                    return l.rstrip("\n")
    except Exception:
        return None
    return None


# ---------------------------
# Caller locating
# ---------------------------

def find_enclosing_symbol(symbols: List[Dict[str, Any]], line: int, ch: int) -> Optional[Dict[str, Any]]:
    """
    Find the innermost symbol whose range encloses (line, ch).
    Prefer function/method kinds and smaller spans.
    """
    candidates: List[Dict[str, Any]] = []
    for s in symbols:
        if pos_in_range(line, ch, s.get("range") or {}):
            candidates.append(s)
    if not candidates:
        return None

    def sort_key(s: Dict[str, Any]) -> Tuple[int, int]:
        sl, sc, el, ec = symbol_span(s)
        span_score = (el - sl) * 10_000 + (ec - sc)
        kind = s.get("kind")
        # Prefer method(6)/function(12)
        pref = 0 if kind in (6, 12) else 1
        return (pref, span_score)

    candidates.sort(key=sort_key)
    return candidates[0]


def looks_like_import(line_text: Optional[str]) -> bool:
    """Simple heuristic to detect import lines in Python."""
    if not line_text:
        return False
    t = line_text.strip()
    return t.startswith("import ") or t.startswith("from ")


def looks_like_call_context(line_text: Optional[str], col: Optional[int]) -> bool:
    """
    Lightweight check for call context: after the symbol token there is a '(' soon.
    If we cannot check safely, return True (non-strict).
    """
    if line_text is None or col is None:
        return True
    # Allow some spaces between name and '('
    tail = line_text[col: col + 64]
    # Find first '(' after some chars; crude but effective for Python
    return "(" in tail


# ---------------------------
# Callee canonicalization
# ---------------------------

def canonicalize_callee(sym: Dict[str, Any], fallback_file: str) -> Tuple[str, str]:
    """
    Return (callee_file, callee_name) canonicalized to the definition file if available.
    If no definition is present, fallback to current file.
    """
    callee_name = sym.get("name")
    if not isinstance(callee_name, str):
        return fallback_file, "<unknown>"

    defs = sym.get("definitions") or []
    if defs and isinstance(defs, list) and isinstance(defs[0], dict):
        def_path = defs[0].get("relativePath") or defs[0].get("absolutePath")
        if isinstance(def_path, str):
            return def_path, callee_name
    return fallback_file, callee_name


# ---------------------------
# Core dependency builder
# ---------------------------

def build_dependencies(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create function-level edges A->B by inverting references:
      For each callee B (symbol), for each reference location r:
        - skip imports and callee-definition-line refs
        - find caller A whose range contains r.start in that file
        - produce A -> canonical(B)
    Also output file-level edges (fileA -> fileB) if any A->B exists across files.
    """
    files = data.get("files", [])
    index = build_symbol_index(files)
    index_keys = list(index.keys())

    func_edges: List[Dict[str, str]] = []
    file_edges: Set[Tuple[str, str]] = set()

    for file_entry in files:
        callee_file_rel = file_entry.get("file")
        if not isinstance(callee_file_rel, str):
            continue

        for sym in file_entry.get("symbols", []):
            # Canonicalize callee to its definition file if available
            canon_file, callee_name = canonicalize_callee(sym, callee_file_rel)
            callee_file_key = normalize_ref_file(canon_file, index_keys) or canon_file
            callee_id = f"{callee_file_key}:{callee_name}"

            # Callee's own definition range (to ignore self-definition as ref)
            callee_rng = sym.get("range") or {}
            callee_def_line = (callee_rng.get("start") or {}).get("line")

            for ref in sym.get("references", []) or []:
                ref_file = ref.get("relativePath") or ref.get("absolutePath")
                ref_rng = ref.get("range")
                if not isinstance(ref_file, str) or not isinstance(ref_rng, dict):
                    continue

                # Skip import lines (not a call)
                abs_path = ref.get("absolutePath")
                start = ref_rng.get("start") or {}
                line = start.get("line")
                col = start.get("character")
                ref_line_text = get_line_text(abs_path, int(line)) if isinstance(line, int) else None
                if looks_like_import(ref_line_text):
                    continue

                # Skip the callee's own definition line
                if isinstance(callee_def_line, int) and isinstance(line, int) and line == callee_def_line:
                    continue

                # Optional: require call-like context (has '(' after token)
                if not looks_like_call_context(ref_line_text, int(col) if isinstance(col, int) else None):
                    # If you prefer to keep non-call refs, comment this out
                    continue

                # Map ref file to index key to locate caller symbols
                ref_file_key = normalize_ref_file(ref_file, index_keys)
                if not ref_file_key:
                    continue
                syms_in_ref_file = index.get(ref_file_key)
                if not syms_in_ref_file:
                    continue

                # Find caller: the innermost symbol in ref file whose range encloses the ref position
                caller_sym = find_enclosing_symbol(
                    syms_in_ref_file,
                    int(line) if isinstance(line, int) else -1,
                    int(col) if isinstance(col, int) else -1
                )
                if not caller_sym:
                    continue

                caller_name = caller_sym.get("name", "<unknown>")
                # Heuristic: skip tiny alias-like symbols (often import alias or simple assignments)
                sl, sc, el, ec = symbol_span(caller_sym)
                if caller_name == callee_name and (el - sl == 0) and (ec - sc < 64):
                    # likely an import alias symbol; skip
                    continue

                caller_id = f"{ref_file_key}:{caller_name}"
                if caller_id != callee_id:
                    func_edges.append({"src": caller_id, "dst": callee_id})
                    # file-level
                    caller_file = ref_file_key
                    callee_file_for_edge = callee_file_key if isinstance(callee_file_key, str) else str(callee_file_key)
                    if caller_file != callee_file_for_edge:
                        file_edges.add((caller_file, callee_file_for_edge))

    # Deduplicate edges
    seen: Set[Tuple[str, str]] = set()
    dedup_func_edges: List[Dict[str, str]] = []
    for e in func_edges:
        k = (e["src"], e["dst"])
        if k not in seen:
            seen.add(k)
            dedup_func_edges.append(e)

    return {
        "function_edges": dedup_func_edges,
        "file_edges": [{"src": s, "dst": d} for (s, d) in sorted(file_edges)]
    }


def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    deps = build_dependencies(data)
    OUT_PATH.write_text(json.dumps(deps, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[INFO] Wrote dependencies → {OUT_PATH}")


if __name__ == "__main__":
    main()
