# cookedbooks/.claude Comprehensive Review
**Date**: 2026-02-04
**Reviewer**: Claude (Manifest project)
**Total Lines**: 2,409 lines across 9 commands + config files

---

## Executive Summary

The cookedbooks `.claude` directory represents a **production-grade, enterprise-level** AI orchestration system for managing a complex polyglot microservices platform. It demonstrates advanced patterns that go beyond Manifest's current capabilities.

**Key Statistics**:
- **9 commands** (2,409 lines total)
- **1 auto-trigger skill** (event-flow-guard)
- **1 project-specific validation override** (validation_overrides.yml)
- **1 orchestration prompt** (headless_prompt.md)
- **70+ explicit permissions** (settings.local.json)

**Sophistication Level**: 🌟🌟🌟🌟🌟 (Expert-tier implementation)

---

## File Inventory

### Commands (9 files, 2,409 lines)

| File | Lines | Purpose | Parallel Agents |
|------|-------|---------|-----------------|
| `issue-process.md` | 404 | Process GitHub issue into implementation | ALWAYS |
| `issue-plan.md` | 387 | Plan implementation strategy | CONDITIONAL |
| `issue-triage.md` | 289 | Triage/cleanup open issues | NO |
| `pipeline-validate.md` | 288 | Validate transaction pipeline | ALWAYS |
| `migration-check.md` | 281 | Database migration RBAC validation | CONDITIONAL |
| `proto-evolve.md` | 246 | Protobuf schema evolution | ALWAYS |
| `issue-review.md` | 179 | Review completed issue | NO |
| `project-commit.md` | 177 | Full commit pipeline | NO |
| `issue-prioritize.md` | 158 | Prioritize issue backlog | NO |

### Configuration Files

| File | Purpose |
|------|---------|
| `config/validation_overrides.yml` | Microservice-specific validation (ledger-first, optimistic locking, schema isolation) |
| `skills/event-flow-guard/SKILL.md` | Auto-trigger on RabbitMQ/event changes |
| `headless_prompt.md` | Orchestration prompt for multi-service coordination |
| `settings.local.json` | Explicit permissions (70+ allowed commands) |

---

## Pattern Analysis

### 1. Parallel Agent Integration

**Pattern**: Commands specify WHEN to use parallel agents with rationale.

```markdown
## Parallel Agent Integration

This command ALWAYS uses parallel agents (schema changes are critical).

Execute:
```bash
~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 600 \
  --cursor-model advanced --claude-model opus \
  --analyze "$TARGET_FILE"
```

Consensus scoring:
- >=80%: Auto-proceed with unified recommendation
- 50-79%: Highlight disagreements to user
- <50%: Block and escalate for human review
```

**Insight**: Each command documents:
- Whether parallel agents are used (ALWAYS, CONDITIONAL, NO)
- Model selection (advanced/opus for critical, flash/sonnet for standard)
- Timeout strategy (300-600s based on complexity)
- Consensus thresholds and actions

**Applicability to Manifest**:
✅ Already documented in our templates
🔄 Could add to our command template as a required section

---

### 2. Multi-Phase Commands

**Pattern**: Commands broken into strict phases with validation gates.

Example: `project-commit.md`
1. **Phase 1**: Documentation Generation
2. **Phase 2**: Pull Latest & Resolve Conflicts
3. **Phase 3**: Pre-commit Checks (with retry logic)
4. **Phase 4**: Stage & Commit
5. **Phase 5**: Push

Each phase:
- Must succeed before next phase
- Has specific error recovery (max 2 retries)
- Reports status in final summary table

**Insight**: This is a **state machine approach** to command execution, ensuring:
- Atomic operations (can't skip phases)
- Clear rollback points
- Comprehensive error reporting

**Applicability to Manifest**:
✅ Already have multi-phase example in templates
💡 Could create a "command state machine" pattern document

---

### 3. Domain-Specific Validation

**Pattern**: Commands embed deep domain knowledge.

Example: `migration-check.md`
- Reads canonical RBAC matrix from `infrastructure/postgres/init.sql`
- Validates against service role boundaries
- Checks column existence before migration
- Enforces schema-per-service isolation

```sql
-- VIOLATION: column merchant_logo_url does not exist on ledger.transactions
UPDATE ledger.transactions SET merchant_logo_url = '...'  -- BLOCKED

-- CORRECT: column exists on enrichment.transaction_metadata
UPDATE enrichment.transaction_metadata SET merchant_logo_url = '...'
```

**Insight**: Commands act as **domain-aware linters**, not just generic helpers.

**Applicability to Manifest**:
✅ `validation_overrides.yml` supports this
💡 Could add "domain knowledge embedding" guide to docs

---

### 4. Cross-Service Tracing

**Pattern**: Commands trace data flow across service boundaries.

Example: `pipeline-validate.md`
- Maps event topology (publisher → consumer)
- Maps gRPC topology (server → clients)
- Validates correlation_id propagation through 5 hops
- Checks optimistic locking version handling

**Output Format**:
```
| Event | Exchange | Routing Key | Publisher | Consumer(s) | Payload Proto |
|-------|----------|-------------|-----------|-------------|---------------|
| transaction.created | cookedbooks.events | transaction.created | Ledger | Enrichment, Rules | TransactionCreatedEvent |
```

**Insight**: Commands generate **architectural documentation as a side effect** of validation.

**Applicability to Manifest**:
💡 NEW - Could create "architecture tracing" command template
💡 Could integrate with `docs-diagrams` command

---

### 5. Protobuf Schema Evolution

**Pattern**: Specialized validation for protocol buffer changes.

Example: `proto-evolve.md`
- Field number safety (no reuse)
- Wire-format compatibility checks
- Naming convention validation (buf lint)
- Consumer impact analysis across polyglot services

**Rules Table**:
| Change | Safe? | Action |
|--------|-------|--------|
| Add new field at end | YES | Document in changelog |
| Remove field | ONLY if reserved | Must add `reserved N; reserved "name";` |
| Change field type | NO | BLOCK - wire incompatible |

**Insight**: **Technology-specific validation** (protobuf) embedded in command.

**Applicability to Manifest**:
💡 NEW - Could add similar for GraphQL schema evolution, REST API versioning
💡 Template: "API Evolution Validator" command

---

### 6. Issue Management Workflow

**Pattern**: Full GitHub issue lifecycle automation.

Five interconnected commands:
1. **Triage** (`issue-triage.md`) - Audit/cleanup backlog
2. **Prioritize** (`issue-prioritize.md`) - Score issues by impact/effort
3. **Plan** (`issue-plan.md`) - Design implementation
4. **Process** (`issue-process.md`) - Execute implementation
5. **Review** (`issue-review.md`) - Validate completion

**Workflow**:
```
Triage → Prioritize → Plan → Process → Review → Close
   ↓         ↓         ↓        ↓        ↓
Cleanup    Score    Design   Code    Validate
```

**Insight**: This is a **complete project management system** via commands.

**Applicability to Manifest**:
✅ Already in `templates/github-workflow/` (placeholder)
💡 Could implement the full workflow as a template

---

### 7. Explicit Permissions System

**Pattern**: Fine-grained allow list in `settings.local.json`.

70+ explicit permissions:
```json
{
  "permissions": {
    "allow": [
      "Bash(~/.claude/scripts/parallel_agent.sh:*)",
      "Bash(pytest:*)",
      "Bash(docker compose:*)",
      "WebFetch(domain:www.simplefin.org)",
      ...
    ]
  }
}
```

**Categories**:
- **Testing**: pytest, go test, npm test
- **Build**: docker compose, npm build, go build
- **Git**: git add, git commit, git fetch, git diff
- **GitHub**: gh issue view, gh issue create, gh issue edit
- **Protobuf**: buf lint, buf generate
- **Domain-specific**: gemini CLI, SimpleFin API

**Insight**: **Zero-trust model** - explicit allow list, no wildcards.

**Applicability to Manifest**:
⚠️ NOT CURRENTLY SUPPORTED - Manifest doesn't have per-project permissions
💡 Could document "recommended permissions" for different project types
💡 Could create permission preset templates

---

### 8. Auto-Trigger Skill Pattern

**Pattern**: `event-flow-guard` skill triggers on RabbitMQ changes.

**Trigger Patterns** (60+ patterns):
- Go: `amqp.Publishing`, `channel.Publish`, `channel.Consume`
- Python: `pika.BasicProperties`, `basic_publish`, `basic_consume`
- Infrastructure: `**/events.proto`, `infrastructure/rabbitmq/**`

**Checks**:
1. Routing key alignment (publisher keys match consumer bindings)
2. Payload format consistency (Go PascalCase vs Python snake_case)
3. Ledger-first commit ordering
4. Contract test coverage

**Insight**: **Polyglot-aware validation** that understands language differences.

**Applicability to Manifest**:
✅ Already in `templates/skills/`
💡 Could add "polyglot considerations" section to skill template

---

## What Manifest Can Learn

### Immediately Applicable (Already Templated)

1. ✅ **Auto-trigger skills** - Already have templates
2. ✅ **Validation overrides** - Already documented
3. ✅ **Multi-phase commands** - Already have example (project-commit)
4. ✅ **Parallel agent integration** - Already documented

### New Patterns to Add

#### 1. Command State Machine Pattern

**What**: Commands as explicit state machines with phase gates.

**Template**:
```markdown
## Command Phases

| Phase | Success Criteria | On Failure | Retry |
|-------|-----------------|------------|-------|
| 1. Preparation | Files readable | Abort | No |
| 2. Analysis | No critical issues | Report & continue | Yes (2x) |
| 3. Implementation | Tests pass | Fix & retry | Yes (2x) |
| 4. Validation | Consensus >= 80% | Escalate | No |
```

**File**: `templates/command-state-machine.md`

---

#### 2. Architecture Tracing Commands

**What**: Commands that generate architecture docs as validation side effects.

**Examples**:
- `/trace-events` - Map all event publishers/consumers
- `/trace-grpc` - Map all gRPC server/client calls
- `/trace-database` - Map all schema access patterns

**File**: `templates/commands/trace-architecture.md`

---

#### 3. Technology-Specific Evolution Validators

**What**: Commands for validating schema/API evolution.

**Examples**:
- `/validate-protobuf-evolution` (like cookedbooks)
- `/validate-graphql-evolution` (breaking changes in GraphQL schema)
- `/validate-rest-api-evolution` (API versioning, deprecation)
- `/validate-database-migration` (already have in templates!)

**File**: `templates/commands/api-evolution-validators.md`

---

#### 4. GitHub Issue Workflow

**What**: Full lifecycle management commands.

**Commands**:
- `/issue-triage` - Audit and cleanup
- `/issue-prioritize` - Score by impact/effort
- `/issue-plan` - Design implementation
- `/issue-process` - Execute implementation
- `/issue-review` - Validate completion

**File**: `templates/github-workflow/full-lifecycle.md`

---

#### 5. Permissions Presets

**What**: Recommended permission sets for common project types.

**Presets**:
- `permissions-python-django.json`
- `permissions-node-express.json`
- `permissions-go-microservices.json`
- `permissions-monorepo.json`

**File**: `templates/permissions/` (new directory)

---

## Recommendations for Manifest

### High Priority (Add to Templates)

1. **Command State Machine Pattern**
   - Create: `templates/command-state-machine.md`
   - Document phase gates, retry logic, error recovery
   - Examples: cookedbooks `project-commit.md`

2. **Architecture Tracing Commands**
   - Create: `templates/commands/trace-architecture.md`
   - Show how to generate docs from validation
   - Examples: event topology, gRPC topology

3. **GitHub Issue Workflow (Full)**
   - Complete: `templates/github-workflow/` (currently placeholder)
   - Port cookedbooks issue-* commands
   - Document the full triage → prioritize → plan → process → review flow

4. **Permissions Presets**
   - Create: `templates/permissions/` directory
   - Add presets for Django, Express, Go, monorepo
   - Document how to customize

### Medium Priority (Documentation)

1. **Polyglot Validation Guide**
   - Add: `docs/POLYGLOT_VALIDATION.md`
   - Cover language differences (PascalCase vs snake_case)
   - Show how to write language-aware validation rules

2. **Domain Knowledge Embedding**
   - Add: `docs/DOMAIN_KNOWLEDGE.md`
   - Show how to embed business rules in commands
   - Example: cookedbooks RBAC matrix, schema-per-service

3. **Advanced Command Patterns**
   - Update: `docs/COMMANDS.md`
   - Add sections on:
     - State machines
     - Error recovery strategies
     - Parallel agent decision trees

### Low Priority (Future Enhancements)

1. **Per-Project Permissions** (requires core changes)
   - Currently not supported in Manifest
   - Would need changes to core Claude Code
   - For now: document recommended permissions

2. **Automatic Architecture Documentation**
   - Commands that update docs as side effect
   - Integrate with `/docs-diagrams`
   - Auto-update ARCHITECTURE_DIAGRAMS.md

3. **Cross-Service Validation Framework**
   - For microservices projects
   - Validate contracts between services
   - Detect breaking changes

---

## Immediate Action Items

### 1. Complete GitHub Workflow Templates

**Current**: Placeholder directory
**Target**: Full implementation like cookedbooks

**Tasks**:
- [ ] Port `issue-triage.md` to template
- [ ] Port `issue-prioritize.md` to template
- [ ] Port `issue-plan.md` to template
- [ ] Port `issue-process.md` to template
- [ ] Port `issue-review.md` to template
- [ ] Create workflow README

**Estimate**: 2-3 hours

---

### 2. Create Command State Machine Pattern Doc

**File**: `templates/command-state-machine.md`

**Contents**:
- Phase definition pattern
- Success criteria format
- Error recovery strategies
- Retry logic patterns
- Summary table format

**Example from cookedbooks**: `project-commit.md`

**Estimate**: 1 hour

---

### 3. Create Architecture Tracing Template

**File**: `templates/commands/trace-architecture.md`

**Contents**:
- How to map event flows
- How to map API calls (gRPC, REST, GraphQL)
- How to trace data flow
- Output format examples

**Example from cookedbooks**: `pipeline-validate.md`

**Estimate**: 1-2 hours

---

### 4. Add Permissions Presets

**Directory**: `templates/permissions/`

**Files**:
- `README.md` - How to use presets
- `django-web-app.json`
- `express-api.json`
- `go-microservices.json`
- `monorepo.json`

**Estimate**: 1 hour

---

## Key Takeaways

### What cookedbooks Does Exceptionally Well

1. **Domain knowledge embedding** - Commands understand the business domain
2. **Multi-phase validation** - Strict state machines with error recovery
3. **Cross-service tracing** - Full topology mapping
4. **Explicit permissions** - Zero-trust model with allow lists
5. **Technology-specific validators** - Protobuf, RabbitMQ, PostgreSQL

### What Manifest Can Adopt

1. ✅ **Already adopted**: Orchestration prompts, auto-trigger skills, validation overrides
2. 🔄 **In templates**: Multi-phase commands, API security guard, DB migration guard
3. 💡 **Should add**: State machine pattern, architecture tracing, GitHub workflow, permissions presets
4. 🚀 **Future**: Per-project permissions (needs core support), automatic doc generation

### What Makes Manifest Different

**Manifest**: **Framework** for building orchestration systems
**cookedbooks**: **Implementation** of an orchestration system for a specific project

Manifest provides:
- ✅ Parallel agent infrastructure
- ✅ Template library
- ✅ Documentation framework
- ✅ Bootstrap tooling

cookedbooks uses Manifest to build:
- Domain-specific commands
- Project-specific validation
- Business logic automation

---

## Conclusion

The cookedbooks `.claude` directory is a **reference implementation** of production-grade AI orchestration for a complex microservices system. It demonstrates how Manifest's primitives (parallel agents, skills, validation overrides) can be composed into a complete workflow automation system.

**Recommendation**: Use cookedbooks as a **case study** and **template source** for Manifest documentation and examples.

**Immediate Actions**:
1. Complete GitHub workflow templates
2. Add state machine pattern doc
3. Add architecture tracing template
4. Add permissions presets

**Estimated Effort**: 5-7 hours total to bring all patterns into Manifest templates.
