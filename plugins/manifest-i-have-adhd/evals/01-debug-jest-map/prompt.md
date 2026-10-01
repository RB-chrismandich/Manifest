---
max_turns: 3
timeout_seconds: 120
allowed_tools: []
model: sonnet
runs: 3
---
(You don't have access to my project here — answer from general knowledge.)

My Jest test fails with `TypeError: Cannot read properties of undefined (reading 'map')` in `UserList.test.tsx`. The component does `props.users.map(u => <li>{u.name}</li>)` and the test renders `<UserList />` with no props. How do I fix it?
