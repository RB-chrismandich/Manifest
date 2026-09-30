---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Agent, Read, Write, Grep, Glob, "Bash(mkdir:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(python3:*)", "Bash(node:*)", "Bash(git:*)"]
runs: 3
model: sonnet
---
First save each file below into this workspace at the path given in its header comment, then run the audit against that local tree.

Can you run an ai-code-audit on this sync worker before we ship it? Want to catch any vibe-coding issues before it hits prod.

```javascript
// worker/sync.js
function syncAll(items) {
  for (const item of items) {
    pushToRemote(item);
  }
  console.log('sync kicked off for', items.length, 'items');
}

async function pushToRemote(item) {
  const res = await fetch(`https://api.example.com/items/${item.id}`, {
    method: 'PUT',
    body: JSON.stringify(item),
  });
  if (!res.ok) {
    throw new Error(`push failed for ${item.id}: ${res.status}`);
  }
}

module.exports = { syncAll };
```
