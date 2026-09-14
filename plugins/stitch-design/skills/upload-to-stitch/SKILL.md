---
name: upload-to-stitch
description: Use when an authorized local DESIGN.md or Markdown document must be uploaded to a Stitch project.
---

# Upload-to-Stitch

Upload an authorized local `DESIGN.md` or Markdown document only through the
policy-controlled `mcp__stitch_upload_design_md` Stitch tool. The policy binds
the approved task digest, project, and exact document content to one mutation,
then requires matching post-mutation readback. The bundled Python script is
retired and deliberately fails closed.

## When to use

- An approved task names a Stitch project and a local `DESIGN.md` or Markdown
  document to upload.
- The document's exact content and canonical
  `sha256:<64 lowercase hexadecimal characters>` input hash are approved.

This skill does not upload images, mockups, binary assets, or HTML. No
policy-controlled MCP mutation exists for those asset types.

## Required OMP preflight

Before any mutation, confirm that this is an OMP host with the OMP UI-delivery
policy extension loaded. Invoke `ui_delivery_status` for the approved task and
require a successful response before using any Stitch MCP tool. Its approved
authorization and policy-extension state are the precondition for every later
step; an absent tool, error, unavailable extension, or unapproved result means
stop without a mutation.

On Claude, Cursor, Gemini, or any other non-OMP host, upload-to-stitch is
unavailable even when a Stitch MCP server is configured. Stop; do not invoke
`list_projects`, `mcp__stitch_upload_design_md`, or any other Stitch MCP tool.

## Workflow

### 1. Identify the target project

Only after the required OMP preflight, use `list_projects` to find the approved
`projectId`. Project listing discovers a target; it is not mutation readback.

### 2. Confirm the authorized document

Accept only `DESIGN.md` or another Markdown document. Confirm the approved
project, external task digest, exact local text, and canonical input hash
before dispatching a mutation. Do not derive content from an unapproved path
or change even whitespace after approval.

### 3. Dispatch the one authorized upload

Call `mcp__stitch_upload_design_md` with precisely the approved project and
document content. Do not use `run_command`, call the retired Python script,
substitute different content, or retry. Policy rejects a missing or changed
digest, wrong project, changed content, and every consumed one-shot grant.

### 4. Reconcile by readback

After the successful mutation result, dispatch the approved readback tool and
wait for that exact result. A read dispatched before the mutation result, or a
concurrent unrelated read, cannot reconcile the upload. Compare its approved
projection with the mutation result and the authorized document content.

## Supported document type

| Extension | MIME Type |
|:---|:---|
| `.md`, including `DESIGN.md` | `text/markdown` |

The approved tool input determines the document content; do not infer or alter
it from an unapproved local path.

## Example

For an approval naming project `project-42` and `DESIGN.md`, submit the
approved text to `mcp__stitch_upload_design_md` once. After its success result,
use the pre-authorized readback for `project-42` and reconcile the returned
projection to that result and the approved document.

## Error handling

| Situation | Required action |
|:---|:---|
| The requested asset is not Markdown | Stop; this MCP mutation cannot upload it. |
| The task digest, project, exact text, or input hash differs from approval | Stop; obtain new authorization before any mutation. |
| The mutation rejects, fails, or times out | Treat its outcome as unknown; do not retry automatically. |
| Readback does not match | Report the discrepancy and do not make another mutation. |

## Authorization contract

Approval names the project, document, and content hash. Make one upload attempt
only. Every reported success requires its authorized readback and reconciliation.
