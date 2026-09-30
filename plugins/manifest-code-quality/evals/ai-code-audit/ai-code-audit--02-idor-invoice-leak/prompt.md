---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Agent, Read, Write, Grep, Glob, "Bash(mkdir:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(python3:*)", "Bash(node:*)", "Bash(git:*)"]
runs: 3
model: sonnet
---
First save each file below into this workspace at the path given in its header comment, then run the audit against that local tree.

Users are reporting they can pull up other customers' invoices just by changing the ID in the URL — e.g. hitting `/api/invoices/1042` shows someone else's invoice. Here's the route. Can you audit it and tell us what's actually wrong architecturally, not just patch the one report?

```javascript
// routes/invoices.js
const express = require('express');
const router = express.Router();

router.get('/api/invoices/:id', requireAuth, async (req, res) => {
  const invoice = await db.invoices.findById(req.params.id);
  if (!invoice) return res.status(404).json({ error: 'not found' });
  res.json(invoice);
});

module.exports = router;
```

`requireAuth` just verifies the JWT is valid and attaches `req.user` — it doesn't know anything about invoices.
