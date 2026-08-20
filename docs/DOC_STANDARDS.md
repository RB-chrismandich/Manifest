# Documentation Standards

> Diataxis types, line caps, and the linter that enforces them.

## Documentation Standards

All documentation in this repository follows these conventions:

### Required Elements

Every user-facing document MUST include:

- **Title** (H1): Clear, descriptive name
- **Tagline**: One-line description in blockquote
- **Last Updated**: Date in YYYY-MM-DD format
- **Table of Contents**: For documents >100 lines
- **Related Documents**: Links to related docs at bottom

### Code Block Standards

```yaml
# All code blocks MUST specify language
services:
  claude:
    enabled: true  # Good: syntax highlighting works
```

### Link Standards

- Use **relative paths** for internal links: `[Config](configuration/README.md)` ✅
- Avoid absolute URLs for internal docs: `https://github.com/.../CONFIGURATION.md` ❌
- Include link descriptions: `[Configuration Guide](configuration/README.md) - All config options` ✅

### Formatting Standards

- Use **tables** for structured comparisons
- Use **code blocks** for all commands, config snippets, file contents
- Use **blockquotes** (`>`) for important callouts
- Use **bold** for UI elements and emphasis
- Use `code` for file names, commands, config keys

---

---

[← Documentation Hub](README.md)
