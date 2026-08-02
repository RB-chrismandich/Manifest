# Unified Hook Usage

The installer registers the same bundle-local normalizer independently in each
supported harness's own native hook target. Every registration passes an
explicit `--source`; source is never inferred from another harness's settings,
command text, or parent process.

```bash
scripts/install_all.py --unified --handler "/path/to/handler.py" --name my-hook
scripts/install_all.py --unified --handler "/path/to/handler.py" --name my-hook --dry-run
```

Each inserted entry carries a `manifest_owner` marker. Removal only deletes the
matching owned entry and preserves unrelated user settings and hooks.

Unsupported events or harnesses return a structured `degraded` result through
`runtime.tool_config.hook_support`; they are never reported as installed.

The normalizer converts native payloads into a canonical event containing
`event_type`, `source`, `session_id`, `cwd`, `tool_name`, `tool_input`,
`timestamp`, and `raw_payload`. Handler failure is fail-open unless the handler
returns an explicit deny response.
