# Best Practices & Templates

> Conventions, FAQ, contributing, and the complete command template.

## Best Practices

### 1. Clear Documentation

- **Description**: Short, action-oriented
- **Instructions**: Step-by-step, no ambiguity
- **Examples**: Show common use cases

### 2. Error Messages

- **Actionable**: Tell user how to fix
- **Specific**: What went wrong
- **Formatted**: Use ❌ ✅ ⚠️ for visibility

### 3. Tool Selection

- **Bash**: Use for git, docker, npm, system commands
- **Read/Glob/Grep**: Use for file operations
- **Edit/Write**: Minimize use, prefer Bash tools when possible
- **Task**: Use for sub-agent delegation

### 4. Validation

- **Input validation**: Check arguments early
- **Precondition checks**: Verify state before executing
- **Post-condition checks**: Verify operation succeeded

### 5. Progress Feedback

- **Start of phase**: "Starting Phase 2: Build Artifacts..."
- **During phase**: Show command output
- **End of phase**: "✅ Phase 2 complete (3m 42s)"
- **Final summary**: Table of all phases

---

## Related Documentation

- [Command State Machine Pattern](../templates/patterns/command-state-machine.md) - Detailed pattern guide
- [Full Deployment Pipeline](../templates/commands/full-deployment-pipeline.md) - Complete example
- [GitHub Workflow Commands](../templates/commands/github-workflow/) - Issue management commands
- [Configuration Guide](../configuration/README.md) - Parallel agent settings
- [Troubleshooting](../troubleshooting/README.md) - Common command issues
- [SkillClaw](.././SKILLCLAW.md) - Session capture, skill evolution, and `/skill-evolve` usage

---

## Contributing Commands

To contribute a command to Manifest:

1. Create command in `templates/commands/`
2. Follow structure guidelines above
3. Test with multiple projects
4. Add to `templates/README.md`
5. Submit PR to GitHub

**Command checklist**:

- [ ] Clear description
- [ ] Frontmatter complete
- [ ] Instructions step-by-step
- [ ] Error handling included
- [ ] Examples provided
- [ ] Tested on real project

---

## FAQ

**Q: How do I invoke a command?**
A: Type `/command-name` in Claude Code (without the .md extension)

**Q: Can commands call other commands?**
A: Yes, use the `Skill` tool to invoke other commands

**Q: How do I pass arguments?**
A: Arguments are passed as `$ARGUMENTS` to the command

**Q: Can commands modify files?**
A: Yes, if `Edit` or `Write` are in `allowed-tools`

**Q: How do I test commands?**
A: Create a test project and run `claude run /command-name`

**Q: Can commands use external APIs?**
A: Yes, via Bash (curl) if allowed in permissions

**Q: How do I debug failed commands?**
A: Check Claude Code logs, verify tool permissions, test bash commands manually

---

## Appendix: Complete Command Template

````markdown
---
description: [Short description of command]
allowed-tools: [Comma-separated list of tools]
argument-hint: [argument-name (optional)]
---

# [Command Name]

[Detailed description of what the command does and when to use it]

## Parallel Agent Integration (if applicable)

This command [ALWAYS|CONDITIONALLY|NEVER] uses parallel agents.

[Integration details if applicable]

## Arguments

- `$ARGUMENTS` - [Description]
- If not provided: [Default behavior]

---

## Instructions

[Step-by-step instructions for Claude to execute]

### Step 1: [First Step]

[Description]

```bash
[Command]
```

### Step 2: [Second Step]

[Description]

```bash
[Command]
```

---

## Error Recovery

**On Failure**:

- [Action 1]
- [Action 2]

---

## Examples

### Example 1: [Use Case]

```bash
/command-name argument
```

Expected output:

```text
[Output]
```

---

## Customization

[How to adapt for different projects]

---

## Related

- [Related command 1]
- [Related command 2]

````

---

[← Commands Guide](../COMMANDS.md)
