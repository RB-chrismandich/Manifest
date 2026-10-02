---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you write a Jest unit test for this reducer? I just want good line coverage, nothing end-to-end.

```javascript
function cartReducer(state, action) {
  switch (action.type) {
    case "ADD_ITEM":
      return { ...state, items: [...state.items, action.item] };
    case "CLEAR":
      return { ...state, items: [] };
    default:
      return state;
  }
}
```

Just put the test in your reply — no need to create files.
