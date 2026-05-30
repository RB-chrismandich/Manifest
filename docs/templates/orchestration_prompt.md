# Orchestration Prompt Template

> Template for creating multi-agent orchestration workflows with Claude Code

**Purpose**: This template helps you create orchestration prompts that coordinate multiple
sub-agents, parallel tools, and complex workflows.

**When to use**: For projects with:

- Multiple services/modules requiring coordination
- Complex multi-step workflows
- Need for parallel agent validation
- Sub-agent delegation patterns

---

## Template Structure

```markdown
# Role: [Your Role Title]

## Objective

[Clear description of what this orchestration prompt achieves]

Process [WHAT] into [DESIRED OUTCOME]. You act as the Orchestrator, coordinating [SUB-AGENTS/TOOLS] for [PURPOSE].

---

## Project Context

**Architecture**: [Brief architecture description]
**Languages**: [List of languages]
**Infrastructure**: [Key infrastructure components]

### Component Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| Component A | Language | Description |
| Component B | Language | Description |

### Data Flow

```text

[ASCII diagram or description of how data flows through the system]

```

### Key Constraints

- [Constraint 1]
- [Constraint 2]
- [Constraint 3]

---

## Workflow (STRICT)

### Step 1: Analysis & Planning

1. [First analysis step]
2. [Run parallel agents if needed]:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --timeout 600 \
     --analyze "[ANALYSIS TASK]"
   ```

3. [Break down into subtasks]

### Step 2: Implementation (Sub-Agent Delegation)

For each affected [component/service]:

1. Read the [component's agent file]: `path/to/AGENTS.md`
2. Reference [relevant standards]: `docs/standards/STANDARDS.md`
3. Delegate to a Task sub-agent with:
   - The relevant slice of the execution plan
   - [Component-specific context]
   - Requirement to write implementation code AND tests
4. Review the sub-agent's output against the plan

### Step 3: Verification

Once all sub-agents have completed:

1. **Unit tests**: [command]
2. **Integration tests**: [command]
3. **Lint**: [command]

**On failure**: Recall the specific sub-agent responsible to fix the error.

### Step 4: Final Validation

Once all tests pass:

1. Run parallel agent validation on each modified file:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --validate --timeout 600 \
     --review /absolute/path/to/modified_file
   ```

2. Evaluate consensus:
   - **>= 80%**: High confidence — proceed
   - **50-79%**: Medium confidence — flag disagreements
   - **< 50%**: Low confidence — escalate to user

---

## Sub-Agent Registry

### [Components/Services] with Dedicated Agents

| Component | Language | Agent File | Scope |
|-----------|----------|-----------|-------|
| **Component A** | Language | `path/to/agents.md` | Description |
| **Component B** | Language | `path/to/agents.md` | Description |

### Standards Reference

| Language | Standards File |
|----------|---------------|
| Language A | `docs/standards/STANDARDS.md` |
| Language B | `docs/standards/STANDARDS.md` |

---

## Cross-Component Change Checklist

When changes span multiple components, follow this checklist:

- [ ] [Change type 1] → [Steps to handle it]
- [ ] [Change type 2] → [Steps to handle it]
- [ ] [Change type 3] → [Steps to handle it]

---

## Critical Rules

1. [Critical rule 1]
2. [Critical rule 2]
3. [Critical rule 3]

---

## Current Task

[Prompt for user to provide input]

```text

---

## Example: Microservices Project

See `examples/microservices_orchestration.md` for a complete example of:
- Service map with gRPC/event-driven communication
- Multi-phase validation workflow
- Protobuf schema evolution rules
- Database migration coordination

---

## Example: Monorepo Project

See `examples/monorepo_orchestration.md` for a complete example of:
- Package dependency graph
- Shared library coordination
- Cross-package refactoring workflow
- Incremental migration strategies

---

## Usage Instructions

### 1. Customize the Template

1. Copy this template to your project's `.claude/` directory
2. Replace all `[PLACEHOLDERS]` with your project specifics
3. Adapt the workflow steps to your needs
4. Add your component map and data flow diagrams

### 2. Deploy as Headless Prompt

Save to `.claude/headless_prompt.md` to make it available when Claude Code starts in your project directory.

### 3. Test the Orchestration

Run through a simple multi-component change to validate your orchestration logic:
```bash
# Example test
echo "Test orchestration with a simple cross-component change"
```

---

## Best Practices

### Clear Delegation Boundaries

- Each sub-agent should have a well-defined scope
- Avoid overlap between sub-agent responsibilities
- Document handoff points clearly

### Validation at Each Phase

- Validate after analysis (is the plan sound?)
- Validate after implementation (do tests pass?)
- Validate with parallel agents (cross-verification)

### Error Recovery

- Specify what to do when sub-agents fail
- Define retry strategies
- Document escalation paths

### Context Management

- Keep sub-agent context focused and minimal
- Reference external docs rather than copying
- Update agent files when patterns change

---

## Related Templates

- `templates/skills/` - Auto-trigger skills for domain-specific validation
- `templates/validation-overrides/` - Project-specific validation rules
- `templates/github-workflow/` - Issue management and workflow automation

---

## References

- [Claude Code Documentation](https://docs.anthropic.com/claude/docs)
- [Parallel Agent Orchestration Guide](../.claude/CLAUDE.md)
- [Validation Criteria](../.claude/config/validation_criteria.yml)
