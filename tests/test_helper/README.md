# Test Helper Libraries

The bats test files in `tests/bats/` depend on
[bats-support](https://github.com/bats-core/bats-support) and
[bats-assert](https://github.com/bats-core/bats-assert).
These must be installed before running the test suite.

## Installation via Git Submodules (Recommended)

From the repository root:

```bash
git submodule add https://github.com/bats-core/bats-support tests/test_helper/bats-support
git submodule add https://github.com/bats-core/bats-assert tests/test_helper/bats-assert
```

Then initialize after cloning:

```bash
git submodule update --init --recursive
```

## Installation via Manual Clone

If you prefer not to use submodules:

```bash
git clone https://github.com/bats-core/bats-support tests/test_helper/bats-support
git clone https://github.com/bats-core/bats-assert tests/test_helper/bats-assert
```

## Installing bats-core

The test runner itself ([bats-core](https://github.com/bats-core/bats-core)) must also be installed:

```bash
# macOS (Homebrew)
brew install bats-core

# Linux (npm)
npm install -g bats

# Linux (from source)
git clone https://github.com/bats-core/bats-core.git
cd bats-core && sudo ./install.sh /usr/local
```

## Running Tests

From the repository root:

```bash
# Run all bats tests
bats tests/bats/

# Run a specific test file
bats tests/bats/git_platform.bats
bats tests/bats/git_ops.bats
bats tests/bats/linear_ops.bats
bats tests/bats/label_sync.bats
bats tests/bats/deploy_skills.bats

# Run with verbose output
bats --verbose-run tests/bats/
```

## Directory Structure

```text
tests/
├── test_helper/
│   ├── README.md               # This file
│   ├── bats-support/           # bats-support library (git submodule)
│   │   └── load.bash
│   └── bats-assert/            # bats-assert library (git submodule)
│       └── load.bash
├── bats/
│   ├── git_platform.bats       # Tests for git_platform.sh
│   ├── git_ops.bats            # Tests for git_ops.sh
│   ├── linear_ops.bats         # Tests for linear_ops.sh
│   ├── label_sync.bats         # Tests for label_sync.sh
│   └── deploy_skills.bats      # Tests for bootstrap skills deploy
├── python/                     # Python test files (future)
│   └── .gitkeep
└── fixtures/                   # Shared test fixtures (future)
    └── .gitkeep
```
