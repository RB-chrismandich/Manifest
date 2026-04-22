with open("configs/claude/scripts/parallel_agent.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "progress.add_task(f\"Running {len(self.agents)} agents...\", total=None)" in line:
        # need to assign to _task
        lines[i] = "            _task = progress.add_task(\n"
        lines[i] = lines[i] + "                f\"Running {len(self.agents)} agents...\", total=None\n"
        lines[i] = lines[i] + "            )\n"
        break

with open("configs/claude/scripts/parallel_agent.py", "w") as f:
    f.writelines(lines)
