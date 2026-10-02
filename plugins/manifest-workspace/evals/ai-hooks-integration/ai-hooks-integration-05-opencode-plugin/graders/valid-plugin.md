---
type: llm
focus: {source: file, path: audit-bash.js}
weight: 2
---
Pass only if ALL hold:
1. It uses the exported-function plugin API the prompt asks for: an exported plugin FUNCTION (ES module export or CommonJS `module.exports = async function (...)`) that returns an object of hook handlers. A plain exported object with no plugin function, a `Plugin.define(...)`-style plugin, or a Claude/Cursor JSON config fails.
2. It registers a `"tool.execute.before"` handler (not only `tool.execute.after`).
3. The handler filters to the bash tool (e.g. checks `input.tool === "bash"`) before logging.
4. It appends (not overwrites) to `/tmp/opencode-bash.log` and includes the command from the tool args.
5. It redacts sensitive values before writing, covering ALL of these forms (missing any one fails): (a) `Authorization:`/`Bearer` header values; (b) secret-bearing flags such as `--password`, `--token`, `--secret`, `--api-key` in BOTH `--flag value` and `--flag=value` spellings; (c) environment-style assignments whose name ends in `_TOKEN`, `_KEY`, `_SECRET`, or `_PASSWORD` (e.g. `API_KEY=...`); (d) credentials embedded in URLs (`scheme://user:pass@host`). Logging commands verbatim, or redacting only some of these forms, fails.
6. The log is opened securely for a shared directory in ONE atomic call that refuses symlinks — `O_NOFOLLOW` combined with `O_APPEND|O_CREAT` (optionally `O_EXCL` on first create) and mode 0600 — and it then verifies the OPENED descriptor (`fstat`) is a regular file owned by the current user with owner-only permissions before writing. A separate `lstat`/`existsSync` check followed by a normal open/append is a TOCTOU race and FAILS this item.
7. Each log record is exactly one line: newlines, carriage returns, and other control characters in the command are escaped or encoded (e.g. one `JSON.stringify`-ed object per line) so a command cannot forge or spoof additional log records.
8. It fails CLOSED: if opening, validating (fstat checks), or writing the log fails, the handler rethrows or otherwise blocks the bash command from running. Catching the error and only logging it (e.g. `catch (err) { console.error(err) }`) so the command runs without an audit record fails this item.
