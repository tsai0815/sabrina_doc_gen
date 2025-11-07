import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict
import argparse


DEFAULT_OUT_ROOT = Path("data/lsp_json_outputs")
    

def merge_symbols_by_file_and_name(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge all symbols from all files, grouped by (file, symbol name).
    This avoids merging unrelated functions that share the same name in different files.
    """
    grouped: DefaultDict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    # Iterate over every file in LSP output
    for file_entry in data.get("files", []):
        file_name = file_entry.get("file")
        for sym in file_entry.get("symbols", []):
            name = sym.get("name")
            if not isinstance(name, str):
                continue
            key = (file_name, name)
            grouped[key].append(sym)

    merged_result: List[Dict[str, Any]] = []

    # Merge all occurrences of the same (file, name)
    for (file_name, name), occurrences in grouped.items():
        all_refs: List[Dict[str, Any]] = []
        all_defs: List[Dict[str, Any]] = []
        all_hover: List[Any] = []

        for occ in occurrences:
            # Collect references and definitions from all occurrences
            all_refs.extend(occ.get("references", []))
            all_defs.extend(occ.get("definitions", []))

            hv = occ.get("hover")
            if hv and hv not in all_hover:
                all_hover.append(hv)

        merged_result.append({
            "file": file_name,
            "name": name,
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
