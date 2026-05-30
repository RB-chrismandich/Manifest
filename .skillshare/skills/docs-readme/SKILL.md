---
name: docs-readme
description: |
  Analyze and improve repository README documentation using code-derived facts,
  clear structure, and practical onboarding guidance.
---

# README Improvement Command

Analyze the project structure and improve or create comprehensive README documentation following best practices.

## Task

You are a documentation expert improving the README.md for the project. Your goals are to:

1. Analyze the codebase to understand its actual functionality
2. Identify missing, outdated, or incomplete README sections
3. Generate accurate, well-structured documentation
4. Ensure all information is derived from actual code, not assumptions
5. Follow established README best practices and formatting conventions

## Instructions

### Step 1: Gather Project Context

Read these files to understand the project:

- Read existing documentation: README.md, AGENTS.md, CLAUDE.md
- Check for dependencies: requirements.txt, package.json, pyproject.toml
- Scan key directories with Glob: src/**/*.py, lib/**/*.ts, tests/**/*

### Step 2: Analyze Current README State

Evaluate the existing README.md (if present) for:

- **Missing sections**: Compare against the standard sections list below
- **Outdated information**: Config defaults, feature lists, version numbers
- **Broken links**: Internal doc references, external URLs
- **Inconsistent formatting**: Code blocks, tables, headings
- **Inaccurate descriptions**: Features that don't match actual code

### Step 3: Generate Improved Content

For each section that needs improvement, follow these guidelines:

#### Project Title & Description (1-3 lines)

- Extract purpose from AGENTS.md or main module docstrings
- One sentence explaining what it does and why it's useful
- Avoid marketing language - be factual

#### Key Features (5-10 bullets)

- Scan src/ for actual capabilities
- One line per feature, focus on user benefits

#### Quick Start (4-6 steps max)

- Minimum steps to get running
- Use actual commands from setup scripts or AGENTS.md
- Include config setup and run command

#### Requirements

- Extract from requirements.txt or package.json
- Note language version requirements
- List external services needed

#### Project Structure

- Generate tree from actual directory structure
- Add one-line comments explaining each key file
- Group related files logically

#### Configuration

- Extract ALL options from config files
- Use tables: Key | Default | Description
- Include example YAML/JSON snippets

#### Usage/Workflow

- Describe the actual execution flow from main entry point
- Include sample output or log examples
- Reference AGENTS.md workflow sections

#### Troubleshooting

- Use table format: Issue | Fix
- Extract common errors from code (try/except blocks)
- Include actual error messages users might see

#### Testing

- List actual test commands that work
- Document test environment variables

### Step 4: Validate and Format

Before finalizing:

1. **Verify all links**: Check that linked files exist
2. **Test code blocks**: Ensure commands are correct
3. **Check table alignment**: Proper markdown table syntax
4. **Consistent style**: Same heading levels, bullet styles

## Standard README Sections

| Section | Purpose | Source Files |
|---------|---------|--------------|
| Title & Description | Project identity | AGENTS.md, main module docstring |
| Key Features | Capability overview | src/ analysis |
| Quick Start | Get running fast | Setup scripts |
| Requirements | Prerequisites | requirements.txt, package.json |
| Project Structure | Code organization | Directory tree |
| Configuration | All options | config/ files |
| Usage/Workflow | How it works | main entry point |
| Troubleshooting | Common issues | Error handling code |
| Testing | Run tests | tests/ directory |

## Formatting Standards

- **Headings**: Use `##` for main sections, `###` for subsections
- **Code blocks**: Always specify language (`bash`, `yaml`, `python`)
- **Tables**: Use for configuration options and troubleshooting
- **Links**: Relative paths for internal docs (`[Guide](docs/GUIDE.md)`)
- **Separators**: Use `---` between major sections

## Output Format

Present your improvements as:

1. **Summary of changes**: What sections were added/updated
2. **Full updated README**: Complete markdown ready to save
3. **Validation notes**: Any issues found (broken links, missing info)

## Notes

- **Accuracy over completeness**: Only document what actually exists in the code
- **Preserve custom content**: Keep project-specific sections the user added
- **Update defaults**: Ensure all config defaults match actual code
- **Link validation**: Every `[text](path)` should point to a real file
- **No assumptions**: If information isn't in the code, note it as "TODO" rather than guessing
