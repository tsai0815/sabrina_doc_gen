import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, DefaultDict
from collections import defaultdict
import argparse


# Inputs
DEFAULT_OUT_ROOT = Path("data/lsp_json_outputs")
PROJECT_TOKEN = "PROJECT"  # must match your prune step


# -----------------------------
# Utilities
# -----------------------------

def to_project_rel(path_str: str) -> Tuple[bool, str]:
    """
    Return (is_project_path, project_relative_str) from a pruned path like
    'PROJECT/data/test_project/main.py' or an external absolute path.
    """
    if not isinstance(path_str, str):
        return False, path_str
    if path_str.startswith(PROJECT_TOKEN + "/"):
        return True, path_str[len(PROJECT_TOKEN) + 1 :]
    return False, path_str


def normalize_external_path(s: str) -> str:
    """
    Best-effort normalization for external/absolute paths coming from deps endpoints.
    Examples:
      "../../../../../../../../../usr/lib/python3.10/csv.py" -> "/usr/lib/python3.10/csv.py"
      "/usr/lib/python3.10/csv.py"                           -> "/usr/lib/python3.10/csv.py"
    If it contains '/usr/', take substring from first '/usr/'.
    Otherwise, if it looks absolute already, return as-is.
    Otherwise, try Path(s).resolve() (may depend on CWD).
    """
    if not isinstance(s, str):
        return s
    if "/usr/" in s:
        return s[s.index("/usr/") :]
    if s.startswith("/"):
        return s
    try:
        return str(Path(s).resolve())
    except Exception:
        return s


def parse_dep_endpoint(ep: str) -> Tuple[str, str]:
    """
    Parse an endpoint string like 'data_utils.py:load_data'
    or '/usr/lib/python3.10/csv.py:csv'
    or 'PROJECT/data/test_project/data_utils.py:load_data'.
    Returns (file_or_abs, name).
    """
    if not isinstance(ep, str) or ":" not in ep:
        return ep, ""
    file_part, name = ep.rsplit(":", 1)
    # If looks external weird relative into /usr/, normalize
    if "/usr/" in file_part and not file_part.startswith("/usr/"):
        file_part = normalize_external_path(file_part)
    return file_part, name


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# -----------------------------
# ID scheme
# -----------------------------

def compute_symbol_id(sym: Dict[str, Any]) -> Optional[str]:
    """
    Build symbol ID as '<definitions[0].absolutePath>:<name>'.
    - Project paths have been normalized to 'PROJECT/...'.
    - External/stdlib remain absolute '/...'.
    Fallback: if no definitions, use 'PROJECT/<file>:<name>' for project symbols.
    """
    name = sym.get("name")
    if not isinstance(name, str):
        return None

    defs = sym.get("definitions") or []
    if defs and isinstance(defs, list) and isinstance(defs[0], dict):
        ap = defs[0].get("absolutePath")
        if isinstance(ap, str) and ap:
            return f"{ap}:{name}"

    # Fallback when no definitions (rare for imports/constants)
    file_rel = sym.get("file")
    if isinstance(file_rel, str) and file_rel:
        return f"{PROJECT_TOKEN}/{file_rel}:{name}"

    return None


def make_external_id(abs_path: str, name: str) -> str:
    """
    External/stdlib ID: '<absolute_path>:<name>'.
    """
    return f"{abs_path}:{name}"


# -----------------------------
# Index builders
# -----------------------------

def build_indices(pruned: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, str], str]]:
    """
    Returns:
      by_id     : id -> symbol dict (with 'id' assigned)
      by_file_name : (file_rel, name) -> id (to map project deps endpoints)
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    by_file_name: Dict[Tuple[str, str], str] = {}

    for sym in pruned.get("symbols", []):
        sid = compute_symbol_id(sym)
        if not sid:
            continue
        # attach id shallowly
        sym_copy = {"id": sid}
        sym_copy.update(sym) 
        sym_copy.setdefault("calls", [])
        sym_copy.setdefault("calledBy", [])
        by_id[sid] = sym_copy

        f = sym.get("file")
        n = sym.get("name")
        if isinstance(f, str) and isinstance(n, str):
            by_file_name[(f, n)] = sid

    return by_id, by_file_name


# -----------------------------
# Integration core
# -----------------------------

def integrate(pruned: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    """
    - Assign IDs using definitions[0].absolutePath + ':' + name (project keeps 'PROJECT/..', externals keep absolute).
    - Merge deps.function_edges into 'calls' and 'calledBy' using the same ID scheme.
    - Build an 'externals' registry for IDs that are not present in project symbols.
    """
    by_id, by_file_name = build_indices(pruned)
    externals: Dict[str, Dict[str, Any]] = {}

    def id_from_dep_endpoint(ep: str) -> Optional[str]:
        file_part, name = parse_dep_endpoint(ep)
        if not name:
            return None

        # Project-style endpoint: either 'PROJECT/..' or bare 'file.py'
        if file_part.startswith(PROJECT_TOKEN + "/"):
            # Project path already normalized; map back to symbol id by definitions if exists
            # Try to find the symbol whose id starts with this file_part and name
            # Or fall back to file/name index (strip PROJECT/)
            proj_rel = file_part[len(PROJECT_TOKEN) + 1 :]
            sid = by_file_name.get((proj_rel, name))
            if sid:
                return sid
            # Fallback: construct ID even if not found in index
            return f"{file_part}:{name}"

        # Bare relative (e.g., 'data_utils.py') – treat as project file key
        if not file_part.startswith("/"):
            sid = by_file_name.get((file_part, name))
            if sid:
                return sid
            # If not found, construct PROJECT-based fallback
            return f"{PROJECT_TOKEN}/{file_part}:{name}"

        # Absolute/external
        abs_norm = normalize_external_path(file_part)
        return make_external_id(abs_norm, name)

    # Wire dependencies
    for e in deps.get("function_edges", []):
        src_raw = e.get("src")
        dst_raw = e.get("dst")
        if not isinstance(src_raw, str) or not isinstance(dst_raw, str):
            continue

        src_id = id_from_dep_endpoint(src_raw)
        dst_id = id_from_dep_endpoint(dst_raw)
        if not src_id or not dst_id:
            continue

        # Ensure externals exist if not project symbol
        if src_id not in by_id and src_id not in externals:
            f, n = parse_dep_endpoint(src_raw)
            if f.startswith("/"):
                externals[src_id] = {"id": src_id, "absolutePath": normalize_external_path(f), "name": n}
        if dst_id not in by_id and dst_id not in externals:
            f, n = parse_dep_endpoint(dst_raw)
            if f.startswith("/"):
                externals[dst_id] = {"id": dst_id, "absolutePath": normalize_external_path(f), "name": n}

        # Attach edges if the target symbol is in-project
        if src_id in by_id:
            if dst_id not in by_id[src_id]["calls"]:
                by_id[src_id]["calls"].append(dst_id)
        if dst_id in by_id:
            if src_id not in by_id[dst_id]["calledBy"]:
                by_id[dst_id]["calledBy"].append(src_id)

    # Sort stable
    symbols_out = list(by_id.values())
    for s in symbols_out:
        s["calls"].sort()
        s["calledBy"].sort()

    result = {
        "projectRootToken": PROJECT_TOKEN,
        "repoRoot": pruned.get("repoRoot", ""),
        "symbols": sorted(symbols_out, key=lambda x: x["id"]),
        "externals": sorted(externals.values(), key=lambda x: x["id"]),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Integrate pruned dependency JSON into final structure.")
    parser.add_argument("--input-file", required=True, help="Pruned JSON file.")
    parser.add_argument("--deps-file", required=True, help="Dependencies JSON file.")
    parser.add_argument("--output-dir", help="Directory to store final JSON.")
    parser.add_argument("--output-name", default="final_integrated.json", help="Output filename.")
    args = parser.parse_args()

    in_file = Path(args.input_file).resolve()
    deps_file = Path(args.deps_file).resolve()

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = DEFAULT_OUT_ROOT.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / args.output_name

    # Load pruned and deps JSON
    with in_file.open("r", encoding="utf-8") as f:
        pruned_json = json.load(f)
    with deps_file.open("r", encoding="utf-8") as f:
        deps_json = json.load(f)

    # Integrate both
    final_json = integrate(pruned_json, deps_json)

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Saved integrated JSON → {out_file}")



if __name__ == "__main__":
    main()
