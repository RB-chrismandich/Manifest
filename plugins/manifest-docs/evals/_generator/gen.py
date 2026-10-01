"""Write evals/<case>/ dirs for manifest-docs. Usage: gen.py <evals_dir> <skill>..."""

import sys

from all_ import all_
from diagrams import diagrams
from improve import improve
from readme import readme

SKILLS = {"readme": readme, "diagrams": diagrams, "improve": improve, "all": all_}

if __name__ == "__main__":
    root = sys.argv[1]
    for name in sys.argv[2:]:
        SKILLS[name](root)
