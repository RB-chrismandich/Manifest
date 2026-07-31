#!/usr/bin/env python3
"""Drop one domain's claim from ~/.apm/apm.lock.yaml (T5.1, spec 674).

Extracted from apm_ungate_domain.sh's inline heredoc so the RETIRE path can call
it too. Reclaiming a domain's files is not enough on its own:
apm_ownership_report.sh reads the lockfile to decide whether APM still owns a
domain, so a lockfile still listing paths APM no longer has leaves the report
stuck on DOUBLE-CLAIMED after a successful rollback.

The same applies after the plugin cutover, for a different reason: once the
skills are deleted from ~/.claude/skills, every path the lockfile asserts is
gone, and apm_drift_report.sh would report them all MISSING on a healthy
machine. (Measured 2026-07-30: that report currently exits 0 with 2640 files
matching — the plan's "exits 1 with 13 MISSING today" is stale, but the
post-cutover exposure is real.)

Usage: apm_drop_domain_claim.py <lockfile> <domain>
Exit 0 on success or when there is nothing to drop; 1 on failure.
"""

import sys

import yaml

path, domain = sys.argv[1], sys.argv[2]
prefix = f".claude/{domain}"
try:
    data = yaml.safe_load(open(path)) or {}
except Exception:
    sys.exit(1)


def strip(entry):
    for key in ("deployed_files", "deployed_file_hashes"):
        val = entry.get(key)
        if isinstance(val, list):
            entry[key] = [v for v in val if not str(v).startswith(prefix)]
        elif isinstance(val, dict):
            entry[key] = {k: v for k, v in val.items() if not str(k).startswith(prefix)}
    return entry


deps = data.get("dependencies")
if isinstance(deps, list):
    # Drop a dependency entirely once it produces nothing for any domain;
    # a husk with empty lists still reads as "apm deployed something here".
    kept = []
    for dep in deps:
        if not isinstance(dep, dict):
            kept.append(dep)
            continue
        strip(dep)
        if dep.get("deployed_files"):
            kept.append(dep)
    data["dependencies"] = kept

depl = data.get("deployments")
if isinstance(depl, list):
    data["deployments"] = [
        d for d in depl
        if not (isinstance(d, dict) and str(d.get("value", "")).startswith(prefix))
    ]

with open(path, "w") as f:
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=True)
