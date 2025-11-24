# -*- coding: utf-8 -*-
"""
Simplified Writer agent — for testing Gemini API connectivity.

This version only calls the model and saves its raw output.
It switches prompts based on the symbol 'kind' (Class vs Function).
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


# ---------------- Prompt Templates ----------------

def build_class_prompt(item):
    """Build a prompt specifically for Python Classes."""
    snippet = item.get("code_snippet", "")
    sid = item.get("id", "unknown")
    
    return (
        f"You are a technical writer documenting a Python **Class**.\n"
        f"Analyze the following class definition and produce a structured **Markdown** section.\n"
        f"\n"
        f"**Requirements:**\n"
        f"- Output **Markdown only**.\n"
        f"- Focus on the **responsibility** of the class and how it manages state.\n"
        f"- Structure the output as follows:\n"
        f"\n"
        f"### <Class Name>\n"
        f"**ID:** `{sid}`\n"
        f"**Type:** Class\n"
        f"\n"
        f"**Summary**:\n"
        f"  - A concise overview of what this class represents and its primary role.\n"
        f"\n"
        f"**Attributes**:\n"
        f"  - List key instance variables (self.var) or class variables.\n"
        f"  - Explain what each attribute stores.\n"
        f"\n"
        f"**Key Methods**:\n"
        f"  - Briefly summarize the most important methods (public APIs).\n"
        f"  - Group them logically if there are many (e.g., 'Initialization', 'Data Processing').\n"
        f"\n"
        f"**Inheritance**:\n"
        f"  - If it inherits from other classes, mention them and explain the relationship.\n"
        f"\n"
        f"**Usage Context**:\n"
        f"  - Explain when or why a developer would instantiate this class.\n"
        f"\n"
        f"Python code to analyze:\n"
        f"```python\n"
        f"{snippet}\n"
        f"```"
    )


def build_function_prompt(item):
    """Build a prompt specifically for Python Functions or Methods."""
    snippet = item.get("code_snippet", "")
    sid = item.get("id", "unknown")
    kind = item.get("kind", "Function")

    return (
        f"You are a technical writer documenting a Python **{kind}**.\n"
        f"Analyze the following code and produce a structured **Markdown** section.\n"
        f"\n"
        f"**Requirements:**\n"
        f"- Output **Markdown only**.\n"
        f"- Focus on the **step-by-step logic**, control flow, and data transformation.\n"
        f"- Structure the output as follows:\n"
        f"\n"
        f"### <Name>\n"
        f"**ID:** `{sid}`\n"
        f"**Type:** {kind}\n"
        f"**Signature:** `<def ... line>`\n"
        f"\n"
        f"**Purpose**:\n"
        f"  - Shortly explain what this function accomplishes.\n"
        f"\n"
        f"**Detailed Logic**:\n"
        f"  - Step-by-step walkthrough of the operation.\n"
        f"  - Explain key decisions (if/else), loops, and algorithm details.\n"
        f"\n"
        f"**Inputs & Outputs**:\n"
        f"  - **Args**: Parameters and their roles.\n"
        f"  - **Returns**: What is returned and its type.\n"
        f"\n"
        f"**Edge Cases**:\n"
        f"  - How does it handle None, empty lists, or exceptions?\n"
        f"\n"
        f"Python code to analyze:\n"
        f"```python\n"
        f"{snippet}\n"
        f"```"
    )


def get_prompt_by_kind(item):
    """Dispatch based on symbol kind."""
    kind = str(item.get("kind", "")).lower()
    
    # List of kinds that should be treated as Class structures
    class_kinds = {"class", "interface", "struct", "enum", "module"}
    
    if kind in class_kinds:
        return build_class_prompt(item)
    else:
        # Default to function prompt for Method, Function, Constructor, etc.
        return build_function_prompt(item)


def main():
    ap = argparse.ArgumentParser(description="Test Gemini Writer agent pipeline.")
    ap.add_argument("--input-file", required=True, help="Path to sorted snippets JSON.")
    ap.add_argument("--output-file", required=True, help="Path to save output.")
    ap.add_argument("--model", default="gemini-2.5-flash-lite", help="Model name.")
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
    
    # Fallback for old data format where snippets were separate
    snippets_list = data.get("snippets", [])
    snippets_map = {s.get("id"): s for s in snippets_list if isinstance(s.get("id"), str)}

    results = []
    
    print(f"[INFO] Processing {len(symbols)} symbols...")

    for sym in symbols:
        sid = sym.get("id")
        
        # 1. Try to get code from the symbol itself (New Format)
        code = sym.get("code_snippet")
        
        # 2. If not found, try to look up in the old snippets map
        if not code and sid in snippets_map:
            code = snippets_map[sid].get("code_snippet")
            
        if not code:
            continue

        # Prepare item for prompt generation
        item = {
            "id": sid, 
            "kind": sym.get("kind", "Function"), # Default to Function if kind is missing
            "code_snippet": code
        }
        
        # Generate prompt based on Kind
        prompt = get_prompt_by_kind(item)
        print('='*20)
        print(prompt)
        print('='*20)
        try:
            resp = model.generate_content(prompt)
            text = (resp.text or "").strip()
        except Exception as e:
            text = f"[ERROR calling model: {e}]"
            print(f"[WARN] Failed to generate for {sid}: {e}")

        # Save result with metadata
        results.append({
            "id": sid, 
            "file": sym.get("file", ""), 
            "kind": item["kind"],
            "raw": text
        })

    out = {"model": args.model, "count": len(results), "items": results}
    save_json(out, Path(args.output_file))
    print(f"[INFO] Wrote {len(results)} doc entries -> {args.output_file}")


if __name__ == "__main__":
    main()