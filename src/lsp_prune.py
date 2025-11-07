import json
from pathlib import Path
from typing import Any, Dict, List
from collections import defaultdict

IN_PATH = Path("data/lsp_output/symbol_grouped.json")
OUT_PATH = Path("data/lsp_output/symbol_grouped_pruned.json")

PROJECT_ROOT_TOKEN = "PROJECT"

def normalize_path(abs_path: str, repo_root: Path) -> str:
    """
    Replace repo_root with PROJECT_ROOT_TOKEN in absolute paths.
    If the path is outside the repo (third-party), keep the original absolute path.
    """
    try:
        abs_p = Path(abs_path).resolve()
        if repo_root in abs_p.parents or abs_p == repo_root:
            rel = abs_p.relative_to(repo_root)
            return f"{PROJECT_ROOT_TOKEN}/{rel.as_posix()}"
        else:
            return abs_path  # external path
    except Exception:
        return abs_path


def prune_references(refs: List[Dict[str, Any]], repo_root: Path) -> List[Dict[str, Any]]:
    """
    Keep only absolutePath and normalize it.
    Then count how many times each path appears.
    """
    counter: Dict[str, int] = defaultdict(int)
    for r in refs:
        abs_path = r.get("absolutePath")
        if isinstance(abs_path, str):
            norm = normalize_path(abs_path, repo_root)
            counter[norm] += 1

    pruned = [{"absolutePath": path, "count": count} for path, count in counter.items()]
    return sorted(pruned, key=lambda x: x["absolutePath"])


def prune_definitions(defs: List[Dict[str, Any]], repo_root: Path) -> List[Dict[str, Any]]:
    """Keep only absolutePath and normalize it."""
    seen = set()
    pruned = []
    for d in defs:
        abs_path = d.get("absolutePath")
        if isinstance(abs_path, str):
            norm = normalize_path(abs_path, repo_root)
            if norm not in seen:
                seen.add(norm)
                pruned.append({"absolutePath": norm})
    return pruned


def prune_hover(hv_list: Any) -> Any:
    """Remove 'range' from hover info."""
    if isinstance(hv_list, list):
        pruned = []
        for hv in hv_list:
            if isinstance(hv, dict):
                hv.pop("range", None)
            pruned.append(hv)
        return pruned
    elif isinstance(hv_list, dict):
        hv_list.pop("range", None)
        return hv_list
    else:
        return hv_list


def detect_repo_root(data: Dict[str, Any]) -> Path:
    """
    Detect the absolute project root by finding the deepest common directory
    that still contains all internal source files.
    """
    abs_paths = []

    # Collect all absolute paths from references and definitions
    for sym in data.get("symbols", []):
        for ref in sym.get("references", []):
            if "absolutePath" in ref:
                abs_paths.append(Path(ref["absolutePath"]).resolve())
        for d in sym.get("definitions", []):
            if "absolutePath" in d:
                abs_paths.append(Path(d["absolutePath"]).resolve())

    # Fallback if none found
    if not abs_paths:
        print("[WARN] No absolutePath found; using current directory as project root.")
        return Path.cwd().resolve()

    # Step 1: take common path among all absolute paths
    common_path = Path(abs_paths[0])
    for p in abs_paths[1:]:
        common_path = Path(*[a for a, b in zip(common_path.parts, p.parts) if a == b])
        if common_path == Path("/"):
            # stop early if we reach filesystem root
            break

    # Step 2: if result is too shallow (e.g. "/"), try to locate 'data/test_project' automatically
    # this ensures absolute project root for your case
    possible_root = None
    for p in abs_paths:
        parts = p.parts
        for i in range(len(parts), 0, -1):
            sub = Path(*parts[:i])
            if (sub / "data").exists() and (sub / "src").exists():
                possible_root = sub
                break
        if possible_root:
            break

    repo_root = possible_root if possible_root else common_path
    return repo_root.resolve()



def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))

    repo_root = detect_repo_root(data)
    print(f"[INFO] Detected project root: {repo_root}")

    symbols_out = []
    for sym in data.get("symbols", []):
        new_sym = {
            "file": sym.get("file"),
            "name": sym.get("name"),
            "references": prune_references(sym.get("references", []), repo_root),
            "definitions": prune_definitions(sym.get("definitions", []), repo_root),
            "hover": prune_hover(sym.get("hover")),
        }
        symbols_out.append(new_sym)

    result = {"symbols": symbols_out}
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[INFO] Wrote pruned symbol JSON → {OUT_PATH}")


if __name__ == "__main__":
    main()
