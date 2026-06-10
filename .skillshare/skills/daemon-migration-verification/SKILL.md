---
name: daemon-migration-verification
description: After retiring a daemon/proxy architecture and redeploying, verify the new state landed AND the old daemon is genuinely gone — automated teardown does not kill manually-started processes
---
# Daemon Migration Verification

When a change replaces a long-running daemon/proxy with a passive or on-demand model, the redeploy can succeed while the *old* daemon keeps running. Automated teardown (removing a launchd/systemd unit) does NOT kill a process someone started by hand. Verify both halves: the new state and the old process's actual death.

1. **Verify the new artifacts actually landed**, not just that deploy exited 0. Check each deployed surface explicitly: new skills/commands present in the target dir, hook registrations present in the settings file (parse the JSON and list the registered commands), scripts executable and runnable, config keys rewritten. Confirm symlinks are still symlinks, not replaced by real dirs.
2. **Hunt for the surviving old daemon.** `ps aux | grep <daemon-name>` for a live process, and check its port is actually free (`lsof -i :<port>` or `nc -z`). A redeploy that removes the launchd/systemd unit will leave a manually-started process alive and unsupervised — it won't respawn, but it won't die either.
3. **Distinguish "no respawn source" from "not running."** Confirm there is no launchd plist / systemd unit that will restart it (so a kill is permanent), separately from confirming the current process is dead.
4. **Verify teardown side-effects completed**, especially security-relevant ones the migration script was supposed to apply: storage directory permissions (e.g. `chmod 700` on a secrets/honeypot dir and its subdirs), removed shell-profile wrappers, deleted state files. Compare actual `stat` perms against the spec — a deploy that exited early can skip the lockdown step.
5. **Get explicit confirmation before killing a process or deleting state** — killing a daemon is an irreversible action on the user's machine. Present what you found (PID, command line, port, what it's still writing to) and the exact remediation commands, then wait for go-ahead.
6. **Identify leftover vestigial files** from the old install (databases, pid/log files, old config) and report them as harmless-but-cleanable rather than silently deleting — the user may want them for forensics.
7. **Record the root cause for next time:** note that the automated teardown can't kill manually-started daemons, so any machine that had the old install needs the same `ps`/port check — a redeploy alone is not sufficient.
