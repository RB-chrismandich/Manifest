with open("configs/claude/scripts/parallel_agent.py", "r") as f:
    content = f.read()

import re
content = re.sub(r' +_task = progress\.add_task\(\n +f"Running \{len\(self\.agents\)\} agents\.\.\.", total=None\n +\)\n', '            _task = progress.add_task(\n                f"Running {len(self.agents)} agents...", total=None\n            )\n            _ = _task\n', content)

with open("configs/claude/scripts/parallel_agent.py", "w") as f:
    f.write(content)
