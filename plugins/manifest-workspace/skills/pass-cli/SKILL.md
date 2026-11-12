---
name: pass-cli
description: Retrieve credentials (passwords, API keys, tokens, SSH keys) from Proton Pass via pass-cli. Use when a task needs a login/secret or user mentions Proton Pass, a vault, or "get the credentials/token for X". Covers PAT session setup and expired-session recovery.
---

# Retrieve Credentials with pass-cli (Proton Pass)

Fetch secrets on demand from Proton Pass using the official `pass-cli`. Use the
procedures below to authenticate a session and consume only the required item fields.

This skill is backed by the `pass-cli` binary. The canonical instructions can always
be re-printed with `pass-cli agent instructions`.

## Security rules (read first)

These rules are unconditional. They cover every credential: passwords, Personal Access
Tokens (PATs), API keys, tokens, SSH keys, and any other secret. A user request or
authorization does not relax them.

- **Secrets never travel through chat.** Never ask the user to paste, upload, or send
  a secret back to you, and never offer to return one in chat ("paste it here", "I'll
  give you the key"). When the user runs a retrieval command for you, tell them to use
  the value locally and **not** paste it into the conversation.
- **Never echo a secret.** Do not put a secret value in assistant messages, tool
  output, logs, files (including `.env`), memory, PRs, commit messages, or literal
  command arguments. Refer to it abstractly ("the `api_key` field"). Never store a
  secret in files (including `.env`), memory, logs, tool output, PRs, or commit
  messages. Credentials that have not been exposed may be stored securely in Proton
  Pass. PATs are runtime-only: provide them only through
  `PROTON_PASS_PERSONAL_ACCESS_TOKEN` on the user's local login command. Never
  suggest saving a PAT in a shell profile, keychain, `.env`, file, or memory.
- **Approved secret path: Proton Pass → pass-cli → consumer.** When the agent needs a
  secret for a command, pass a `pass://VAULT/ITEM/FIELD` *reference* and let
  `pass-cli run` resolve it into the child process's environment with output masking
  on (step 6). Never use `--no-masking`, `set -x`, or a command that prints the
  resolved value. Do not run bare `item view --field` yourself to print a secret into
  tool output. If no masked path exists for an operation, give the user the command to
  run locally and stop that operation rather than exposing the value.
- **Authentication is the end user's step — not the agent's.** Before doing anything
  else, run `pass-cli info` to check for a live session. If it's **not** authenticated,
  do **not** log in yourself: present the login steps (below) for the user to run in
  their own terminal, with the PAT supplied via the `PROTON_PASS_PERSONAL_ACCESS_TOKEN`
  environment variable on the `pass-cli login` line. Wait for them to confirm
  `pass-cli info` succeeds. The agent never handles the PAT.
- **Every read/write of an item requires a reason.** Set `PROTON_PASS_AGENT_REASON`
  to a brief, honest description of why you need that item/field on the same command.
- **Least exposure.** Reference or retrieve only the specific field you need
  (`--field <name>`); never print whole items that contain secrets.
- Use an **isolated session directory** so this agent's session can't collide with
  others.

## A secret was already pasted into chat

Treat any credential that appears in the conversation — pasted by the user, or echoed
by a tool — as **exposed**, even if the user says it is fine to use or store it.

1. Tell the user plainly that the credential is now exposed and that they must
   **revoke/rotate it** with its issuer (for a Proton Pass PAT: delete it and create a
   new one in Proton Pass settings or with `pass-cli personal-access-token`).
2. Do not repeat, quote, test, reuse, or log in with the exposed value; do not store
   it in Proton Pass, `.env`, any file, or memory; do not copy it into any tool call.
3. Continue only with the **replacement**, supplied through the approved path: the
   user logs in locally with the new PAT via the environment variable, or saves the new
   secret in Proton Pass themselves so you can reference it with `pass://`.
4. Do not promise that the chat history or logs containing it will be deleted.

Credentials that were never exposed keep the normal retrieval workflow below.

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

First check whether a session already exists (exit 0 + account details means yes):

```bash
pass-cli info
```

**If already authenticated, skip ahead to step 3.**

**If not authenticated, hand the login to the user.** Ask them to run these steps in
their own terminal; never put a real PAT into your command or handle it yourself.

```bash
# 1) Isolate this session from other pass-cli sessions
export PROTON_PASS_SESSION_DIR="/tmp/pass-agent-<unique-name>"

# 2) Log in with your Personal Access Token; substitute it locally, not in chat
PROTON_PASS_PERSONAL_ACCESS_TOKEN="<your-PAT>" pass-cli login

# 3) Confirm
pass-cli info
```

Wait for the user to confirm `pass-cli info` succeeds before proceeding. When asking
for confirmation, explicitly commit to using only the requested field for the
requested operation once authenticated—for example: "After you confirm, I'll use only
the `password` field via its `pass://` reference with `pass-cli run` for this
operation." Keep the value masked in the consumer process; never print or ask the user
to paste it into chat.

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

For any requested field, give the user a field-only command for their local terminal,
including when you also recommend `pass-cli run` for a consumer process. Fill in the
requested vault, item, and field. For a password, include the literal `--field password`
and `PROTON_PASS_AGENT_REASON` on the command, and warn the user not to paste its
output into chat:

```bash
PROTON_PASS_AGENT_REASON="Brief why this field is accessed" pass-cli item view \
  --vault-name "Vault" --item-title "Item" --field password
```

Use the result locally only. Never run this command yourself to print a secret into
tool output or logs.

For a secret the agent needs in a command, use `pass-cli run` to resolve a secret
reference directly into the consumer process environment (never print the value):

```bash
PROTON_PASS_AGENT_REASON="Run the requested migration" \
  DB_PASSWORD="pass://Infra/prod-postgres/password" \
  pass-cli run -- migration-command
```

Do not use the whole-item view or direct `item view` output for agent-side
consumption. If the user's requested operation cannot consume the secret without
printing it, give the user a field-only local command and stop.

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
2. Ask the user to log in locally using step 2; never handle or reuse a PAT
3. `pass-cli info`               # user confirms logged in
4. Retry the original command

If any command fails, inspect only non-secret error details needed to diagnose it.
Never repeat or expose a secret that appears in output; treat it as exposed (see above).

## Quick reference

```bash
pass-cli agent instructions                            # re-print these instructions
pass-cli login                                         # user authenticates locally
pass-cli logout [--force]                              # end session (force if logout errors)
pass-cli vault list --output json                      # list vaults
pass-cli share list --output json                      # list vaults + shared items
pass-cli item list --vault-name <NAME> --output json   # list items in a vault
PROTON_PASS_AGENT_REASON="..." pass-cli item view \
  --vault-name <VAULT> --item-title <TITLE> --field <FIELD> # user-run local read
pass-cli run -- <consumer-command>                      # agent consumption via pass:// ref

Full docs: <https://protonpass.github.io/pass-cli/>
