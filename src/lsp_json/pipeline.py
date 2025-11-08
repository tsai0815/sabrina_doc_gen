import argparse
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable  # use current python interpreter
DEFAULT_OUT_ROOT = Path("data/lsp_json_outputs")
SHOW_ABS_PATH = False

def run(cmd: list[str]):
    """
    Execute a command and print it in readable form.
    - By default, prints relative paths (shorter, cleaner output).
    - If SHOW_ABS_PATH is True, prints absolute paths instead.
    """
    if SHOW_ABS_PATH:
        # Print command as-is with absolute paths
        print("[RUN]", " ".join(cmd))
    else:
        # Print relative paths instead of absolute ones when possible
        cwd = Path.cwd()
        rel_cmd = []
        for arg in cmd:
            try:
                p = Path(arg)
                # Convert absolute paths under current working dir to relative
                if p.is_absolute() and cwd in p.parents:
                    rel_cmd.append(str(p.relative_to(cwd)))
                else:
                    rel_cmd.append(arg)
            except Exception:
                # Non-path argument, keep as-is
                rel_cmd.append(arg)
        print("[RUN]", " ".join(rel_cmd))

    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Run LSP JSON pipeline.")
    parser.add_argument("--input", required=True, help="Source project directory to analyze.")
    # still optional; if user gives one, we use it directly
    parser.add_argument("--output", help="Directory to store all generated JSON files.")
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()

    if args.output:
        # user specified output explicitly
        output_dir = Path(args.output).resolve()
    else:
        # name output dir by input folder name
        input_name = input_dir.name  # e.g. "foo" from ".../foo"
        output_dir = (DEFAULT_OUT_ROOT / input_name).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    per_file_json = output_dir / "00_per_file.json"
    per_func_json = output_dir / "01_per_func.json"
    deps_json = output_dir / "02_deps.json"
    pruned_json = output_dir / "03_pruned.json"
    final_json = output_dir / "04_final_integrated.json"

    # 1. per-file
    run([
        PYTHON, "src/lsp_json/lsp_per_file.py",
        "--input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--output-name", per_file_json.name,
    ])

    # 2. per-file -> per-func
    run([
        PYTHON, "src/lsp_json/per_file2per_func.py",
        "--input-file", str(per_file_json),
        "--output-dir", str(output_dir),
        "--output-name", per_func_json.name,
    ])

    # 3. deps
    run([
        PYTHON, "src/lsp_json/lsp_build_deps.py",
        "--input-file", str(per_file_json),
        "--output-dir", str(output_dir),
        "--output-name", deps_json.name,
    ])

    # 4. prune
    run([
        PYTHON, "src/lsp_json/lsp_prune.py",
        "--input-file", str(per_func_json),
        "--output-dir", str(output_dir),
        "--output-name", pruned_json.name,
        "--repo-root", str(input_dir),   # Pass default repo root from pipeline
    ])

    # 5. integrate
    run([
        PYTHON, "src/lsp_json/integrate.py",
        "--input-file", str(pruned_json),
        "--deps-file", str(deps_json),     
        "--output-dir", str(output_dir),
        "--output-name", final_json.name,
    ])

    print("Pipeline finished. Final file:", final_json)


if __name__ == "__main__":
    main()
