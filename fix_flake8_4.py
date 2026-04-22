with open("configs/claude/scripts/parallel_agent.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "configs/claude/scripts/parallel_agent.py:1454:13: E303 too many blank lines (2)" in line:
        pass # this isn't right

# Just delete extra blank lines near 1454
lines = [l for i, l in enumerate(lines) if not (i >= 1445 and i <= 1455 and l == "\n" and lines[i-1] == "\n")]
with open("configs/claude/scripts/parallel_agent.py", "w") as f:
    f.writelines(lines)
