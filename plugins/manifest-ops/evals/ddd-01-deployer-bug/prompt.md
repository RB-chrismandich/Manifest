---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from our dotfiles deployer repo; you don't have a checkout.)

Health check on every machine: `~/.gemini/` has only 3 of the 5 expected shared symlinks (`scripts`, `config`, `prompts` present; `skills`, `.plans` missing). Re-running the deploy doesn't help.

`configs/claude/` contains: `scripts/ config/ prompts/ skills/ .plans/`. README's manual-deploy section lists all five for Gemini.

`bootstrap/lib/deploy.sh`:
```bash
120 deploy_cursor() {
121   link_shared_assets "$HOME/.cursor"
122 }
123
124 deploy_codex() {
125   link_shared_assets "$HOME/.codex"
126 }
127
128 deploy_gemini() {
129   create_symlink "$SRC/scripts" "$HOME/.gemini/scripts"
130   create_symlink "$SRC/config"  "$HOME/.gemini/config"
131   create_symlink "$SRC/prompts" "$HOME/.gemini/prompts"
132 }
```
`link_shared_assets` links all five. What's wrong and how should it be fixed?
