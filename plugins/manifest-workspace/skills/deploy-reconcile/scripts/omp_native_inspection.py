#!/usr/bin/env python3
"""Emit read-only OMP native inspection JSON using only Python's standard library."""

import argparse
import json

from _omp_readonly.inspection import inspection_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(json.dumps(inspection_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
