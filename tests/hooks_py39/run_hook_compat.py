#!/usr/bin/env python3
"""Execute registered Claude Python hooks on the deployed Python floor."""

import platform
import sys

from hook_compat_registration import verify_registrations
from hook_compat_scenarios import run_scenarios


def main():
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 9):
        raise SystemExit("hook compatibility gate requires CPython 3.9")
    verify_registrations()
    run_scenarios()
    print("PASS registered built-in and plugin Python hooks under CPython 3.9")


if __name__ == "__main__":
    main()
