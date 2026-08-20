# Using Commands

> Invoking skills and commands after your first successful run.

## Using Commands

Manifest integrates with Claude Code through slash commands.

### Available Commands

#### `/python-refactor` - Code Analysis (Always uses parallel agents)

Analyzes Python codebases for security, architecture, and code quality issues.

**Example:**

```bash
# In Claude Code
/python-refactor src/
```

**What it does:**

1. Runs every enabled agent in parallel (Cursor, Gemini, Claude, Codex, Antigravity,
   plus Devin when enabled)
2. Each agent analyzes for: security vulnerabilities, bugs, performance issues
3. Synthesizes results with consensus scoring
4. Validates against Tier 1 (security) and Tier 2 (quality) checks
5. Returns unified recommendation

#### `/docs-generate-diagrams` - Architecture Diagrams (Conditional)

Generates Mermaid diagrams for project documentation.

**Example:**

```bash
# In Claude Code
/docs-generate-diagrams docs/ARCHITECTURE.md
```

**Triggers parallel agents when:** Analyzing 5+ unique imports/modules

#### `/docs-improve` - Documentation Analysis (Conditional)

Analyzes documentation against the Diataxis framework.

**Example:**

```bash
# In Claude Code
/docs-improve docs/
```

**Triggers parallel agents when:** Total documentation lines > 500

#### `/docs-improve-readme` - README Enhancement (Never uses parallel agents)

Improves README.md documentation following best practices.

**Example:**

```bash
# In Claude Code
/docs-improve-readme
```

### Command Output Formats

**Markdown (default):**

```bash
~/.claude/scripts/parallel_agent.py "Review this code"
```

**JSON (for programmatic parsing):**

```bash
~/.claude/scripts/parallel_agent.py --json "Review this code"
```

**Full output (no truncation):**

```bash
~/.claude/scripts/parallel_agent.py --json --full-output "Review this code"
```

---

---

[← Getting Started](../GETTING_STARTED.md)
