with open("docs/KNOWLEDGE_BASE.md", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "TD-001" in line:
        lines[i] = line + "\n"
    elif "CI-002" in line:
        lines[i] = line + "\n"

with open("docs/KNOWLEDGE_BASE.md", "w") as f:
    f.writelines(lines)
