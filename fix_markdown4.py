with open("docs/SHELL_ANALYSIS_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    if lines[i].startswith("```"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")

with open("docs/SHELL_ANALYSIS_REPORT.md", "w") as f:
    f.writelines(lines)

with open("docs/VALIDATION_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    if lines[i].startswith("```"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")
    if "- ✅ ShellCheck correctly ident" in lines[i]:
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
    # fix MD029
    if lines[i].startswith("2. `flake8"):
        lines[i] = "1. `flake8" + lines[i][2:]
    if lines[i].startswith("3. `yamllint"):
        lines[i] = "2. `yamllint" + lines[i][2:]

with open("docs/VALIDATION_REPORT.md", "w") as f:
    f.writelines(lines)
