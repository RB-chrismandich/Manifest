# Manifest Extension Implementation Plan
**Based on**: cookedbooks/.claude analysis
**Goal**: Extend Manifest with production-grade patterns from cookedbooks
**Total Effort**: 12-15 hours across 4 phases

---

## Overview

Extend Manifest with battle-tested patterns from cookedbooks:
1. Command state machine pattern
2. Complete GitHub issue workflow
3. Architecture tracing commands
4. Permissions presets

**Success Criteria**:
- ✅ Users can build multi-phase commands with error recovery
- ✅ Users can automate full GitHub issue lifecycle
- ✅ Users can trace architecture (events, APIs, data flow)
- ✅ Users have security-approved permission templates

---

## Phase 1: Command State Machine Pattern
**Priority**: CRITICAL
**Effort**: 2-3 hours
**Dependencies**: None
**Value**: Foundation for all advanced commands

### Deliverables

1. **Template Document**
   - File: `templates/patterns/command-state-machine.md`
   - Contents:
     - State machine definition format
     - Phase gate patterns
     - Error recovery strategies
     - Retry logic examples
     - Summary table templates
   - Reference: cookedbooks `project-commit.md`

2. **Example Command**
   - File: `templates/commands/full-deployment-pipeline.md`
   - Demonstrates:
     - 5-phase deployment (test → build → validate → deploy → verify)
     - Retry logic (2x per phase)
     - Rollback on failure
     - Summary table output

3. **Documentation Update**
   - File: `docs/COMMANDS.md`
   - Add section: "Building State Machine Commands"
   - Cross-reference: templates/patterns/command-state-machine.md

### Success Criteria

- [ ] Template document created with all patterns
- [ ] Example command demonstrates all features
- [ ] Documentation explains when/how to use
- [ ] README updated with link to new pattern

### Tasks

1. Create `templates/patterns/` directory
2. Write `command-state-machine.md` template
3. Create `full-deployment-pipeline.md` example
4. Update `docs/COMMANDS.md` with new section
5. Add to `templates/README.md` index

---

## Phase 2: GitHub Issue Workflow Templates
**Priority**: HIGH
**Effort**: 4-5 hours
**Dependencies**: Phase 1 (state machine pattern)
**Value**: Complete project management via Claude

### Deliverables

1. **Issue Triage Command**
   - File: `templates/github-workflow/issue-triage.md`
   - Purpose: Audit open issues, detect duplicates, close stale
   - Reference: cookedbooks `issue-triage.md` (289 lines)
   - Features:
     - Duplicate detection (title similarity, body overlap)
     - Stale issue detection (>90 days, no activity)
     - File existence validation (close if referenced files deleted)
     - Auto-close with `--close-stale` flag

2. **Issue Prioritize Command**
   - File: `templates/github-workflow/issue-prioritize.md`
   - Purpose: Score issues by impact × feasibility
   - Reference: cookedbooks `issue-prioritize.md` (158 lines)
   - Features:
     - Impact scoring (user-facing, performance, security)
     - Feasibility scoring (effort estimate, complexity)
     - Priority matrix output
     - Label application (high-priority, low-hanging-fruit)

3. **Issue Plan Command**
   - File: `templates/github-workflow/issue-plan.md`
   - Purpose: Design implementation strategy
   - Reference: cookedbooks `issue-plan.md` (387 lines)
   - Features:
     - Cross-service impact analysis
     - Multi-phase implementation plan
     - Dependency identification
     - Test strategy

4. **Issue Process Command**
   - File: `templates/github-workflow/issue-process.md`
   - Purpose: Execute implementation with sub-agents
   - Reference: cookedbooks `issue-process.md` (404 lines)
   - Features:
     - Sub-agent delegation per service
     - Parallel agent validation (>=80% consensus)
     - Test execution per phase
     - Progress tracking

5. **Issue Review Command**
   - File: `templates/github-workflow/issue-review.md`
   - Purpose: Validate completion before closing
   - Reference: cookedbooks `issue-review.md` (179 lines)
   - Features:
     - Acceptance criteria verification
     - Test coverage check
     - Documentation completeness
     - Auto-close with label if all pass

6. **Workflow README**
   - File: `templates/github-workflow/README.md`
   - Purpose: Explain the full lifecycle
   - Contents:
     - Workflow diagram (triage → prioritize → plan → process → review)
     - When to use each command
     - Integration with GitHub Projects
     - Customization guide

### Success Criteria

- [ ] All 5 issue commands ported and adapted for general use
- [ ] Workflow README explains full lifecycle
- [ ] Commands use state machine pattern from Phase 1
- [ ] Commands integrate with parallel agents appropriately
- [ ] Examples for monorepo, microservices, web app

### Tasks

1. Port `issue-triage.md` (remove cookedbooks-specific logic)
2. Port `issue-prioritize.md` (generic scoring matrix)
3. Port `issue-plan.md` (generic architecture patterns)
4. Port `issue-process.md` (generic sub-agent delegation)
5. Port `issue-review.md` (generic validation)
6. Create workflow README with diagram
7. Add examples for 3 project types
8. Update main `templates/README.md`

---

## Phase 3: Architecture Tracing Commands
**Priority**: MEDIUM
**Effort**: 3-4 hours
**Dependencies**: Phase 1 (state machine pattern)
**Value**: Generate docs from validation

### Deliverables

1. **Event Topology Tracer**
   - File: `templates/commands/trace-events.md`
   - Purpose: Map all event publishers → consumers
   - Reference: cookedbooks `pipeline-validate.md` (event topology section)
   - Supports:
     - RabbitMQ (Go pika, Python pika)
     - Kafka (Go sarama, Python kafka-python)
     - Cloud Pub/Sub (GCP)
   - Output: Markdown table + Mermaid diagram

2. **API Topology Tracer**
   - File: `templates/commands/trace-api.md`
   - Purpose: Map all API server → client calls
   - Supports:
     - gRPC (Go, Python, Node.js)
     - REST (Express, Django, FastAPI, Go net/http)
     - GraphQL (Apollo, graphql-go)
   - Output: Markdown table + Mermaid diagram

3. **Database Access Tracer**
   - File: `templates/commands/trace-database.md`
   - Purpose: Map all schema access patterns
   - Supports:
     - PostgreSQL (Django ORM, SQLAlchemy, Go database/sql)
     - MySQL (Sequelize, GORM)
     - MongoDB (Mongoose, Go mongo-driver)
   - Output: Schema ownership matrix + Mermaid ER diagram

4. **Architecture Tracing Guide**
   - File: `docs/ARCHITECTURE_TRACING.md`
   - Contents:
     - When to trace (new service, refactoring, onboarding)
     - How to interpret outputs
     - Integration with `/docs-diagrams`
     - Auto-update workflows

### Success Criteria

- [ ] All 3 tracing commands created
- [ ] Each supports 3+ technology stacks
- [ ] Output includes both tables and diagrams
- [ ] Guide explains integration with existing commands
- [ ] Examples for microservices, monolith, monorepo

### Tasks

1. Create `trace-events.md` (RabbitMQ, Kafka, Pub/Sub)
2. Create `trace-api.md` (gRPC, REST, GraphQL)
3. Create `trace-database.md` (PostgreSQL, MySQL, MongoDB)
4. Create `docs/ARCHITECTURE_TRACING.md` guide
5. Integrate with `/docs-diagrams` command
6. Add examples for 3 architecture patterns
7. Update `templates/README.md`

---

## Phase 4: Permissions Presets
**Priority**: MEDIUM
**Effort**: 2-3 hours
**Dependencies**: None
**Value**: Security best practices

### Deliverables

1. **Django Web App Preset**
   - File: `templates/permissions/django-web-app.json`
   - Permissions:
     - pytest, python manage.py test
     - python manage.py migrate
     - docker-compose (for dev DB)
     - git operations
     - Pre-commit hooks
   - Excludes: django-admin (dangerous), rm -rf, production commands

2. **Express.js API Preset**
   - File: `templates/permissions/express-api.json`
   - Permissions:
     - npm test, npm run build
     - docker-compose
     - git operations
     - Sequelize migrations
   - Excludes: npm publish, production deployment

3. **Go Microservices Preset**
   - File: `templates/permissions/go-microservices.json`
   - Permissions:
     - go test, go build
     - docker-compose, docker exec
     - buf (protobuf)
     - kubectl (read-only)
     - git operations
   - Excludes: kubectl apply/delete, docker push, production

4. **Python Monorepo Preset**
   - File: `templates/permissions/python-monorepo.json`
   - Permissions:
     - pytest, ruff, mypy
     - poetry, pip
     - docker-compose
     - git operations
   - Excludes: pip install (system-wide), production commands

5. **Permissions Guide**
   - File: `templates/permissions/README.md`
   - Contents:
     - How to use presets (copy to .claude/settings.local.json)
     - How to customize (add/remove permissions)
     - Security considerations (zero-trust model)
     - Wildcard usage (when safe, when dangerous)
     - Testing permissions (dry-run mode)

### Success Criteria

- [ ] 4 preset files created
- [ ] Each preset follows zero-trust model
- [ ] README explains how to use and customize
- [ ] Examples show safe vs unsafe patterns
- [ ] Integration with bootstrap process

### Tasks

1. Create `templates/permissions/` directory
2. Create `django-web-app.json` with comments
3. Create `express-api.json` with comments
4. Create `go-microservices.json` with comments
5. Create `python-monorepo.json` with comments
6. Create permissions README
7. Add "Security" section to main README
8. Update `docs/CONFIGURATION.md` (reference presets)

---

## Phase 5: Integration & Documentation
**Priority**: HIGH
**Effort**: 2-3 hours
**Dependencies**: Phases 1-4 complete
**Value**: Discoverability and usability

### Deliverables

1. **Updated Main README**
   - Add "Advanced Patterns" section
   - Link to state machine pattern
   - Link to GitHub workflow
   - Link to architecture tracing

2. **Updated docs/README.md**
   - Add links to new docs:
     - ARCHITECTURE_TRACING.md
     - COMMANDS.md (updated)
     - CONFIGURATION.md (updated)

3. **Updated templates/README.md**
   - Add patterns/ section
   - Update github-workflow/ section
   - Update commands/ section
   - Add permissions/ section

4. **Quick Start Examples**
   - File: `examples/quick-start/`
   - Django project setup (10 min)
   - Express.js project setup (10 min)
   - Go microservices setup (15 min)

5. **Video Tutorial Scripts**
   - File: `docs/tutorials/`
   - Script: "Building Your First State Machine Command"
   - Script: "Automating GitHub Issues"
   - Script: "Tracing Your Architecture"

### Success Criteria

- [ ] Main README clearly shows new capabilities
- [ ] All docs cross-reference correctly
- [ ] Quick start examples work end-to-end
- [ ] Tutorial scripts are ready for recording

### Tasks

1. Update main README.md
2. Update docs/README.md
3. Update templates/README.md
4. Create examples/quick-start/ directory
5. Create 3 quick start examples
6. Create docs/tutorials/ directory
7. Write 3 tutorial scripts

---

## Implementation Order

### Week 1 (Core Patterns)
1. Phase 1: Command State Machine Pattern (2-3 hours)
2. Phase 4: Permissions Presets (2-3 hours)

**Why**: Foundation + security best practices

### Week 2 (High-Value Features)
3. Phase 2: GitHub Issue Workflow (4-5 hours)

**Why**: Most requested feature

### Week 3 (Advanced Features)
4. Phase 3: Architecture Tracing (3-4 hours)

**Why**: Valuable but advanced

### Week 4 (Polish)
5. Phase 5: Integration & Documentation (2-3 hours)

**Why**: Make it discoverable

---

## Success Metrics

Track these before/after:

| Metric | Before | Target |
|--------|--------|--------|
| Template patterns | 3 | 7+ |
| GitHub workflow commands | 0 (placeholder) | 5 (complete) |
| Architecture commands | 1 (docs-diagrams) | 4 (+ 3 tracers) |
| Permission presets | 0 | 4 |
| Tutorial examples | 0 | 3 |
| Documentation pages | 6 | 10 |

---

## Risk Mitigation

### Risk: Commands too cookedbooks-specific

**Mitigation**:
- Generalize all service/schema references
- Add "customization" section to each command
- Provide examples for 3+ project types

### Risk: Overwhelming users with complexity

**Mitigation**:
- Clear "Basic → Advanced" progression in docs
- Quick start examples for common cases
- "When to use this" guidance in each template

### Risk: Maintenance burden

**Mitigation**:
- Use templates, not hardcoded commands
- Document customization points clearly
- Test with real projects before release

---

## Testing Plan

### Phase 1 Testing
- [ ] Create a real multi-phase command
- [ ] Test error recovery (forced failures)
- [ ] Verify retry logic works
- [ ] Check summary table output

### Phase 2 Testing
- [ ] Run issue-triage on real repo
- [ ] Test duplicate detection
- [ ] Test stale issue detection
- [ ] Run full workflow (triage → review)

### Phase 3 Testing
- [ ] Trace events in RabbitMQ project
- [ ] Trace APIs in gRPC project
- [ ] Trace database in Django project
- [ ] Verify diagram generation

### Phase 4 Testing
- [ ] Apply Django preset to Django project
- [ ] Apply Express preset to Node project
- [ ] Verify permissions block dangerous commands
- [ ] Test customization workflow

---

## Rollout Strategy

### Stage 1: Internal Testing (Week 1)
- Implement Phase 1 + Phase 4
- Test with Manifest itself
- Gather feedback from cookedbooks

### Stage 2: Early Access (Week 2-3)
- Implement Phase 2 + Phase 3
- Test with 2-3 real projects
- Iterate based on feedback

### Stage 3: Public Release (Week 4)
- Complete Phase 5 (integration)
- Announce in README
- Create tutorial videos

### Stage 4: Post-Release (Week 5+)
- Monitor GitHub issues
- Add more permission presets
- Add more architecture tracer examples

---

## Future Enhancements (Beyond Scope)

### Not in This Plan

1. **Per-Project Permission System** (requires core Claude Code changes)
2. **Automatic Doc Updates** (complex, needs file watching)
3. **Visual Workflow Builder** (requires UI)
4. **Command Marketplace** (requires hosting infrastructure)

### Could Add Later

1. **More permission presets** (Ruby on Rails, Spring Boot, etc.)
2. **More architecture tracers** (Redis, Elasticsearch, etc.)
3. **CI/CD integration commands** (GitHub Actions, GitLab CI)
4. **Monitoring/observability commands** (trace logs, metrics)

---

## Appendix: cookedbooks Reference Mapping

| cookedbooks File | Manifest Equivalent | Status |
|-----------------|---------------------|--------|
| `project-commit.md` | `templates/patterns/command-state-machine.md` | Phase 1 |
| `issue-triage.md` | `templates/github-workflow/issue-triage.md` | Phase 2 |
| `issue-prioritize.md` | `templates/github-workflow/issue-prioritize.md` | Phase 2 |
| `issue-plan.md` | `templates/github-workflow/issue-plan.md` | Phase 2 |
| `issue-process.md` | `templates/github-workflow/issue-process.md` | Phase 2 |
| `issue-review.md` | `templates/github-workflow/issue-review.md` | Phase 2 |
| `pipeline-validate.md` | `templates/commands/trace-events.md` | Phase 3 |
| `migration-check.md` | Already in templates (database-migration-guard) | Done |
| `proto-evolve.md` | Could add as advanced example | Future |
| `validation_overrides.yml` | Already in templates | Done |
| `event-flow-guard/SKILL.md` | Already in templates | Done |
| `settings.local.json` | `templates/permissions/*.json` | Phase 4 |

---

## Notes

- All cookedbooks-specific references (ledger, enrichment, rules schemas) will be generalized
- Examples will cover Django, Express, Go microservices
- All templates include "How to Customize" section
- Focus on 80% use cases, document edge cases
