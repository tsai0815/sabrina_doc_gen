import json
import argparse
from pathlib import Path
from typing import List, Dict, Any


def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def save_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Combine LLM Markdown outputs (id+raw) into one DOCS.md in reverse order.")
    ap.add_argument("--input", required=True, help="Path to JSON file containing items[].id and items[].raw")
    ap.add_argument("--output", required=True, help="Path to output Markdown file")
    ap.add_argument("--title", default="Project Documentation", help="Top-level title for the Markdown document")
    args = ap.parse_args()

    data = load_json(Path(args.input))
    items: List[Dict[str, Any]] = data.get("items", [])

    if not items:
        print("[WARN] No items found in input JSON.")
        return

    # Reverse order
    items = list(reversed(items))

    parts: List[str] = [f"# {args.title}", ""]
    for it in items:
        sid = it.get("id", "")
        raw = (it.get("raw") or "").strip()

        if not raw:
            parts.append(f"### {sid}\n_Missing content._\n")
        else:
            parts.append(raw)

        parts.append("---")  # section separator

    result = "\n".join(parts)
    save_text(Path(args.output), result)
    print(f"[INFO] Combined {len(items)} sections in reverse order → {args.output}")


if __name__ == "__main__":
    main()