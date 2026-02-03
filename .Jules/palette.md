## 2026-01-27 - Improving CLI Ergonomics
**Learning:** Users often struggle with long paths for internal scripts (`~/.claude/scripts/parallel_agent.sh`). Providing a copy-pasteable alias command during setup significantly reduces friction.
**Action:** Always offer shell aliases for tools installed in non-standard locations. Detect the user's shell to provide the correct command.

## 2026-01-28 - Visualizing Data in CLI
**Learning:** CLI tools often output raw numbers that are hard to scan quickly. Adding simple ASCII/Unicode visualizations (like progress bars) significantly improves "at-a-glance" readability without requiring a GUI.
**Action:** Look for opportunities to visualize percentage-based or status-based data in CLI outputs using text-based bars or indicators.

## 2026-01-31 - Providing Duration Feedback in CLI
**Learning:** For long-running CLI operations, users often lack context on whether a process is stuck or just slow. Providing a duration summary at the end helps users benchmark performance and reinforces completion.
**Action:** Add a simple execution timer to the final success message of long-running scripts.

## 2026-02-01 - Managing Concurrent CLI Output
**Learning:** Background spinners in shell scripts often conflict with output from parallel background processes, causing visual artifacts. Redirecting background job output and using a main-thread polling loop to update a status line provides a much cleaner, artifact-free experience.
**Action:** When orchestrating parallel tasks in CLI, suppress background job stdout and use a centralized status monitor loop that polls PIDs.

## 2026-02-02 - Liveness Indicators for Long Operations
**Learning:** For indeterminate waiting states (like waiting for external APIs), a simple spinner is insufficient as users can't tell if the process is stalled. Adding an elapsed time counter (MM:SS) provides immediate liveness feedback and helps users decide if they should abort.
**Action:** Enhance CLI spinners with a dynamic elapsed time counter for operations expected to take more than 10 seconds.
