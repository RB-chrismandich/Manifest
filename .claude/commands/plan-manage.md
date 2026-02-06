# Plan Management

Manage implementation plans in `.claude/.plans/`.

## Actions

Determine the requested action from the user's argument (default: **list**).

### list

1. Read all `*.md` files in `.claude/.plans/` (excluding TEMPLATE.md and README.md)
2. For each plan, extract: filename, status, title, created date, number of completed/total deliverables
3. Flag any plan not modified in 7+ days as **STALE**
4. Display a summary table

### create

1. Read `.claude/.plans/TEMPLATE.md`
2. Ask the user for: title, objective, and initial deliverables
3. Generate a new plan file named `YYYYMMDD-short-description.md` (today's date)
4. Save to `.claude/.plans/`

### review

1. Read all active plans in `.claude/.plans/`
2. For each plan, report:
   - Deliverable completion progress (checked vs total)
   - Days since last modification
   - Whether it should be archived (all done) or flagged as stale (7+ days)
3. Suggest actions for each plan

### archive

1. Ask which plan to archive (or accept a filename argument)
2. Verify all deliverables are checked off
3. Move the plan to `.claude/.plans/.archive/`

### abandon

1. Ask which plan to abandon (or accept a filename argument)
2. Confirm with the user
3. Move the plan to `.claude/.plans/.abandoned/`

## Tool Usage

- Use **Read**, **Glob**, **Grep** to inspect plans
- Use **Bash** only for `mv` operations (archive/abandon) and `date` commands
- Use **Write** only when creating new plans from the template
