---
name: upload-to-stitch
description: Upload authorized local assets to Stitch and reconcile them by readback.
---

# Upload-to-Stitch

Upload local assets (images, mockups, HTML, and markdown files) only through the
policy-controlled `mcp__stitch_upload_design_md` Stitch tool. Its extension
binds the externally approved task digest, project, and exact content to the
single authorized mutation, then requires a matching post-mutation readback.
The bundled Python script is retired and deliberately fails closed.

## Steps

### 1. Identify Target Project

Use `list_projects` to find the correct `projectId`.


### 3. Dispatch the approved upload

Use `mcp__stitch_upload_design_md` with precisely the approved project and
content. Do not use `run_command`, call the retired Python script, substitute
different bytes, or retry: policy rejects a missing/changed digest, wrong
project, changed content, and every consumed one-shot grant.

After a successful mutation result, dispatch the approved readback tool and
wait for that exact readback result. A read dispatched before the mutation
result, or a concurrent unrelated read, cannot reconcile the upload.

### Supported File Types

| Extension | MIME Type |
|:---|:---|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.webp` | `image/webp` |
| `.html`, `.htm` | `text/html` |
| `.md` | `text/markdown` |

The approved tool input determines the content type; do not derive or alter it
from an unapproved local path.

## Authorized upload contract

Approval names the project, files, and content hashes. Make one upload attempt only. Failure or timeout is unknown until readback; never retry automatically. Read back every reported success and reconcile it to the approved hashes.
