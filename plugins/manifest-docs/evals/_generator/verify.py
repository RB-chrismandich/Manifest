"""Check evals/ against the generator. Usage: verify.py <evals_dir>; exits 1 on any problem.

1. Drift: regenerate every case into a temp dir and require evals/ to match it exactly —
   same case dirs, subdirs, and files, byte for byte. Stops here on any difference.
2. Fixtures: run each freshly generated (trusted) setup script, never the checked-in
   copy, in an empty dir with a minimal env and a timeout, and require it to produce
   exactly its fixture's files with exactly its fixture's contents.
"""

import filecmp
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import fixtures as F
import gen

CASE = re.compile(r"^\d{2}-")
SETUP_TIMEOUT = 60


def _rel(base, name, root):
    """Path of base/name relative to root, normalized."""
    return os.path.normpath(os.path.relpath(os.path.join(base, name), root))


def tree(root, cases_only=True):
    """Every file and directory under root (dirs end in '/'), relative to root."""
    out = set()
    tops = [x for x in os.listdir(root) if CASE.match(x)] if cases_only else ["."]
    for top in tops:
        for base, dirs, names in os.walk(os.path.join(root, top)):
            out.update(_rel(base, d, root) + "/" for d in dirs)
            out.update(_rel(base, n, root) for n in names)
        if top != ".":
            out.add(top + "/")
    return out


def drift(generated, evals):
    want, have = tree(generated), tree(evals)
    problems = [f"MISSING {p}" for p in sorted(want - have)]
    problems += [f"STALE   {p}" for p in sorted(have - want)]
    problems += [
        f"DIFFERS {p}"
        for p in sorted(want & have)
        if not p.endswith("/")
        and not filecmp.cmp(
            os.path.join(generated, p), os.path.join(evals, p), shallow=False
        )
    ]
    return problems


def expected_fixtures():
    expected = {}
    real = gen.write_case
    gen.write_case = lambda root, slug, files, *a, **k: expected.__setitem__(
        slug, files or {}
    )
    try:
        for fn in gen.SKILLS.values():
            fn(None)
    finally:
        gen.write_case = real
    return expected


def fixtures(generated):
    problems = []
    for slug, files in sorted(expected_fixtures().items()):
        if not files:
            continue
        prompt = Path(generated, slug, "prompt.md").read_text()
        script = prompt.split("````bash\n", 1)[1].split("\n````", 1)[0]
        with tempfile.TemporaryDirectory() as d:
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": d,
                "LANG": "C.UTF-8",
            }
            try:
                r = subprocess.run(
                    ["bash", "-c", script],
                    cwd=d,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=SETUP_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                problems.append(f"SETUP TIMEOUT {slug} (>{SETUP_TIMEOUT}s)")
                continue
            if r.returncode:
                problems.append(f"SETUP FAIL {slug}: {r.stderr[:200]}")
                continue
            produced = {p for p in tree(d, cases_only=False) if not p.endswith("/")}
            problems += [f"EXTRA    {slug}: {p}" for p in sorted(produced - set(files))]
            problems += [f"ABSENT   {slug}: {p}" for p in sorted(set(files) - produced)]
            problems += [
                f"MISMATCH {slug}: {p}"
                for p in sorted(produced & set(files))
                if Path(d, p).read_text() != F.render(files[p])
            ]
    return problems


def main(evals):
    with tempfile.TemporaryDirectory() as generated:
        for fn in gen.SKILLS.values():
            fn(generated)
        problems = drift(generated, evals)
        if problems:
            print(
                "\n".join(problems)
                + "\nstopped: fix drift (re-run gen.py) before fixtures are executed"
            )
            return 1
        problems = fixtures(generated)
    print(
        "\n".join(problems)
        or "ok: cases match the generator and every fixture reproduces exactly"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
