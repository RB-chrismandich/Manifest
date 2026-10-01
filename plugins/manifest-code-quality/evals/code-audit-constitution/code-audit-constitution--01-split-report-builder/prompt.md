---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Write, Edit, Grep, Glob, "Bash(python3:*)", "Bash(pytest:*)", "Bash(grep:*)", "Bash(echo:*)", "Bash(ls:*)"]
runs: 3
model: sonnet
---
Save this as `report_builder.py`. The constitution checker keeps flagging `build_report` in it as over the function size ceiling. Can you actually fix it instead of just noting it, and confirm it still produces the same report?

```python
def build_report(rows, min_amount=0, currency="USD", include_zero=False):
    if not isinstance(rows, list):
        raise TypeError("rows must be a list")
    if not isinstance(currency, str) or not currency:
        raise ValueError("currency must be a non-empty string")

    cleaned = []
    skipped = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        if "name" not in row or "amount" not in row:
            skipped += 1
            continue
        if row["amount"] is None:
            skipped += 1
            continue
        try:
            amount = float(row["amount"])
        except (TypeError, ValueError):
            skipped += 1
            continue
        if amount < min_amount:
            skipped += 1
            continue
        if amount == 0 and not include_zero:
            skipped += 1
            continue
        name = str(row["name"]).strip()
        if not name:
            skipped += 1
            continue
        cleaned.append({"name": name, "amount": amount})

    total = 0.0
    by_name = {}
    for row in cleaned:
        total += row["amount"]
        if row["name"] in by_name:
            by_name[row["name"]] += row["amount"]
        else:
            by_name[row["name"]] = row["amount"]
    sorted_names = sorted(by_name.keys(), key=lambda n: by_name[n], reverse=True)
    top_five = sorted_names[:5]
    average = total / len(cleaned) if cleaned else 0.0
    largest = max((row["amount"] for row in cleaned), default=0.0)
    smallest = min((row["amount"] for row in cleaned), default=0.0)
    unique_names = len(by_name)

    lines = []
    lines.append(f"Report ({currency})")
    lines.append("=" * 40)
    lines.append(f"Total: {total:.2f}")
    lines.append(f"Average: {average:.2f}")
    lines.append(f"Largest: {largest:.2f}")
    lines.append(f"Smallest: {smallest:.2f}")
    lines.append(f"Entries: {len(cleaned)} (skipped {skipped})")
    lines.append(f"Unique names: {unique_names}")
    lines.append("")
    lines.append("Top 5 by name:")
    for name in top_five:
        lines.append(f"  {name}: {by_name[name]:.2f}")
    lines.append("")
    lines.append("All entries:")
    for row in cleaned:
        lines.append(f"  {row['name']}: {row['amount']:.2f}")
    return "\n".join(lines)
```
