---
name: learning-capture
description: "Capture structured lessons learned after major tasks. Categories: pattern, antipattern, tool discovery, configuration insight. Stores in ~/.claude/config/knowledge_base.yml and queries existing learnings."
---

# Learning Loop Skill

After completing significant tasks, capture structured lessons learned. Stores
knowledge entries in a YAML knowledge base for future reference. Can also query
existing entries by language, tool, or category.

## Arguments

- `$ARGUMENTS` -- One of:
  - `capture` -- Interactive capture of a new learning (default if no args)
  - `query <term>` -- Search existing learnings by keyword
  - `list [category]` -- List all entries, optionally filtered by category
  - `stats` -- Show knowledge base statistics

---

## Phase 1: Mode Detection

| Argument | Action |
|----------|--------|
| (empty) or `capture` | Begin structured capture flow |
| `query <term>` | Search knowledge base for matching entries |
| `list [category]` | List entries, filter by category if provided |
| `stats` | Show entry counts by category, language, recency |

---

## Phase 2: Capture Flow

When capturing a new learning, gather the following fields:

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| `title` | Short descriptive title | "Ruff replaces flake8+isort+black" |
| `category` | One of: `pattern`, `antipattern`, `tool-discovery`, `config-insight` | `tool-discovery` |
| `language` | Language/ecosystem (or `general`) | `python` |
| `description` | 1-3 sentence explanation | "Ruff is a single tool that replaces..." |

### Optional Fields

| Field | Description | Example |
|-------|-------------|---------|
| `tags` | Searchable keywords | `[linting, formatting, migration]` |
| `tool` | Specific tool involved | `ruff` |
| `source` | Where this was learned | `task-42`, `pr-review`, `debugging` |
| `confidence` | How proven is this (high/medium/low) | `high` |
| `example` | Brief code/config example | `ruff check --fix .` |

### Context Inference

Before prompting, infer context from the current session:

- Check recent git log for task context
- Check current directory for language indicators
- Pre-fill fields where possible to reduce friction

---

## Phase 3: Storage

Store entries in `~/.claude/config/knowledge_base.yml` using this schema:

```yaml
# Knowledge Base - Auto-managed by learning-capture skill
# Do not edit manually unless correcting entries
version: 1
entries:
  - id: "20260211-001"
    title: "Ruff replaces flake8+isort+black"
    category: tool-discovery
    language: python
    description: "Ruff is a single Rust-based tool that replaces flake8, isort, and black with faster execution."
    tags: [linting, formatting, migration]
    tool: ruff
    source: python-refactor
    confidence: high
    example: "ruff check --fix . && ruff format ."
    created: "2026-02-11T14:30:00Z"
    last_referenced: "2026-02-11T14:30:00Z"
```

### Antipattern entries: guardrail fields (spec 457)

When the captured learning is an **antipattern**, additionally populate the
guardrail-registry fields so the entry is immediately consumed by write-time
guidance (`code-audit`) and `/manifest-code-quality:ai-code-audit` (capture-to-active in one step):

- `severity`: `critical` | `high` | `medium` | `low` | `info`
- `detection_cue`: how to spot it in code (string, or per-language map)
- `prevention_rule`: positive "do this instead" phrasing
- `provenance: session-capture`
- `tags` MUST include exactly ONE guardrail-category tag: `arch`,
  `async-state`, `error-handling`, `security`, `dependency`, `iteration`
  (structure/duplication/tests → arch; async/lifecycle/races → async-state;
  swallowed errors/validation → error-handling; vulns/secrets → security;
  packages/env → dependency; refinement/session-drift → iteration)

Prefer capturing via `~/.claude/scripts/learning_capture.sh add` (supports all
of the above as `--severity`, `--detection-cue`, `--prevention-rule`,
`--provenance`, plus the tag in `--tags`).

### ID Generation

Format: `YYYYMMDD-NNN` where NNN is a zero-padded sequence number for that date.

### File Creation

If `knowledge_base.yml` does not exist, create it with the version header and an
empty entries list before adding the first entry.

---

## Phase 4: Query Flow

When querying, search across these fields: `title`, `description`, `tags`, `tool`,
`language`, `category`.

```bash
# Search examples
/learning-capture query ruff
/learning-capture query "go test"
/learning-capture list antipattern
/learning-capture list tool-discovery
/learning-capture stats
```

### Query Output

```markdown
## Knowledge Base: Query Results

**Query**: {search-term}
**Matches**: {count}

| ID | Category | Title | Language | Confidence |
|----|----------|-------|----------|------------|
| 20260211-001 | tool-discovery | Ruff replaces flake8+isort+black | python | high |
| 20260210-003 | pattern | Use ruff in pre-commit hooks | python | high |

### Details

#### 20260211-001: Ruff replaces flake8+isort+black
- **Category**: tool-discovery
- **Language**: python
- **Description**: Ruff is a single Rust-based tool that replaces flake8, isort, and black.
- **Example**: `ruff check --fix . && ruff format .`
- **Source**: python-refactor
```

### Stats Output

```markdown
## Knowledge Base Statistics

**Total entries**: {count}
**Date range**: {oldest} to {newest}

| Category | Count |
|----------|-------|
| pattern | 12 |
| antipattern | 8 |
| tool-discovery | 5 |
| config-insight | 3 |

| Language | Count |
|----------|-------|
| python | 10 |
| go | 6 |
| node | 5 |
| general | 7 |
```

---

## Phase 5: Reference Tracking

When a knowledge base entry is relevant to a current task, update its
`last_referenced` timestamp. This enables staleness tracking and prioritization.

---

## Safety Checks

- Never delete existing entries -- append only
- Validate YAML syntax before writing
- Deduplicate: warn if a similar title+category+language already exists
- Back up `knowledge_base.yml` before writing (copy to `knowledge_base.yml.bak`)
- Maximum 500 entries per file (suggest archiving if exceeded)
