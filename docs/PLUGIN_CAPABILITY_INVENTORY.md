# Plugin Capability Inventory

Generated from `src/manifest_agent/data/legacy_inventory.yml`; do not edit by hand.
Unlisted paths and credential stores are user-owned and are never changed by migration.

| ID | Legacy source | Classification | Native destination | Ownership proof | Action | Recovery | Parity test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| antigravity-config-link | `~/.antigravity/config` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/config` | disable | restore-symlink | `plugin_migration.bats` |
| antigravity-plans-link | `~/.antigravity/.plans` | bundle-owned | xdg-plan-store | symlink-target: `~/.claude/.plans` | disable | restore-symlink | `plugin_migration.bats` |
| antigravity-skills-link | `~/.antigravity/skills` | bundle-owned | native-plugin-managers | symlink-target: `~/.manifest/skills` | disable | restore-symlink | `plugin_migration.bats` |
| apm-drift-report | `~/.claude/scripts/apm_drift_report.sh` | retired | retired-plugin-drift-report | generated-hash: `apm-drift-report-v1` | remove | restore-file | `plugin_migration.bats` |
| bootstrap-uninstall-marker | `~/.manifest/bootstrap-uninstall.json` | coordinator-owned | native-receipt-uninstall | exact-marker: `manifest-bootstrap-uninstall-v1` | remove | restore-file | `plugin_migration.bats` |
| claude-agents | `~/.claude/agents` | bundle-owned | manifest-workspace | deploy-stamp: `config/deploy_stamp` | disable | restore-tree | `plugin_migration.bats` |
| claude-config | `~/.claude/config` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.manifest/config` | disable | restore-symlink | `plugin_migration.bats` |
| claude-context7 | `~/.claude.json` | mixed | native-mcp-context7 | exact-marker: `context7` | retain | restore-owned-mcp-entry | `plugin_migration.bats` |
| claude-guidance | `~/.claude/CLAUDE.md` | bundle-owned | manifest-workspace | deploy-stamp: `config/deploy_stamp` | disable | restore-file | `plugin_migration.bats` |
| claude-hooks | `~/.claude/settings.json` | mixed | native-hook-registration | exact-marker: `manifest-hook-envelope-v1` | retain | restore-owned-hook-entry | `plugin_migration.bats` |
| claude-permissions | `~/.claude/settings.local.json` | mixed | native-permission-registration | exact-marker: `manifest-permission-v1` | retain | restore-owned-permission-entry | `plugin_migration.bats` |
| claude-plans | `~/.claude/.plans` | user-owned | xdg-plan-store | exact-marker: `manifest-plan-template-v1` | retain | none | `test_spec_planning_runtime.py` |
| claude-prompts | `~/.claude/prompts` | bundle-owned | domain-bundle-runtime | deploy-stamp: `config/deploy_stamp` | disable | restore-tree | `plugin_migration.bats` |
| claude-references | `~/.claude/references` | bundle-owned | domain-bundle-runtime | deploy-stamp: `config/deploy_stamp` | disable | restore-tree | `plugin_migration.bats` |
| claude-scripts | `~/.claude/scripts` | bundle-owned | domain-bundle-runtime | deploy-stamp: `config/deploy_stamp` | disable | restore-tree | `plugin_migration.bats` |
| claude-shared-skills | `~/.claude/skills` | bundle-owned | native-plugin-managers | symlink-target: `~/.manifest/skills` | disable | restore-symlink | `plugin_migration.bats` |
| codex-config-link | `~/.codex/config` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/config` | disable | restore-symlink | `plugin_migration.bats` |
| codex-guidance | `~/.codex/AGENTS.md` | bundle-owned | manifest-workspace | deploy-stamp: `config/deploy_stamp` | disable | restore-symlink | `plugin_migration.bats` |
| codex-plans-link | `~/.codex/.plans` | bundle-owned | xdg-plan-store | symlink-target: `~/.claude/.plans` | disable | restore-symlink | `plugin_migration.bats` |
| codex-prompts-link | `~/.codex/prompts` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/prompts` | disable | restore-symlink | `plugin_migration.bats` |
| codex-shared-skills | `~/.codex/skills` | bundle-owned | native-plugin-managers | symlink-target: `~/.manifest/skills` | disable | restore-symlink | `plugin_migration.bats` |
| cursor-config-link | `~/.cursor/config` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/config` | disable | restore-symlink | `plugin_migration.bats` |
| cursor-generated-rules | `~/.cursor/rules` | bundle-owned | generated-cursor-native-view | deploy-stamp: `config/deploy_stamp` | disable | restore-tree | `plugin_migration.bats` |
| cursor-mcp | `~/.cursor/mcp.json` | mixed | native-mcp-context7 | exact-marker: `context7` | retain | restore-owned-mcp-entry | `plugin_migration.bats` |
| cursor-plans-link | `~/.cursor/.plans` | bundle-owned | xdg-plan-store | symlink-target: `~/.claude/.plans` | disable | restore-symlink | `plugin_migration.bats` |
| cursor-prompts-link | `~/.cursor/prompts` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/prompts` | disable | restore-symlink | `plugin_migration.bats` |
| deploy-stamp | `~/.claude/config/deploy_stamp` | coordinator-owned | installation-receipt | exact-marker: `manifest-deploy-stamp-v1` | remove | restore-file | `plugin_migration.bats` |
| devin-claude-inheritance | `~/.config/devin/config.json` | mixed | native-plugin-registration | exact-marker: `read_config_from` | retain | restore-owned-settings-entry | `plugin_migration.bats` |
| gemini-config-link | `~/.gemini/config` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/config` | disable | restore-symlink | `plugin_migration.bats` |
| gemini-guidance | `~/.gemini/GEMINI.md` | bundle-owned | manifest-workspace | deploy-stamp: `config/deploy_stamp` | disable | restore-file | `plugin_migration.bats` |
| gemini-plans-link | `~/.gemini/.plans` | bundle-owned | xdg-plan-store | symlink-target: `~/.claude/.plans` | disable | restore-symlink | `plugin_migration.bats` |
| gemini-prompts-link | `~/.gemini/prompts` | bundle-owned | domain-bundle-runtime | symlink-target: `~/.claude/prompts` | disable | restore-symlink | `plugin_migration.bats` |
| gemini-settings | `~/.gemini/settings.json` | mixed | native-settings-registration | exact-marker: `manifest-settings-v1` | retain | restore-owned-settings-entry | `plugin_migration.bats` |
| gemini-shared-skills | `~/.gemini/skills` | bundle-owned | native-plugin-managers | symlink-target: `~/.manifest/skills` | disable | restore-symlink | `plugin_migration.bats` |
| graphify-cli | `~/.local/bin/graphify` | bundle-owned | manifest-graphify | generated-hash: `graphify-wrapper-v1` | remove | restore-file | `test_graphify_runtime.py` |
| manifest-cli | `~/.local/bin/manifest` | coordinator-owned | ephemeral-uvx-coordinator | generated-hash: `manifest-cli-router-v1` | remove | restore-file | `plugin_migration.bats` |
| manifest-release-metadata | `~/.manifest/releases.json` | coordinator-owned | xdg-release-metadata | exact-marker: `manifest-release-v1` | remove | restore-file | `plugin_migration.bats` |
| manifest-skills-hub | `~/.manifest/skills` | bundle-owned | native-plugin-managers | deploy-stamp: `~/.manifest/deploy_stamp` | retain | user-directed-removal-after-parity | `plugin_migration.bats` |
| native-credentials | `~/.config/manifest/credentials.json` | harness-native | native-credential-store | exact-marker: `never-migrate` | retain | none | `manual-credential-preservation` |
| sync-skills-cli | `~/.local/bin/sync-skills` | bundle-owned | manifest-workspace | generated-hash: `sync-skills-router-v1` | remove | restore-file | `plugin_migration.bats` |
