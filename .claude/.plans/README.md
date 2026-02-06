# Plan Management — Quick Reference

## Naming Convention

```text
YYYYMMDD-short-description.md
```

Examples: `20260205-model-config-alignment.md`, `20260210-add-auth-middleware.md`

## Lifecycle

```text
CREATE → ACTIVE → COMPLETED (.archive/) or ABANDONED (.abandoned/)
```

1. **CREATE**: Copy `TEMPLATE.md`, fill in details, save with date-prefixed name
2. **ACTIVE**: Plan lives in `.plans/` root while work is in progress
3. **COMPLETED**: Move to `.archive/` when all deliverables are checked off
4. **ABANDONED**: Move to `.abandoned/` if the plan is superseded or no longer relevant

## Directory Structure

```text
.claude/.plans/
├── .archive/          # Completed plans
├── .abandoned/        # Stale or abandoned plans
├── TEMPLATE.md        # Plan template
├── README.md          # This file
└── *.md               # Active plans
```

## Rules

- **Review existing plans** before creating a new one — avoid duplicates
- **Check off deliverables** as you implement them
- Plans untouched for **7+ days** should be reviewed for staleness
- Use the `/plan-manage` command for housekeeping tasks
