# Permissions Presets

> Security-approved permission templates for common project types

**Purpose**: Provide zero-trust permission presets that allow development workflows while blocking dangerous operations.

**Security Model**: Explicit allow list - only explicitly permitted commands can run.

---

## Available Presets

| Preset | Project Type | Use Case |
|--------|--------------|----------|
| `django-web-app.json` | Django Web Application | Python web development with PostgreSQL |
| `express-api.json` | Express.js/Node.js API | JavaScript/TypeScript backend development |
| `go-microservices.json` | Go Microservices | Go services with gRPC, Kubernetes (read-only) |
| `python-monorepo.json` | Python Monorepo | Multi-package Python projects with Poetry |

---

## Quick Start

### 1. Copy Preset to Your Project

```bash
# Copy the appropriate preset
cp templates/permissions/django-web-app.json .claude/settings.local.json

# Or for Express.js
cp templates/permissions/express-api.json .claude/settings.local.json

# Or for Go microservices
cp templates/permissions/go-microservices.json .claude/settings.local.json

# Or for Python monorepo
cp templates/permissions/python-monorepo.json .claude/settings.local.json
```

### 2. Review and Customize

Open `.claude/settings.local.json` and:

- Remove permissions you don't need
- Add project-specific commands
- Update WebFetch domains for your docs

### 3. Test Permissions

```bash
# Try a safe command (should work)
claude run "Run pytest on the test suite"

# Try a dangerous command (should be blocked)
claude run "Install a new package with pip install requests"
```

---

## Permission Structure

### Allow List

Commands in the `allow` array can be executed:

```json
{
  "permissions": {
    "allow": [
      "Bash(pytest:*)",
      "Bash(git status:*)",
      "WebSearch",
      "WebFetch(domain:docs.djangoproject.com)"
    ]
  }
}
```

**Format**: `Tool(command:pattern)`

**Wildcards**:

- `*` - Matches anything
- `pytest:*` - Allows all pytest commands
- `git status:*` - Allows git status with any arguments

### Deny List

Commands in the `deny` array are explicitly blocked:

```json
{
  "permissions": {
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(sudo:*)",
      "Bash(pip install:*)"
    ]
  }
}
```

**Note**: Deny list is for documentation only - commands not in allow list are blocked by default.

---

## What's Allowed in Each Preset

### Django Web App

✅ **Allowed**:

- Testing: `pytest`, `coverage`, `ruff`, `mypy`
- Django commands: `manage.py test`, `makemigrations`, `migrate`, `runserver`
- Docker: `docker compose` (local development)
- Git: All read + write operations
- GitHub: Create PRs/issues
- Pre-commit hooks

❌ **Blocked**:

- `pip install` (use virtual env manually)
- `django-admin` (too powerful)
- `manage.py createsuperuser` (admin account creation)
- `manage.py flush` (deletes all data)
- Production commands: `gunicorn`, `collectstatic`
- Deployment: `kubectl`, `heroku`, cloud CLIs

### Express.js API

✅ **Allowed**:

- Testing: `npm test`, `jest`, `vitest`, `mocha`
- Linting: `eslint`, `prettier`, `tsc`
- Development: `npm run dev`, `npm run build`
- Migrations: Sequelize, Knex, Prisma, TypeORM
- Docker: `docker compose`
- Git: All read + write operations
- GitHub: Create PRs/issues

❌ **Blocked**:

- `npm install` (use `npm ci` or allow explicitly)
- `npm publish` (package publishing)
- Database drops: `sequelize db:drop`, `prisma db reset`
- Production: `pm2`, `forever`
- Deployment: `kubectl`, cloud CLIs
- Docker registry: `docker push`

### Go Microservices

✅ **Allowed**:

- Testing: `go test`, `go vet`, `golangci-lint`
- Build: `go build`, `go run`, `go mod`
- Protobuf: `buf`, `protoc`
- Migrations: `golang-migrate`
- Docker: `docker compose`, `docker build`
- Kubernetes: **Read-only** (`get`, `describe`, `logs`)
- Git: All read + write operations
- GitHub: Create PRs/issues

❌ **Blocked**:

- `go mod tidy` (dependency updates)
- Database operations: `migrate down`, `migrate drop`
- Kubernetes write: `apply`, `delete`, `scale`, `exec`
- Docker registry: `docker push`, `docker tag`
- Cloud providers: `aws`, `gcloud`, `terraform`
- Service mesh: `istioctl`, `linkerd`

### Python Monorepo

✅ **Allowed**:

- Testing: `pytest`, `coverage`, `ruff`, `mypy`, `black`
- Poetry: `poetry show`, `poetry run`, `poetry shell`
- Docker: `docker compose`
- Git: All read + write operations
- GitHub: Create PRs/issues
- Monorepo tools: `nx`, `lerna`, `turborepo`
- Pre-commit hooks

❌ **Blocked**:

- `pip install` (use virtual env)
- `poetry install`, `poetry add` (dependency management)
- `poetry publish` (package publishing)
- Database operations: `dropdb`
- Deployment: `kubectl`, cloud CLIs
- Docker registry: `docker push`

---

## Customization Guide

### Adding Project-Specific Commands

```json
{
  "permissions": {
    "allow": [
      "// Existing permissions...",

      "// ============================================",
      "// Project-Specific Commands",
      "// ============================================",
      "Bash(./scripts/dev-setup.sh:*)",
      "Bash(npm run custom-task:*)",
      "Bash(python scripts/data-import.py:*)"
    ]
  }
}
```

### Adding Custom WebFetch Domains

```json
{
  "permissions": {
    "allow": [
      "WebFetch(domain:docs.mycompany.com)",
      "WebFetch(domain:internal-wiki.example.com)",
      "WebFetch(domain:api.github.com)"
    ]
  }
}
```

### Allowing Deployment in CI/CD

For CI/CD environments, create a separate preset:

```json
{
  "permissions": {
    "allow": [
      "// All development permissions...",

      "// ============================================",
      "// CI/CD Only",
      "// ============================================",
      "Bash(npm install:*)",
      "Bash(docker push:*)",
      "Bash(kubectl apply:*)",
      "Bash(aws s3 sync:*)"
    ]
  }
}
```

---

## Security Best Practices

### 1. Zero-Trust Model

**Principle**: Nothing is allowed unless explicitly permitted.

**Implementation**:

- Start with a restrictive preset
- Add permissions as needed
- Remove unnecessary permissions

### 2. Separate Development and Production

**Development** (`.claude/settings.local.json`):

- Allow testing, linting, local docker
- Block deployments, cloud operations
- Block dangerous database operations

**CI/CD** (separate preset):

- Allow package installation
- Allow docker push
- Allow deployment commands
- Still block system admin commands

### 3. Avoid Wildcards at Tool Level

```json
// BAD - Too permissive
"Bash(*)"

// GOOD - Specific commands only
"Bash(pytest:*)",
"Bash(npm test:*)"
```

### 4. Review Periodically

- Monthly review of permissions
- Remove unused permissions
- Add new project-specific commands
- Check for security advisories

### 5. Version Control

**Commit** `.claude/settings.local.json` to your repository:

- Team uses same permissions
- Changes are reviewed in PRs
- History of permission changes tracked

**Exception**: Don't commit if it contains secrets or internal URLs.

---

## Testing Permissions

### Dry Run Mode

Test if a command would be allowed:

```bash
# This doesn't actually run the command
# Check Claude Code logs to see if it would be permitted
claude run "Would this command work: pip install requests"
```

### Incremental Testing

1. Start with restrictive preset
2. Try your normal workflow
3. Note which commands fail
4. Add specific permissions for those commands
5. Repeat until workflow smooth

### Security Audit

```bash
# Review all allowed commands
jq '.permissions.allow[]' .claude/settings.local.json

# Check for overly permissive patterns
jq '.permissions.allow[]' .claude/settings.local.json | grep "\\*)"

# Count total permissions
jq '.permissions.allow | length' .claude/settings.local.json
```

---

## Common Issues

### Issue: Command Blocked Unexpectedly

**Symptom**: Command should be allowed but is blocked

**Cause**: Pattern doesn't match exactly

**Solution**:

```json
// Check exact command being run
// If running: pytest --cov --cov-report=html
// Pattern must be: "Bash(pytest:*)"
// NOT: "Bash(pytest)"
```

### Issue: Too Many Permissions Needed

**Symptom**: Keep adding permissions, list growing large

**Cause**: May need a broader pattern or reconsider workflow

**Solution**:

```json
// Instead of:
"Bash(pytest tests/unit:*)",
"Bash(pytest tests/integration:*)",
"Bash(pytest tests/e2e:*)"

// Use:
"Bash(pytest:*)"
```

### Issue: Unclear What Commands Are Needed

**Symptom**: Don't know what to allow

**Solution**:

1. Start with a preset
2. Try your workflow
3. Check Claude Code logs for blocked commands
4. Add specific commands that are safe
5. Repeat

---

## Examples by Project Type

### Django + PostgreSQL + Docker

```json
{
  "permissions": {
    "allow": [
      "Bash(pytest:*)",
      "Bash(python manage.py:*)",
      "Bash(docker compose:*)",
      "Bash(git:*)",
      "Bash(gh:*)",
      "Bash(~/.claude/scripts/parallel_agent.py:*)",
      "WebSearch",
      "WebFetch(domain:docs.djangoproject.com)"
    ]
  }
}
```

### Express + TypeScript + Kubernetes (read-only)

```json
{
  "permissions": {
    "allow": [
      "Bash(npm test:*)",
      "Bash(npm run:*)",
      "Bash(npx:*)",
      "Bash(kubectl get:*)",
      "Bash(kubectl logs:*)",
      "Bash(kubectl describe:*)",
      "Bash(git:*)",
      "Bash(gh:*)",
      "WebSearch"
    ]
  }
}
```

### Go + gRPC + Protobuf

```json
{
  "permissions": {
    "allow": [
      "Bash(go test:*)",
      "Bash(go build:*)",
      "Bash(buf:*)",
      "Bash(protoc:*)",
      "Bash(docker compose:*)",
      "Bash(git:*)",
      "Bash(gh:*)",
      "WebSearch",
      "WebFetch(domain:grpc.io)",
      "WebFetch(domain:buf.build)"
    ]
  }
}
```

---

## Frequently Asked Questions

**Q: Should I commit .claude/settings.local.json?**
A: Yes, if it doesn't contain secrets. This ensures team consistency.

**Q: Can I have multiple presets?**
A: Yes. Create `settings.dev.json`, `settings.ci.json`, etc. Copy the appropriate one to `settings.local.json`.

**Q: What if I need sudo?**
A: Create a separate preset for that specific operation, or run it manually outside Claude Code.

**Q: How do I allow all git commands?**
A: Use `"Bash(git:*)"` - this allows any git subcommand.

**Q: Can I use environment variables?**
A: No, permissions don't support environment variable expansion.

**Q: What about dangerous commands I actually need?**
A: Add them to a separate "admin" preset, use only when needed, never commit to repo.

**Q: How specific should patterns be?**
A: As specific as practical. Prefer `pytest tests/` over `pytest:*` if you only run specific tests.

**Q: Can permissions change per-branch?**
A: Yes, if `.claude/settings.local.json` is in version control.

---

## Related Documentation

- [Configuration Guide](../../configuration/README.md) - All configuration options
- [Commands Guide](../../COMMANDS.md) - Building custom commands
- [Security Best Practices](../../docs/SECURITY.md) - (Coming soon)

---

## Contributing Presets

To contribute a new preset:

1. Create `[framework]-[type].json`
2. Follow zero-trust model (explicit allow list)
3. Test with real project
4. Add to this README
5. Submit PR

**Naming convention**: `[framework]-[type].json`

- `django-web-app.json`
- `rails-api.json`
- `spring-boot-service.json`
- `rust-cli-tool.json`

---

## License

Same as Manifest project (see root LICENSE file)
