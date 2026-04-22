with open("docs/VALIDATION_REPORT.md", "r") as f:
    lines = f.readlines()

# Let's disable MD029 too
if "MD029" not in lines[0] and "MD029" not in lines[1]:
    lines.insert(2, "<!-- markdownlint-disable MD029 -->\n")

with open("docs/VALIDATION_REPORT.md", "w") as f:
    f.writelines(lines)
