---
name: upload-to-stitch
description: "Upload local assets (images, mockups, HTML, design markdown) to a Stitch project. ALWAYS use when visual assets or design docs need uploading, especially when direct MCP calls fail/truncate on base64 token limits."
allowed-tools:
  - "stitch*:*"
  - "Bash"
  - "Read"
  - "Write"
  - "web_fetch"
---

# Upload-to-Stitch

Upload local assets (images, mockups, HTML, and markdown files) to a Stitch project using the
provided upload script, which bypasses the MCP tool's base64 output token limits.

> [!NOTE]
> The AI model cannot upload files via MCP tools directly because the base64
> encoding of even a small file exceeds the model's output token limit (~16K
> tokens). This script reads the file and sends it directly over HTTP.

## Steps

### 1. Identify Target Project

Use `list_projects` to find the correct `projectId`.

### 2. Get the API Key

Require the secret through the `STITCH_API_KEY` environment variable. Never
read an assistant configuration or persist the key in a project file. The
optional `STITCH_API_URL` environment variable overrides the default
`https://stitch.googleapis.com` endpoint.

> [!IMPORTANT]
> If `STITCH_API_KEY` is absent, ask the user to provide it through their secure
> environment and stop. Do not echo the value or continue without it.

### 3. Run Upload Script

> [!WARNING]
> **Checkpoint — User Confirmation Required.**
> Before running the upload script, you **MUST** pause and present the file(s)
> to be uploaded (paths, sizes, and types) to the user and wait for explicit
> approval. Do **NOT** execute the upload script until the user confirms.

Use `run_command` to execute the Python script:

```bash
python3 <SKILL_DIR>/scripts/upload_to_stitch.py \
  --project-id <PROJECT_ID> \
  --file-path <PATH_TO_FILE> \
  [--api-url "${STITCH_API_URL:-https://stitch.googleapis.com}"] \
  [--title <SCREEN_TITLE>] \
  [--generated-by <GENERATED_BY>]
```

> [!TIP]
> **macOS / SSL Certificate Troubleshooting:**
> If the upload fails with `ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate`, this means your Python installation does not have root certificate authorities configured.
>
> The script automatically attempts to use the `certifi` package to load the CA bundle if it is installed in your python environment. If `certifi` is not installed, you can either install it (`pip install certifi`) or manually supply the `SSL_CERT_FILE` environment variable when running the script:
>
> ```bash
> SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())") python3 <SKILL_DIR>/scripts/upload_to_stitch.py \
>   --project-id <PROJECT_ID> \
>   --file-path <PATH_TO_FILE> \
>   [--api-url <STITCH_API_URL>] \
>   [--title <SCREEN_TITLE>] \
>   [--generated-by <GENERATED_BY>]
> ```

### Supported File Types

| Extension | MIME Type |
|:---|:---|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.webp` | `image/webp` |
| `.html`, `.htm` | `text/html` |
| `.md` | `text/markdown` |

The script auto-detects MIME type from the file extension.

### Script Options

- `--project-id`: **Required**. The Stitch project ID.
- `--file-path`: **Required**. Path to the local file to upload.
- `STITCH_API_KEY` (environment variable): **Required**. API key for Stitch authorization. The script reads this from the environment; there is no `--api-key` flag.
- `--api-url`: Optional. Base URL of the Stitch API. Defaults to `https://stitch.googleapis.com` (or `STITCH_API_URL`).
- `--title`: Optional. Title for the uploaded screen.
- `--generated-by`: Optional. Specify how the uploaded file was generated (e.g., 'stitch::extract-static-html' skill, 'Claude Code', 'Codex', 'Gemini' etc.).
