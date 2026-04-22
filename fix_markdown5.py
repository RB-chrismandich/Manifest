with open("docs/SHELL_ANALYSIS_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    if lines[i].startswith("```"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")

with open("docs/SHELL_ANALYSIS_REPORT.md", "w") as f:
    f.writelines(lines)
