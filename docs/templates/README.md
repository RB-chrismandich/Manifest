# Templates Directory

> Advanced patterns and examples for extending Manifest

This directory contains templates and examples for:

- Settings and permissions
- Orchestration prompts
- Auto-trigger skills
- Validation overrides
- GitHub workflow automation

---

## Directory Structure

```text
templates/
├── README.md                           # This file
├── settings-low-risk.json              # Low-risk auto-executable permissions
├── orchestration_prompt.md             # Template for multi-agent orchestration
├── permissions/                        # Project-specific permission templates
│   ├── django-web-app.json             # Django development permissions
│   ├── express-api.json                # Express.js API permissions
│   ├── go-microservices.json           # Go microservices permissions
│   └── python-monorepo.json            # Python monorepo permissions
├── skills/                             # Auto-trigger skill examples
│   ├── api-security-guard/             # API endpoint security validation
│   └── database-migration-guard/       # Database schema change safety
├── validation-overrides/               # Framework-specific validation rules
│   ├── django-security.yml             # Django security checks
│   └── express-security.yml            # Express.js/Node.js security checks
└── github-workflow/                    # (Coming soon) GitHub issue management
```

---

## Settings Templates

### Low-Risk Auto-Executable Permissions

**File**: `settings-low-risk.json`

**Purpose**: Pre-configured permissions for low-risk commands that Claude can auto-execute
without prompting, minimizing environmental impact while enabling efficient development workflows.

**Installation**:

```bash
# Copy to Claude Code settings
cp templates/settings-low-risk.json ~/.claude/settings.json

# Or merge with existing settings
jq -s '.[0] * .[1]' ~/.claude/settings.json templates/settings-low-risk.json > ~/.claude/settings.json.new
mv ~/.claude/settings.json.new ~/.claude/settings.json
```

**Included Permissions** (200+ safe commands):

| Category | Examples | Risk Level |
|----------|----------|------------|
| Web Access | WebFetch (GitHub, docs, npm, AWS), WebSearch | Low - Read-only |
| File Operations | Read, ls, cat, head, tail, grep, find | Low - Read-only |
| Git Operations | status, diff, log, fetch, pull, add, checkout | Low - Local only |
| GitHub CLI | issue/pr view, repo view, run view | Low - Read-only |
| Python Tools | pytest, mypy, ruff, bandit, pip list/show | Low - Analysis |
| Pre-commit | pre-commit run --all-files | Low - Local checks |
| Docker | ps, images, logs, stats | Low - Inspection |
| AWS | Read-only describe/list operations | Low - No modifications |
| Parallel Agents | ~/.claude/scripts/parallel_agent.py | Low - Analysis |

**Excluded** (requires prompt):

- Destructive git operations (reset --hard, clean -f, push --force)
- File modifications (rm without -f, destructive mv/cp)
- AWS write operations (create, update, delete)
- System-level changes (sudo, systemctl start/stop)
- Package installations (npm install, pip install, brew install)
- Git commits and pushes (requires explicit user request)

**Hooks**:

- **PreToolUse (Skill)**: Runs parallel agent pre-analysis (180s timeout)
- **PostToolUse (Bash)**: Post-execution validation (10s timeout)

**Project-Specific Customization**:

```bash
# Start with low-risk template
cp templates/settings-low-risk.json my-project-settings.json

# Add project-specific permissions
jq '.permissions.allow += ["Bash(make deploy-staging:*)"]' my-project-settings.json > temp.json
mv temp.json my-project-settings.json

# Apply
cp my-project-settings.json ~/.claude/settings.json
```

### Project-Specific Permission Templates

**Location**: `permissions/`

Pre-configured permission sets for common project types:

- **django-web-app.json**: Django development with pytest, migrations, runserver
- **express-api.json**: Node.js/Express with npm, debugging, API testing
- **go-microservices.json**: Go services with Docker, Kubernetes, protobuf
- **python-monorepo.json**: Python monorepo with Poetry, tox, submodules

**Usage**:

```bash
# Apply permission template
jq -s '.[0] * .[1]' \
  templates/settings-low-risk.json \
  templates/permissions/django-web-app.json \
  > ~/.claude/settings.json
```

---

## Orchestration Prompt Template

**File**: `orchestration_prompt.md`

**Purpose**: Create multi-agent workflows that coordinate sub-agents, parallel tools, and complex validation.

**When to use**:

- Multi-service architectures (microservices, monorepos)
- Complex workflows requiring multiple validation phases
- Projects needing sub-agent delegation

**How to use**:

1. Copy `orchestration_prompt.md` to your project's `.claude/headless_prompt.md`
2. Replace all `[PLACEHOLDERS]` with your project specifics
3. Test with a simple multi-component change

**Example projects**:

- Microservices with event-driven communication
- Monorepos with shared libraries
- Multi-language codebases

---

## Auto-Trigger Skills

**Location**: `skills/`

Auto-trigger skills activate when Claude detects specific code patterns, providing inline feedback without blocking workflow.

### API Security Guard

**File**: `skills/api-security-guard/SKILL.md`

**Triggers on**:

- HTTP endpoint modifications (Express, Django, FastAPI, Flask, Go, Rails)
- Request handler changes
- Authentication/authorization middleware

**Validates**:

- Input validation (schemas, sanitization)
- Authentication (JWT, sessions)
- Authorization (IDOR prevention, ownership checks)
- Rate limiting (login, password reset, resource creation)
- CSRF protection (state-changing endpoints)
- SQL injection protection (parameterized queries)

**How to use**:

1. Copy `skills/api-security-guard/` to `.claude/skills/`
2. Customize trigger patterns for your framework
3. Add to `.claude/skills/` directory in your project

### Database Migration Guard

**File**: `skills/database-migration-guard/SKILL.md`

**Triggers on**:

- Database migration files (Django, Rails, Alembic, Sequelize, etc.)
- Model/schema changes

**Validates**:

- Breaking vs non-breaking changes
- Backwards compatibility
- Data migration strategy
- Index creation (CONCURRENT for large tables)
- Constraint safety (NOT VALID pattern)
- Rollback strategy

**How to use**:

1. Copy `skills/database-migration-guard/` to `.claude/skills/`
2. Adjust `large_table_threshold` in config
3. Add framework-specific patterns if needed

---

## Validation Overrides

**Location**: `validation-overrides/`

Project-specific validation rules that extend the base `~/.claude/config/validation_criteria.yml`.

> **Status**: these templates are a design sketch — no code currently loads a
> `validation_overrides.yml` file (see issue #325). For working per-command
> customization use the `command_overrides` section of
> `validation_criteria.yml` (documented in docs/CONFIGURATION.md). The
> templates below catalog the checks worth adopting if/when the loader is
> implemented.

### Django Security

**File**: `validation-overrides/django-security.yml`

**Tier 1 (Critical) Checks**:

- CSRF protection enabled
- No raw SQL with string interpolation
- Template output auto-escaped
- SECRET_KEY from environment
- DEBUG=False in production

**Tier 2 (Quality) Checks**:

- Model field validators
- Permission decorators on views
- Reversible migrations
- QuerySet optimization (select_related, prefetch_related)
- Test coverage

**How to use**:

1. Copy to your project: `.claude/config/validation_overrides.yml`
2. Customize checks for your needs
3. Reference in your project's CLAUDE.md

### Express.js/Node.js Security

**File**: `validation-overrides/express-security.yml`

**Tier 1 (Critical) Checks**:

- Input validation (Joi, Zod)
- SQL injection prevention
- Authentication middleware
- Helmet.js security headers
- Rate limiting on auth endpoints

**Tier 2 (Quality) Checks**:

- Error handling middleware
- Async error handling
- CORS configuration
- Environment variables
- Logging

**TypeScript-specific**:

- Strict mode enabled
- Request/Response typing

**How to use**:

1. Copy to `.claude/config/validation_overrides.yml`
2. Enable/disable checks as needed
3. Add exemptions for test files, migrations, etc.

---

## Creating Your Own

### Auto-Trigger Skill

1. Create directory: `.claude/skills/your-skill-name/`
2. Create `SKILL.md` with frontmatter:

   ```markdown
   ---
   name: your-skill-name
   description: |
     Auto-trigger when detecting [PATTERN].
     Validates [WHAT] without blocking user flow.
   ---
   ```

3. Define trigger patterns (file paths, code patterns)
4. Define validation checks
5. Test by modifying matching files

### Validation Override

1. Create `.claude/config/validation_overrides.yml`
2. Define `project_tier1` (critical) and `project_tier2` (quality) checks
3. Use patterns (regex) to detect issues
4. Add exemptions for test files, generated code, etc.
5. Test with `/refactor-python` or `--validate` flag

---

## Integration with Manifest

These templates integrate with Manifest's core features:

### Parallel Agent Orchestration

```bash
# Use in orchestration prompts
~/.claude/scripts/parallel_agent.py --json --timeout 600 \
  --analyze "Check cross-service impact of migration"
```

### Validation Framework

```bash
# Validate with custom overrides
~/.claude/scripts/parallel_agent.py --json --validate \
  --review /absolute/path/to/file
```

### Command System

Use in custom commands:

```markdown
## Phase 3: Validation

Run validation with overrides:
```bash
~/.claude/scripts/parallel_agent.py --validate --review $CHANGED_FILE
```

```text

---

## Examples by Project Type

| Project Type | Orchestration | Skills | Validation |
|--------------|--------------|--------|------------|
| **Django Web App** | Basic | API Security | django-security.yml |
| **Express.js API** | Basic | API Security | express-security.yml |
| **Microservices** | Advanced (cookedbooks pattern) | API, DB Migration | Framework-specific |
| **Monorepo** | Advanced | Multiple | Combined overrides |

---

## Contributing Templates

To add a new template:

1. Create the template file(s)
2. Add usage documentation
3. Include example for common use case
4. Test with a real project
5. Submit PR to Manifest repository

---

## Related Documentation

- [Main Documentation](../README.md)
- [Configuration Guide](../CONFIGURATION.md)
- [Skills Documentation](../../.skillshare/skills/)
- [Validation Criteria](../../configs/claude/config/validation_criteria.yml)
- [Parallel Agent Guide](../../configs/claude/CLAUDE.md)

---

## License

Same as Manifest project (see root LICENSE file)
