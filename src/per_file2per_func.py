import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, DefaultDict
from collections import defaultdict

# Input / Output paths
IN_PATH = Path("data/lsp_output/python_multilspy_output.json")
OUT_PATH = Path("data/lsp_output/symbol_grouped.json")


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
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    merged = merge_symbols_by_file_and_name(data)

    OUT_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[INFO] Wrote grouped symbol JSON → {OUT_PATH}")


if __name__ == "__main__":
    main()
