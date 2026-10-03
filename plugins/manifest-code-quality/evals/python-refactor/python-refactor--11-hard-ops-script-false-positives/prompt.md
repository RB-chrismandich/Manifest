---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Quick look before I merge this ops script?

```python
# ops/maintenance.py
import logging
import subprocess

logger = logging.getLogger(__name__)

# password = "<REDACTED>"  -- old creds, rotated 2019, kept here for incident history only
ARCHIVE_ROOT = "/var/snapshots"


def purge_old_snapshots(retention_days):
    """Called by POST /admin/purge with the request body's `days` field passed
    straight through as retention_days."""
    logger.info(f"SELECT * FROM audit_log WHERE age_days > {retention_days}")
    cmd = "find {}/daily -mtime +{} -delete".format(ARCHIVE_ROOT, retention_days)
    subprocess.run(cmd, shell=True)
```
