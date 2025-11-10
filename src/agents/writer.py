# -*- coding: utf-8 -*-
"""
Simplified Writer agent — for testing Gemini API connectivity.

This version only calls the model and saves its raw output.
It does NOT enforce JSON or structured output.
"""

import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(obj, p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prompt(item):
    """Build a prompt that asks the model to return a single Markdown section."""
    snippet = item.get("code_snippet", "")

    return (
        "You are to produce a self-contained **Markdown** section that explains the full logical flow "
        "of the following Python function.\n"
        "\n"
        "Requirements:\n"
        "- Output **Markdown only**\n"
        "- Focus on describing the function’s **step-by-step logic**, control flow, and how data moves through it.\n"
        "- Provide a clear explanation of the procedure, inputs, outputs, and decisions.\n"
        "- Use Markdown headings and lists to organize content.\n"
        "- Sections (omit a section if not applicable):\n"
        "  ### <function name>\n"
        "  **ID:** <the symbol id if provided, else infer from code>\n"
        "  **Signature:** <def ... line>\n"
        "  **Purpose**: Shortly and concisely explain what the function is intended to accomplish\n"
        "  **Detailed Flow**:\n"
        "    - Step-by-step explanation of key operations\n"
        "    - Explain conditional logic, loops, data transformations\n"
        "  **Inputs**: parameters and their roles\n"
        "  **Outputs**: what the function returns or modifies\n"
        "  **Interactions**: functions or modules it calls, and why\n"
        "  **Edge Cases**: describe how the function handles special or invalid inputs\n"
        "\n"
        "Python code to analyze:\n"
        "```python\n"
        f"{snippet}\n"
        "```"
    )


def main():
    ap = argparse.ArgumentParser(description="Test Gemini Writer agent pipeline.")
    ap.add_argument("--input-file", required=True, help="Path to sorted snippets JSON.")
    ap.add_argument("--output-file", required=True, help="Path to save output.")
    ap.add_argument("--model", default="gemini-1.5-flash", help="Model name.")
    args = ap.parse_args()

    # Load API key
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in environment or .env file.")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(args.model)

    data = load_json(Path(args.input_file))
    symbols = data.get("symbols", [])
    snippets = data.get("snippets", [])

    code_by_id = {s.get("id"): s for s in snippets if isinstance(s.get("id"), str)}

    results = []
    for sym in symbols:
        sid = sym.get("id")
        sn = code_by_id.get(sid)
        if not sn:
            continue
        item = {"id": sid, "code_snippet": sn.get("code_snippet", "")}
        prompt = build_prompt(item)

        try:
            resp = model.generate_content(prompt)
            text = (resp.text or "").strip()
        except Exception as e:
            text = f"[ERROR calling model: {e}]"

        results.append({"id": sid, "raw": text})

    out = {"model": args.model, "count": len(results), "items": results}
    save_json(out, Path(args.output_file))
    print(f"[INFO] Wrote {len(results)} raw entries → {args.output_file}")


if __name__ == "__main__":
    main()
