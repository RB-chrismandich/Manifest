---
name: pass-cli
description: |
  Retrieve credentials (passwords, API keys, tokens, SSH keys, secrets) from Proton
  Pass via the `pass-cli` agent CLI. Use whenever a task needs a login/secret to
  access a tool, website, database, or API — or when the user mentions Proton Pass,
  pass-cli, a vault, or "get the credentials/password/token for X". Covers session
  setup with a Personal Access Token, the mandatory access-reason for reading items,
  vault/item discovery, and auto-recovery from an expired session.
---

# Retrieve Credentials with pass-cli (Proton Pass)

Fetch secrets on demand from Proton Pass using the official `pass-cli`. This skill is
the procedure for authenticating an agent session and reading items/fields.

This skill is backed by the `pass-cli` binary. The canonical instructions can always
be re-printed with `pass-cli agent instructions`.

## Security rules (read first)

- **The Personal Access Token (PAT) is supplied by the user at runtime.** Never
  hardcode, invent, commit, or store a PAT in files, skills, or memory. Pass it only
  via the `PROTON_PASS_PERSONAL_ACCESS_TOKEN` environment variable on the login line.
- **Every read/write of an item requires a reason.** Set `PROTON_PASS_AGENT_REASON`
  to a brief, honest description of why you need that item/field on the same command.
- **Don't echo secrets unnecessarily.** Retrieve the specific field you need
  (`--field <name>`) and use it for the task; avoid printing full item contents or
  pasting secrets into logs/PRs/chat.
- Use an **isolated session directory** so this agent's session can't collide with
  others.

## When to use

- A task requires logging into a tool/website/DB/API and the credential lives in
  Proton Pass.
- The user says "get the password / API key / token for X" or references a vault/item.
- A previously working pass-cli command starts failing with an auth error (re-auth).

## Procedure

### 1. Confirm the CLI is installed

```bash
pass-cli --version
```

If missing, see <https://protonpass.github.io/pass-cli/get-started/installation/> for
platform install steps, then re-check.

### 2. Ensure an active, isolated session

```bash
# Isolate this agent's session from any other pass-cli sessions
export PROTON_PASS_SESSION_DIR="/tmp/pass-agent-<unique-name>"

# Are we already logged in? (exit 0 + session details means yes)
pass-cli info
```

If `info` shows an expired/absent session, log in with the user-provided PAT:

```bash
# The PAT comes from the user — do NOT store it anywhere.
PROTON_PASS_PERSONAL_ACCESS_TOKEN="<paste-user-PAT-here>" pass-cli login
pass-cli info   # verify you are logged in
```

### 3. Verify access to resources

```bash
pass-cli vault list --output json    # vaults the agent can access
pass-cli share list --output json    # vaults + directly-shared items granted
```

If you cannot see the expected vaults, stop and report the exact error output to the
user rather than guessing.

### 4. Discover items

```bash
pass-cli item list --vault-name "<Name>" --output json   # items in one vault
pass-cli item list --output json                          # all accessible items
```

### 5. Read an item or a single field (REASON REQUIRED)

```bash
# Whole item
PROTON_PASS_AGENT_REASON="Brief why this item is accessed" pass-cli item view \
  --vault-name "Vault Name" --item-title "Item Title"

# Direct pass:// URI
PROTON_PASS_AGENT_REASON="..." pass-cli item view "pass://SHARE_ID/ITEM_ID"

# Just one field (preferred — least exposure)
PROTON_PASS_AGENT_REASON="..." pass-cli item view \
  --vault-name "Vault" --item-title "DB" --field password
```

**Commands that require `PROTON_PASS_AGENT_REASON`:** `item view`, `item create*`
(e.g. `item create login`, `item create ssh-key`), `item update`, `item trash`,
`item untrash`, `vault update`.

## Session & connection health

```bash
pass-cli info    # account type + session details
pass-cli test    # verify connectivity to the Proton Pass API
```

## Auto-recovery from a dropped session

Before any pass-cli command in a long task, re-check `pass-cli info`. If a command
fails with an authentication error:

1. `pass-cli logout --force`     # clear the stale session
2. Re-run the login from step 2 (PAT via env var)
3. `pass-cli info`               # confirm logged in
4. Retry the original command

If any command fails, read the full output (error message, exit code, hints —
auth failure, permission denied, invalid params) before retrying.

## Quick reference

```bash
pass-cli agent instructions                            # re-print these instructions
pass-cli login                                         # authenticate with PAT from env
pass-cli logout [--force]                              # end session (force if logout errors)
pass-cli vault list --output json                      # list vaults
pass-cli share list --output json                      # list vaults + shared items
pass-cli item list --vault-name <NAME> --output json   # list items in a vault
PROTON_PASS_AGENT_REASON="..." pass-cli item view \
  --vault-name <VAULT> --item-title <TITLE> [--field <FIELD>]   # read item/field
```

Full docs: <https://protonpass.github.io/pass-cli/>
