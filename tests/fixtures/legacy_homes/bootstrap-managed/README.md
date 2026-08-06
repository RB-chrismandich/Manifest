# Bootstrap-managed legacy home fixture

Tests materialize `~/.claude/skills -> ~/.manifest/skills` from this fixture in
a temporary home.  The symlink is made at test time so the fixture remains
portable across checkout locations.
