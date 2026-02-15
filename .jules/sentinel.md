## 2026-02-11 - TOCTOU in File Creation
**Vulnerability:** Found insecure file creation pattern (`touch file; chmod 600 file`) in `bootstrap/lib/auth.sh` exposing API keys during the window between creation and permission change.
**Learning:** Shell scripts often default to `umask 022` or similar, making new files readable by others before `chmod` runs. This race condition (Time-of-Check-to-Time-of-Use) is critical for secrets.
**Prevention:** Use atomic creation with restricted permissions: `(umask 077; echo 'content' > file)`.
