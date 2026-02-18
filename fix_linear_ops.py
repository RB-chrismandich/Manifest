import re

filepath = "configs/claude/scripts/linear_ops.sh"

with open(filepath, "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Match local query='...' or local mutation='...'
    if re.search(r"^\s*local\s+(query|mutation|target_state_query)='", line):
        indent = re.match(r"^\s*", line).group(0)
        new_lines.append(f"{indent}# shellcheck disable=SC2016\n")
    new_lines.append(line)

with open(filepath, "w") as f:
    f.writelines(new_lines)
