# Running the Sabrina Doc Gen Pipeline

This guide details how to build the Docker environment and execute the documentation generation pipeline.

## 1. Prerequisites

Ensure the following are installed on your system:
* **Docker Engine**
* **NVIDIA Container Toolkit** (Required for `--gpus all` support)

## 2. Build the Docker Image

Run the following command from the project root directory to build the image:

```bash
docker build -t sabrina-doc-gen:gpu .
```

## 3. Configuration (API Key)

To generate docstrings using the Writer Agent, you must provide a Google Gemini API key. You can pass this key directly in the command line or store it in an environment variable on your host machine.

## 4. Execute the Standard Pipeline

The pipeline runs inside a Docker container. You must mount your local `data` directory to the container so it can access your source code and write the output files.

### Basic Command

```bash
docker run --rm -it --gpus all \
  -v "$(pwd)/data:/app/data" \
  -e GEMINI_API_KEY="your_actual_api_key_here" \
  sabrina-doc-gen:gpu \
  python3 src/pipeline.py \
  --input data/test_project
```

### Command Breakdown

| Flag / Argument | Description |
| :--- | :--- |
| `--rm` | Automatically remove the container after execution. |
| `-it` | Run in interactive mode (useful for seeing logs). |
| `--gpus all` | Grants the container access to GPU resources. |
| `-v "$(pwd)/data:/app/data"` | **Critical**: Mounts your local `data` folder to `/app/data` inside the container. |
| `-e GEMINI_API_KEY="..."` | Passes your API key into the container environment. |
| `python3 src/pipeline.py` | The entry point script for the analysis pipeline. |
| `--input <path>` | The path to the project you want to analyze (relative to the container's `/app` directory). |

### Output

After execution, the results will be generated in `data/lsp_json_outputs/<project_name>/`.
The final structured documentation can be found at:

`data/lsp_json_outputs/<project_name>/doc_full.md`

---

## 5. Enter the Container (Interactive Shell)

If you need to debug, inspect files, or run scripts manually from inside the environment, you can launch an interactive Bash shell:

```bash
docker run --rm -it --gpus all \
  -v "$(pwd)/data:/app/data" \
  -e GEMINI_API_KEY="your_actual_api_key_here" \
  sabrina-doc-gen:gpu \
  /bin/bash
```

Once inside, your source code and data are located in `/app/data`. Type `exit` to leave the container.

---

## 6. Running Agents Manually

If you have already run the pipeline and generated the intermediate JSON files (specifically `06_sorted_snippets.json`), you can re-run the **Writer** or **Assembler** agents without re-doing the LSP analysis.

### Step A: Run the Writer Agent (Generate Docstrings)
This reads the code snippets and calls the LLM to generate documentation.

```bash
docker run --rm -it --gpus all \
  -v "$(pwd)/data:/app/data" \
  -e GEMINI_API_KEY="your_actual_api_key_here" \
  sabrina-doc-gen:gpu \
  python3 src/agents/writer.py \
  --input-file data/lsp_json_outputs/test_project/06_sorted_snippets.json \
  --output-file data/lsp_json_outputs/test_project/07_docstrings.json \
  --model gemini-1.5-flash
```

### Step B: Run the Assembler (Generate Markdown)
This takes the generated docstrings and groups them into a structured Markdown file.

```bash
docker run --rm -it --gpus all \
  -v "$(pwd)/data:/app/data" \
  sabrina-doc-gen:gpu \
  python3 src/agents/structured_md_assembler.py \
  --input data/lsp_json_outputs/test_project/07_docstrings.json \
  --output data/lsp_json_outputs/test_project/doc_full.md \
  --title "My Project Documentation"
```