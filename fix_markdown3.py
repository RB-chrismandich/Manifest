with open("docs/SHELL_ANALYSIS_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    # Fix MD032
    if lines[i].startswith("- ") or lines[i].startswith("1. "):
        if i > 0 and lines[i-1] != "\n" and not lines[i-1].startswith("- ") and not lines[i-1].startswith("1. "):
            lines.insert(i, "\n")
            i += 1

    # Fix MD013 line length (naively wrap, but actually let's just ignore or truncate if too long, or use markdown formatting)
    # The actual fix for MD013 is complicated, maybe we can just disable MD013 in the config or the file.

with open("docs/SHELL_ANALYSIS_REPORT.md", "w") as f:
    f.writelines(lines)

with open("docs/VALIDATION_REPORT.md", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    if lines[i].startswith("- ") or lines[i].startswith("1. "):
        if i > 0 and lines[i-1] != "\n" and not lines[i-1].startswith("- ") and not lines[i-1].startswith("1. "):
            lines.insert(i, "\n")
            i += 1
    if lines[i].startswith("```\n"):
        lines[i] = "```text\n"
    if lines[i].startswith("### ") or lines[i].startswith("#### "):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")
    if lines[i].startswith("```"):
        if i > 0 and lines[i-1] != "\n":
            lines.insert(i, "\n")
            i += 1
        if i < len(lines)-1 and lines[i+1] != "\n":
            lines.insert(i+1, "\n")

with open("docs/VALIDATION_REPORT.md", "w") as f:
    f.writelines(lines)
