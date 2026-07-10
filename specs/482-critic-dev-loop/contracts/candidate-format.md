# Contract: Implementer Candidate Format (file blocks)

**Feature**: `482-critic-dev-loop` | Enforces spec FR-005, FR-007, FR-011, FR-017

The implementer role MUST express its candidate change as one or more file blocks:

````text
```cddl-file path/relative/to/repo/root.py
<complete new file content>
```
````

- The info-string is `cddl-file ` + exactly one path (no quotes, no spaces in v1 —
  a path containing spaces is a validation failure).
- Content is the **full** intended file content (full-file semantics, not a diff —
  research D10). An empty body creates/truncates to an empty file.
- Deleting a file: ` ```cddl-delete path``` ` with empty body.
- Prose outside blocks is retained as `notes` in the iteration record and ignored by
  apply.

## Validation (all-or-nothing, pre-write — FR-017)

For every block path:

1. MUST be relative (no leading `/`, no drive prefix).
2. MUST NOT contain a `..` segment.
3. `realpath(repo_root / parent_dir)` MUST be inside `realpath(repo_root)` — resolves
   symlinked parents, catching symlink escapes.
4. MUST NOT point into `.git/`.

Any violation ⇒ the ENTIRE candidate is rejected with zero writes, a `confinement`
deficiency is recorded and fed back (FR-007), and the iteration counts toward the
ceiling. A candidate with zero `cddl-file`/`cddl-delete` blocks is likewise a
rejected candidate (`no-candidate` deficiency).

## Apply semantics

- Writes are atomic per file (temp file + rename within the same directory);
  parent directories created as needed.
- Before overwriting or deleting an existing file, its pre-image is copied to
  `iterations/<n>/backup/<path>` — the rollback path for `--allow-dirty` runs
  whose uncommitted edits git cannot recover.
- Every written/deleted path is appended to the run's `written_paths` — the exact
  set staged on success (`git add -- <paths>`) and reported for manual discard on
  failure (FR-011).
- Byte-identical candidate to the previous iteration ⇒ `stalled=true` flagged in the
  iteration record and the report; never treated as success (spec edge case).

## Test fixtures required (D13)

Traversal `../escape`, absolute `/etc/x`, symlink-parent escape, `.git/hooks/x`,
space-in-path, zero-block output, delete-block, byte-identical stall, multi-file
happy path.
