# Regular package on purpose. The repo's `tests` tree was a PEP 420 namespace
# package, and any environment with a *regular* `tests` package in
# site-packages (esp-coredump ships one) silently wins the import — a regular
# package anywhere on sys.path closes the namespace, so
# `tests.token_benchmark` stops resolving and pytest dies at collection.
# This __init__ makes the repo's `tests` regular too; rootdir is prepended to
# sys.path (root conftest.py), so the repo copy is found first and wins.
