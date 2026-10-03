---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
A contributor we've never worked with before opened a PR adding this plugin. We haven't reviewed the code yet -- can you check it over, dependencies included, before we even run it locally?

```json
// package.json
{
  "name": "importer-plugin",
  "version": "0.1.0",
  "main": "index.js",
  "dependencies": {
    "lodash": "4.17.4",
    "axios": "0.18.0"
  }
}
```

```javascript
// index.js
const _ = require("lodash");
const axios = require("axios");

async function importRecords(records) {
  const grouped = _.groupBy(records, "type");
  for (const type of Object.keys(grouped)) {
    await axios.post(`https://ingest.example.com/${type}`, grouped[type]);
  }
  return grouped;
}

module.exports = { importRecords };
```
