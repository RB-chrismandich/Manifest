# Patches for branches this one must not touch

## `T1.15-adversarial-design-loop.patch`

Fixes the `adversarial-design-loop` plugin, which lives on
`emdash/twelve-emus-wonder-cfrk0` at `99f3e41` — **not** on this branch.

**Why it is a patch and not a commit.** That worktree has live processes in it
(verified with `lsof`, not assumed from the directory's existence). Committing
would move a branch ref under a running session. Its working tree is clean, so
nothing would have been destroyed, but a ref moving underneath an active session
is still someone else's call to opt into.

**Verified, not merely written.** Applied in a detached worktree at `99f3e41`:
`claude plugin validate --strict` passes, `marketplace.json` parses, and all six
skills' frontmatter loads with `name` + `description`.

```bash
git checkout emdash/twelve-emus-wonder-cfrk0
git apply specs/674-plugin-architecture/patches/T1.15-adversarial-design-loop.patch
claude plugin validate . --strict
```

### What it changes

- **`loop-scaffold` step 2** — the real defect. It told the model to copy
  `../render-verify/scripts/render_and_scan.py`, "resolve relative to this
  skill's directory". A shell command runs with cwd set to the user's project,
  so that resolves against the wrong root and the copy lands nowhere. Now
  `${CLAUDE_PLUGIN_ROOT}/skills/render-verify/scripts/render_and_scan.py`.
- **`render-verify`** — anchors the command with `cd <artifact-dir>`, and names
  the plugin's own copy by variable under Additional resources.
- **`marketplace.json`** — adds `homepage` (260 of 276 official entries carry
  one).

### What it deliberately does not change

**`python3 tools/render_and_scan.py` at `render-verify:38` is left alone, and
the task's description of it is wrong.** It is not a bare plugin-relative path:
it is the *project's pinned copy*, placed in `<artifact-dir>/tools/` by
`loop-scaffold` and deliberately owned by the project so that a plugin update
cannot change a gate under it. The `tools/` (line 32) versus `scripts/` (line
76) "self-contradiction" the task records is that real distinction — the
project's copy versus the plugin's source — not an error. Rewriting it would
have broken a working design to satisfy a misreading.

Defect 2 (`${CLAUDE_PLUGIN_ROOT}` absent from all six skills) is true as
measured, but its actionable surface is **one line**: five of the six skills
reference no plugin-local asset, and the plugin contains exactly one such asset.
