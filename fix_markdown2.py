with open("docs/SHELL_ANALYSIS_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    # MD022/blanks-around-headings
    if lines[i].startswith("#### SC"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")
    if lines[i].startswith("### "):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")

    # MD031/blanks-around-fences
    if lines[i].startswith("```"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")

with open("docs/SHELL_ANALYSIS_REPORT.md", "w") as f:
    f.writelines(lines)
