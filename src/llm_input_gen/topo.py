import json
import argparse
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, Any, List, Set

# ---------- helpers ----------

def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(obj: Dict[str, Any], p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def is_external(sym_id: str) -> bool:
    # External nodes are absolute-path based or explicitly marked 'external:/'
    return sym_id.startswith("/") or sym_id.startswith("external:/")

# ---------- topo sort core ----------

def topo_order(symbols: List[Dict[str, Any]], reverse: bool = False) -> List[str]:
    """
    Produce a topological order of in-project symbols using `calls` edges.
    - Nodes:   all in-project symbol IDs present in `symbols`.
    - Edges:   sid -> d for each d in symbol.calls if d is also in-project.
    - reverse: if True, return reverse topological order (high-level first).
    """
    ids: Set[str] = {s.get("id") for s in symbols if isinstance(s.get("id"), str) and not is_external(s["id"])}
    out_e = defaultdict(set)
    in_deg = {sid: 0 for sid in ids}

    for s in symbols:
        sid = s.get("id")
        if not isinstance(sid, str) or is_external(sid):
            continue
        for d in (s.get("calls") or []):
            if d in ids:
                if d not in out_e[sid]:
                    out_e[sid].add(d)
                    in_deg[d] += 1
        _ = out_e[sid]  # ensure key exists

    # Kahn's algorithm
    q = sorted([v for v, d in in_deg.items() if d == 0])
    order: List[str] = []
    while q:
        v = q.pop(0)
        order.append(v)
        for w in sorted(out_e.get(v, [])):
            in_deg[w] -= 1
            if in_deg[w] == 0:
                q.append(w)
        q.sort()

    # If cycles remain, append them in deterministic order
    remaining = sorted([v for v, d in in_deg.items() if d > 0 and v not in order])
    order.extend(remaining)

    return list(reversed(order)) if reverse else order

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Topologically sort symbols using calls/calledBy from final_integrated.json")
    ap.add_argument("--input-file", required=True, help="Path to final_integrated.json (output of integrate.py)")
    ap.add_argument("--output-file", required=True, help="Where to write sorted JSON")
    ap.add_argument("--reverse", action="store_true",
                    help="If set, produce reverse topological order (high-level first)")
    ap.add_argument("--keep-externals", action="store_true",
                    help="Append externals after topo-ordered project symbols (kept in original order)")
    args = ap.parse_args()

    data = load_json(Path(args.input_file))
    symbols = data.get("symbols", [])
    externals = data.get("externals", [])

    order = topo_order(symbols, reverse=True)
    pos = {sid: i for i, sid in enumerate(order)}

    # Reorder project symbols by topo index; keep stable tie-breaker by id
    proj_syms = [s for s in symbols if isinstance(s.get("id"), str) and not is_external(s["id"])]
    proj_syms_sorted = sorted(proj_syms, key=lambda s: (pos.get(s["id"], 10**9), s["id"]))

    if args.keep_externals:
        # Keep externals in original appearance order at the end
        final_syms = proj_syms_sorted + [s for s in symbols if is_external(s.get("id", ""))]
    else:
        final_syms = proj_syms_sorted  # drop externals from symbols list

    out = {
        "projectRootToken": data.get("projectRootToken", "PROJECT"),
        "repoRoot": data.get("repoRoot", ""),
        "symbols": final_syms,
        "externals": externals,  # always pass-through externals table for reference
        "meta": {
            "order": "topological" if not args.reverse else "reverse_topological",
            "node_count": len(final_syms),
        }
    }
    save_json(out, Path(args.output_file))
    print(f"[INFO] Wrote topo-sorted JSON → {args.output_file}")

if __name__ == "__main__":
    main()
