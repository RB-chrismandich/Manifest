---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Why does this always print NaN?

```js
function parsePrice(input) {
  return parseInt(input.trim(), 10) * 1.0;
}

console.log(parsePrice("$19.99"));
```
