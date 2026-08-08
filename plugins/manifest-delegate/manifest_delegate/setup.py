"""manifest-delegate: setup."""

import concurrent.futures
import json
import sys

from . import readiness, registry


def cmd_setup(args, backends, user_config, services_disabled):
    if getattr(args, "enable_review_gate", False) or getattr(
        args, "disable_review_gate", False
    ):
        return readiness._cmd_setup_gate_toggle(args, user_config)

    targets = backends
    if getattr(args, "backend", None):
        entry = registry.resolve_backend(backends, args.backend)
        if entry is None:
            sys.stderr.write(
                "delegate: unknown backend {!r}; known backends: {}\n".format(
                    args.backend, ", ".join(b["id"] for b in backends)
                )
            )
            return 2
        targets = [entry]

    rows = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, len(targets))
    ) as pool:
        futures = [
            pool.submit(
                readiness.probe_backend_readiness, entry, user_config, services_disabled
            )
            for entry in targets
        ]
        for future in futures:
            rows.append(future.result())

    if args.json:
        print(json.dumps(rows))
        return 0

    print(f"{'backend':<12} {'state':<18} {'version':<9} fix")
    for row in rows:
        print(
            f"{row['backend']:<12} {row['state']:<18} "
            f"{row.get('version') or '—':<9} {row.get('fix') or '—'}"
        )
    return 0
