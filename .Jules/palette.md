## 2026-01-27 - Improving CLI Ergonomics
**Learning:** Users often struggle with long paths for internal scripts (`~/.claude/scripts/parallel_agent.sh`). Providing a copy-pasteable alias command during setup significantly reduces friction.
**Action:** Always offer shell aliases for tools installed in non-standard locations. Detect the user's shell to provide the correct command.

## 2026-01-28 - Visualizing Data in CLI
**Learning:** CLI tools often output raw numbers that are hard to scan quickly. Adding simple ASCII/Unicode visualizations (like progress bars) significantly improves "at-a-glance" readability without requiring a GUI.
**Action:** Look for opportunities to visualize percentage-based or status-based data in CLI outputs using text-based bars or indicators.
