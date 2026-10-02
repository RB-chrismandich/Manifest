---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit]
runs: 3
---
Create `README.md` with this content:

```
# Widget

Teh widget renders charts.

## Install

pip install widget

## Usage

import widget; widget.render()
```

Now switch to token-conserve mode, then fix the typo "Teh" in README.md.
