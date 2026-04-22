with open("configs/claude/scripts/parallel_agent.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "f\"Running {len(self.agents)} agents...\", total=None" in line:
        lines[i] = "            progress.add_task(f\"Running {len(self.agents)} agents...\", total=None)\n"
        lines[i+1] = "\n"

with open("configs/claude/scripts/parallel_agent.py", "w") as f:
    f.writelines(lines)
