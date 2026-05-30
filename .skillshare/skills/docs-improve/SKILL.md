---
name: docs-improve
description: |
  Audit and improve project documentation using Diataxis and documentation
  quality best practices across the docs set.
---

# Documentation Improvement Command

Analyze and improve project documentation in the `docs/` directory following
documentation best practices and the Diataxis framework.

## Parallel Agent Integration

This command uses parallel agents CONDITIONALLY when total documentation lines > 500.
When triggered, executes: `~/.claude/scripts/parallel_agent.py --json --validate`

## Task

You are a documentation expert improving project documentation. Your goals are to:

1. Audit all documentation for completeness and quality
2. Identify missing document types essential for great applications
3. Ensure consistent formatting and cross-referencing
4. Improve individual documents based on their purpose
5. Generate a documentation health score with actionable recommendations

## The Diataxis Framework

Organize documentation into four quadrants based on user needs:

| Type | Orientation | Purpose | Example |
|------|-------------|---------|---------|
| **Tutorials** | Learning | Step-by-step lessons for beginners | "Your First Feature" |
| **How-to Guides** | Problem-solving | Steps to achieve specific goals | "How to Configure X" |
| **Reference** | Information | Technical specifications | "API Reference" |
| **Explanation** | Understanding | Conceptual background | "Architecture Overview" |

## Instructions

### Step 1: Gather Documentation Inventory

Read all documentation files:

- Core documentation: README.md, AGENTS.md, CONTRIBUTING.md, CHANGELOG.md
- Docs directory: Glob docs/**/*.md
- Config documentation: config/README.md

### Step 2: Evaluate Against Required Documents

**Essential Documents**:

| Document | Priority | Purpose | Audience |
|----------|----------|---------|----------|
| `README.md` | Critical | Project overview, quick start | All |
| `AGENTS.md` | Critical | AI assistant context | AI/Contributors |
| `docs/README.md` | High | Documentation index/hub | All |
| `docs/GETTING_STARTED.md` | High | First-time user guide | New users |
| `docs/CONFIGURATION.md` | High | All config options | Operators |
| `docs/ARCHITECTURE.md` | Medium | System design | Developers |
| `docs/TROUBLESHOOTING.md` | Medium | Common problems/solutions | Operators |
| `CONTRIBUTING.md` | Medium | How to contribute | Contributors |
| `CHANGELOG.md` | Low | Version history | All |

### Step 3: Quality Assessment

For each document, check:

**Structure Quality**:

- [ ] Clear title and one-line description
- [ ] Table of contents (if > 100 lines)
- [ ] Consistent heading hierarchy (H2 for sections, H3 for subsections)
- [ ] "Last Updated" date
- [ ] "Related Documents" section

**Content Quality**:

- [ ] Defines target audience
- [ ] States prerequisites
- [ ] Provides working code examples
- [ ] No placeholder text (TODO, TBD, FIXME)
- [ ] Progressive disclosure (overview → details)

**Formatting Quality**:

- [ ] Code blocks have language specified (`yaml`, `python`, `bash`)
- [ ] Tables are properly aligned
- [ ] Links use relative paths
- [ ] Consistent emoji/icon usage

**Cross-Reference Validation**:

- [ ] All internal links resolve
- [ ] Bidirectional links where appropriate
- [ ] No orphan documents (not linked from anywhere)

### Step 4: Calculate Documentation Health Score

Score documentation on a 100-point scale:

| Factor | Weight | Measurement |
|--------|--------|-------------|
| Required docs present | 30% | Count present / total required |
| No broken links | 20% | Percentage of valid links |
| Consistent formatting | 15% | Passes automated checks |
| Has code examples | 15% | Docs with examples / total docs |
| Up-to-date markers | 10% | Docs with "Last Updated" / total |
| Cross-referenced | 10% | Docs with "Related" section / total |

### Step 5: Generate Improvements

**For Missing Documents** - Create from template:

```markdown
# [Document Title]

> [One-line description of this document's purpose]

**Last Updated**: YYYY-MM-DD
**Audience**: [Target audience]

---

## Overview

[2-3 sentences explaining what this document covers]

## Table of Contents

- [Section 1](#section-1)
- [Section 2](#section-2)

---

## [Section 1]

[Content]

---

## Related Documents

- [AGENTS.md](../AGENTS.md) - Project context
- [Related Doc](path/to/doc.md) - Brief description
```

**For Existing Documents** - Apply improvements:

- Add missing sections (overview, prerequisites, related docs)
- Fix broken links
- Add "Last Updated" dates
- Standardize formatting
- Improve code examples

### Step 6: Create Documentation Index

If `docs/README.md` doesn't exist, create it with:

- Quick Links to most important docs
- Documentation by Audience sections
- All Documents table with descriptions and dates

## Output Format

Provide your analysis and improvements as:

### 1. Documentation Health Report

```text
## Documentation Health Score: XX/100

### Score Breakdown
- Required Documents: XX/30 (X of Y present)
- Link Integrity: XX/20 (X broken links found)
- Formatting: XX/15
- Code Examples: XX/15
- Freshness: XX/10
- Cross-References: XX/10

### Inventory
| Document | Status | Issues |
|----------|--------|--------|
| README.md | Good | None |
| docs/README.md | Missing | Create documentation index |

### Priority Actions
1. [HIGH] Create docs/README.md - Documentation index
2. [HIGH] Add GETTING_STARTED.md - Core functionality
3. [MEDIUM] Fix 3 broken links in AGENTS.md
```

### 2. Improved/Generated Documents

For each document that needs creation or significant updates, provide the full content.

### 3. Validation Summary

```text
## Validation Results

### Broken Links
- docs/ARCHITECTURE.md:45 → invalid-path.md (NOT FOUND)

### Missing Cross-References
- GETTING_STARTED.md should link to CONFIGURATION.md

### Formatting Issues
- docs/CONFIGURATION.md: Code block on line 23 missing language
```

## Writing Principles

- **Be accurate**: Only document what actually exists
- **Be concise**: Respect reader's time
- **Be consistent**: Same style across all docs
- **Be current**: Update docs with code changes
- **Be connected**: Link related information

## Audience-Specific Language

| Audience | Tone | Detail Level | Focus |
|----------|------|--------------|-------|
| Engineers | Direct | Technical | Core functionality |
| Developers | Technical | In-depth | Architecture and APIs |
| Operators | Direct | Practical | Config and troubleshooting |
| Contributors | Collaborative | Process-oriented | Standards and workflow |
