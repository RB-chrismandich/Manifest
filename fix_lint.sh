#!/bin/bash
# Insert shellcheck disable for files with SC2016
sed -i '2i # shellcheck disable=SC2016' configs/claude/scripts/linear_ops.sh
sed -i '2i # shellcheck disable=SC2016' configs/claude/scripts/parallel_agent.sh

# Fix SC2001 in generate_cursor_rules.sh
sed -i 's/desc_value=$(echo "$desc_line" | sed '"'s\/^description:[[:space:]]*\/\/'"'/desc_value="${desc_line#description:[[:space:]]*}"/' configs/claude/scripts/generate_cursor_rules.sh

# Fix SC2181 in learning_capture.sh
# Oh wait, we should modify the file directly or use replace_with_git_merge_diff
