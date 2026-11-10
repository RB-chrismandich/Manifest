---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from our dotfiles deployer repo; you don't have a checkout.)

We had a deploy gap where two symlinks never got created, but our bats test `deploy_cursor links shared assets` was green the whole time.

```bash
create_symlink() {
  local src=$1 dst=$2
  if [[ ! -e "$src" ]]; then
    echo "warning: $src missing, skipping" >&2
    return 0
  fi
  ln -sfn "$src" "$dst"
}
```

```bash
@test "deploy_cursor links shared assets" {
  export SRC="$BATS_TMPDIR/src" HOME="$BATS_TMPDIR/home"
  mkdir -p "$SRC/scripts" "$HOME/.cursor"
  run deploy_cursor
  [ "$status" -eq 0 ]
  [ -L "$HOME/.cursor/scripts" ]
}
```
Why didn't the test catch it and how should the tests change?
