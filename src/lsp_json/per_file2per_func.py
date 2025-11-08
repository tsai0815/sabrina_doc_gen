import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict
import argparse


DEFAULT_OUT_ROOT = Path("data/lsp_json_outputs")


def merge_symbols_by_file_and_name(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge all symbols across files by their *definition file* and name.
    The output 'file' field will always be the file where the symbol is defined.
    For range/selectionRange, we keep the ones from the defining occurrence.
    """
    # Collect raw occurrences
    raw: List[Tuple[str, Dict[str, Any]]] = []  # (file_name_in_this_doc, symbol_dict)
    for file_entry in data.get("files", []):
        file_name = file_entry.get("file")
        for sym in file_entry.get("symbols", []):
            raw.append((file_name, sym))

    # Helper: pick candidate definition file from one occurrence
    def candidate_def_file(sym: Dict[str, Any], fallback_file: str) -> str:
        defs = sym.get("definitions") or []
        if defs and isinstance(defs, list) and isinstance(defs[0], dict):
            # Prefer relativePath if available; else absolutePath; else fallback
            rel = defs[0].get("relativePath")
            if isinstance(rel, str) and rel:
                return rel
            ap = defs[0].get("absolutePath")
            if isinstance(ap, str) and ap:
                return ap
        return fallback_file

    # First pass: determine canonical (def_file, name) for grouping
    groups: DefaultDict[Tuple[str, str], List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    for file_name, sym in raw:
        name = sym.get("name")
        if not isinstance(name, str):
            continue
        def_file = candidate_def_file(sym, file_name)
        groups[(def_file, name)].append((file_name, sym))

    merged_result: List[Dict[str, Any]] = []

    # Second pass: merge each group; set file to canonical def file
    for (def_file, name), occs in groups.items():
        all_refs: List[Dict[str, Any]] = []
        all_defs: List[Dict[str, Any]] = []
        all_hover: List[Any] = []

        # Prefer range/selectionRange from the occurrence that lives in the definition file
        def_range = None
        def_sel_range = None

        for file_name, sym in occs:
            # accumulate references/definitions
            refs = sym.get("references") or []
            defs = sym.get("definitions") or []
            all_refs.extend(refs)
            all_defs.extend(defs)

            hv = sym.get("hover")
            if hv and hv not in all_hover:
                all_hover.append(hv)

            # capture range from defining occurrence
            if def_range is None and file_name == def_file:
                if "range" in sym:
                    def_range = sym.get("range")
                if "selectionRange" in sym:
                    def_sel_range = sym.get("selectionRange")

        merged_result.append({
            "file": def_file,                 # always the definition file
            "name": name,
            "range": def_range,               # may be None if not present
            "selectionRange": def_sel_range,  # may be None if not present
            "references": all_refs,
            "definitions": all_defs,
            "hover": all_hover
        })

    return {"symbols": merged_result}



def main():
    """Main entry: read the original LSP JSON, merge symbols, and save grouped output."""
    
    parser = argparse.ArgumentParser(description="Convert per-file JSON to per-function JSON.")
    parser.add_argument("--input-file", required=True, help="Per-file JSON produced by lsp_per_file.py.")
    parser.add_argument("--output-dir", help="Directory to store output JSON.")
    parser.add_argument("--output-name", default="01_per_func.json", help="Output filename.")
    args = parser.parse_args()

    in_file = Path(args.input_file).resolve()
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = DEFAULT_OUT_ROOT.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / args.output_name

    with in_file.open("r", encoding="utf-8") as f:
        per_file_json = json.load(f)

    per_func_json = merge_symbols_by_file_and_name(per_file_json)

    with out_file.open("w", encoding="utf-8") as f:
        json.dump(per_func_json, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
