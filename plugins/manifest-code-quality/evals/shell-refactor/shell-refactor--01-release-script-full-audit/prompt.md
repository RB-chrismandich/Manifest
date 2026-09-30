---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Refactor this release script for security and quality — give me a prioritized report with effort and risk ratings for each finding.

```bash
#!/usr/bin/env bash
set -e

SLACK_WEBHOOK="https://hooks.slack.com/services/T0000000/B0000000/AbCdEfGhIjKlMnOpQrStUvWx"

notify() {
  eval "curl -s -X POST -d '{\"text\": \"$1\"}' $SLACK_WEBHOOK"
}

backup_dir=$1
tmp=/tmp/release.$$

echo "cleaning $backup_dir"
rm -rf $backup_dir/*

echo "building release" > $tmp
cat $tmp

notify "release cleaned and built"
```
