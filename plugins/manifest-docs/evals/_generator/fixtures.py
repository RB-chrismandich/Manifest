"""Fixture repo ("tallyho") builders for manifest-docs evals."""

import textwrap


def D(s: str) -> str:
    """Dedent a triple-quoted fixture body and drop its leading newline."""
    return textwrap.dedent(s).lstrip("\n")


CODE = {
    "pyproject.toml": D("""
        [project]
        name = "tallyho"
        version = "0.3.0"
        requires-python = ">=3.11"
        dependencies = ["click>=8.1"]

        [project.scripts]
        tally = "tally.cli:main"
        """),
    "Makefile": "install:\n\tpip install -e .\n\ntest:\n\tpytest -q\n",
    "tally/__init__.py": '"""tallyho: count events from CSV logs and flag threshold breaches."""\n',
    "tally/config.py": D('''
        """Config loading. Values come from tally.toml, falling back to DEFAULTS."""
        import tomllib

        DEFAULTS = {"threshold": 5, "db_path": "tally.db", "window_minutes": 60}


        def load(path="tally.toml"):
            try:
                with open(path, "rb") as f:
                    return {**DEFAULTS, **tomllib.load(f)}
            except FileNotFoundError:
                return dict(DEFAULTS)
        '''),
    "tally/ingest.py": D('''
        """Read CSV event logs and hand normalized records to the store."""
        import csv

        from tally import store


        def read_csv(path):
            with open(path, newline="") as f:
                return list(csv.DictReader(f))


        def normalize(row):
            return {"event": row["event"].strip().lower(), "ts": row["ts"]}


        def run(path, db_path):
            store.save([normalize(r) for r in read_csv(path)], db_path)
        '''),
    "tally/store.py": D('''
        """SQLite persistence for events."""
        import sqlite3


        def save(records, db_path):
            con = sqlite3.connect(db_path)
            con.execute("CREATE TABLE IF NOT EXISTS events (event TEXT, ts TEXT)")
            con.executemany("INSERT INTO events VALUES (:event, :ts)", records)
            con.commit()


        def counts(db_path):
            con = sqlite3.connect(db_path)
            return dict(con.execute("SELECT event, COUNT(*) FROM events GROUP BY event"))
        '''),
    "tally/report.py": D('''
        """Flag events whose count meets the threshold."""
        from tally import store


        def breaches(db_path, threshold):
            return {e: n for e, n in store.counts(db_path).items() if n >= threshold}
        '''),
    "tally/cli.py": D('''
        """Command-line entry point."""
        import click

        from tally import config, ingest, report


        @click.group()
        def main():
            pass


        @main.command("ingest")
        @click.argument("csv_path")
        def ingest_cmd(csv_path):
            cfg = config.load()
            ingest.run(csv_path, cfg["db_path"])


        @main.command("report")
        @click.option("--threshold", type=int, default=None)
        def report_cmd(threshold):
            cfg = config.load()
            t = threshold if threshold is not None else cfg["threshold"]
            for event, n in report.breaches(cfg["db_path"], t).items():
                click.echo(f"{event}\\t{n}")
        '''),
    "tests/test_report.py": D("""
        from tally import ingest, report


        def test_breach(tmp_path):
            csv_path = tmp_path / "e.csv"
            csv_path.write_text("event,ts\\n" + "login,1\\n" * 5)
            db = str(tmp_path / "t.db")
            ingest.run(str(csv_path), db)
            assert report.breaches(db, 5) == {"login": 5}
        """),
}

SPLIT_INGEST = {
    "tally/ingest/__init__.py": D('''
        """Ingest pipeline: reader -> normalize -> store."""
        from tally import store
        from tally.ingest.normalize import normalize
        from tally.ingest.reader import read_csv


        def run(path, db_path):
            store.save([normalize(r) for r in read_csv(path)], db_path)
        '''),
    "tally/ingest/reader.py": D('''
        """CSV reading."""
        import csv


        def read_csv(path):
            with open(path, newline="") as f:
                return list(csv.DictReader(f))
        '''),
    "tally/ingest/normalize.py": D('''
        """Row normalization."""


        def normalize(row):
            return {"event": row["event"].strip().lower(), "ts": row["ts"]}
        '''),
}

ACME = D("""
    ## Running on the ops cron host

    Ops runs `tally report` every 15 minutes from cron on the shared metrics
    host; the crontab entry is `*/15 * * * * cd /srv/tally && tally report`.
    Output goes to the host's mail spool, so check there first when a breach
    alert looks wrong.
    """)

SUPPORT = "## Support\n\nOpen an issue or ping #tally in chat.\n"


def good_readme(typo=False, install="make install"):
    recv = "recieve" if typo else "receive"
    return (
        D(f"""
        # tallyho

        Count events from CSV logs and flag any event whose count meets a threshold.

        ## Requirements

        - Python 3.11+
        - click 8.1+

        ## Quick start

        ```bash
        {install}
        tally ingest events.csv
        tally report
        ```

        ## Usage

        `tally ingest FILE` loads a CSV with `event,ts` columns into SQLite.
        `tally report` prints every event whose count is at or above the threshold.
        Pass `--threshold N` to override it for one run.

        ## Configuration

        Settings are read from `tally.toml` in the working directory.

        | Key | Default | Meaning |
        |-----|---------|---------|
        | `threshold` | `5` | Minimum count to report |
        | `db_path` | `tally.db` | SQLite file |
        | `window_minutes` | `60` | Reporting window |

        ## Testing

        ```bash
        make test
        ```

        Tests {recv} a temporary directory from pytest and never touch `tally.db`.

        """)
        + ACME
        + "\n"
        + SUPPORT
    )


class Code(str):
    """A Python expression emitted verbatim into the setup script."""


def bloated_readme():
    intro = D("""
        # tallyho

        tallyho is a comprehensive, powerful and seamless event counting platform.
        It is blazing fast and robust, with a rich set of features. Simply install
        it and you just need to run a command. It is important to note that tallyho
        is state-of-the-art.

        ## Table of Contents

        """)
    body = good_readme().split("\n", 3)[3]
    return [
        intro,
        Code('"".join(f"- [Section {i}](#section-{i})\\n" for i in range(1, 13))'),
        "\n" + body + "\n## Directory tree\n\n```text\n",
        Code(
            '"".join(f"tally/module_{i:02d}.py   # placeholder listing line {i}\\n" for i in range(1, 41))'
        ),
        "```\n\n## FAQ\n\n",
        Code(
            '"".join(f"**Q{i}: Does tally handle case {i}?**\\n\\nOf course. Obviously it does, basically out of the box.\\n\\n" for i in range(1, 31))'
        ),
        "\n## Changelog\n\n",
        Code(
            '"".join(f"- 0.{i // 10}.{i % 10}: minor fixes\\n" for i in range(30, 0, -1))'
        ),
    ]


def stale_readme(onboarding=False):
    install = "" if onboarding else "make install\nmake docker\n"
    link = "" if onboarding else "\nSee [the usage guide](docs/USAGE.md) for more.\n"
    return (
        D("""
        # tallyho

        Count events from CSV logs and flag threshold breaches.

        ## Requirements

        - Python 3.8+

        ## Quick start

        ```bash
        """)
        + install
        + "tally report\n```\n"
        + link
        + D("""

        ## Configuration

        Default threshold: `10`. Set `threshold` in `tally.toml` to change it.

        """)
        + SUPPORT
    )


def troubleshooting():
    head = D("""
        # Troubleshooting

        In this document we will cover every error. It is important to note that
        most errors are simply configuration mistakes. Needless to say, read carefully.

        """)
    body = Code(
        '"".join(f"## {s} errors\\n\\n" + "".join(f"### `{s.upper()}-{i:02d}`\\n\\n'
        'Please note that this error is basically caused by case {i}. Obviously, re-run the command.\\n\\n"'
        ' for i in range(1, 25)) for s in ("Install", "Auth", "Ingest"))'
    )
    return [head, body]


CONFIG_HEAD = D("""
    # Configuration reference

    | Key | Default | Meaning |
    |-----|---------|---------|
    | `threshold` | `5` | Minimum count to report |
    | `db_path` | `tally.db` | SQLite file |
    | `window_minutes` | `60` | Reporting window |
    """)


def config_ref():
    return [
        CONFIG_HEAD,
        Code(
            '"".join(f"| `legacy_alias_{i:03d}` | none | Deprecated alias, ignored |\\n" for i in range(440))'
        ),
    ]


SMALL = {
    "docs/GETTING_STARTED.md": "# Getting started\n\n1. `make install`\n2. `tally ingest events.csv`\n3. `tally report`\n",
    "docs/CONFIGURATION.md": CONFIG_HEAD,
    "docs/ingest-howto.md": "# How to ingest a CSV\n\nColumns must be `event,ts`. Run `tally ingest FILE`.\n",
    "docs/ARCHITECTURE.md": "# Architecture\n\n`cli` -> `ingest` -> `store` (SQLite); `report` reads counts from `store`.\n",
}


def mermaid(title, body, caption):
    return f"## {title}\n\n```mermaid\n{body}\n```\n\n{caption}\n\n"


FLOW = "flowchart LR\n    cli[tally.cli] --> ingest[tally.ingest]\n    ingest --> store[(tally.store / SQLite)]\n    cli --> report[tally.report]\n    report --> store"


def huge_diagrams():
    return [
        "# Architecture diagrams\n\n",
        Code(
            '"".join(f"## Diagram {i}\\n\\n```mermaid\\n" + '
            + repr(FLOW)
            + ' + "\\n```\\n\\n" + "".join('
            'f"Note {j} on diagram {i}: this paragraph restates the node list in prose.\\n" for j in range(1, 45)) + "\\n\\n"'
            " for i in range(1, 8))"
        ),
    ]


def stale_diagrams():
    redis = "flowchart LR\n    cli[tally.cli] --> ingest[tally.ingest]\n    ingest --> cache[(Redis cache)]\n    cache --> store[tally.store]\n    report[tally.report] --> cache"
    seq = "sequenceDiagram\n    participant C as cli\n    participant I as ingest\n    participant R as Redis\n    C->>I: run(path)\n    I->>R: SET event counts"
    return (
        "# Architecture diagrams\n\n"
        + mermaid("Components", redis, "Counts are cached in Redis before persistence.")
        + mermaid("Ingest", seq, "Ingest writes straight to Redis.")
    )


def split_stale_diagrams():
    f = "flowchart LR\n    cli[tally.cli] --> ingest_py[tally/ingest.py]\n    ingest_py --> store[(tally.store / SQLite)]\n    report[tally.report] --> store"
    return "# Architecture diagrams\n\n" + mermaid(
        "Components", f, "`tally/ingest.py` reads and normalizes CSV rows."
    )


Q3 = "'" * 3


def parts(value):
    return value if isinstance(value, list) else [value]


def render(value):
    """Content a file value produces, for local checks."""
    return "".join(eval(p) if isinstance(p, Code) else p for p in parts(value))


def emit(value):
    out = []
    for p in parts(value):
        if isinstance(p, Code):
            out.append(str(p))
        else:
            assert Q3 not in p and not p.endswith("\\"), p[:40]
            out.append("r" + Q3 + p + Q3)
    return " + ".join(out)


def setup_block(files):
    lines = [
        "import os",
        "",
        "def w(path, text):",
        "    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)",
        "    open(path, 'w').write(text)",
        "",
    ]
    lines += [f"w({path!r}, {emit(v)})" for path, v in sorted(files.items())]
    return (
        "Before anything else, create the project by running this with Bash exactly as written "
        "(it writes the repository into the current directory):\n\n"
        "````bash\npython3 - <<'EOF'\n" + "\n".join(lines) + "\nEOF\n````\n\n"
    )
