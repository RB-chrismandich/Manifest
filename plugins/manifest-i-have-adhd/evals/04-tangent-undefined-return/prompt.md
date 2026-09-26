---
max_turns: 3
timeout_seconds: 120
allowed_tools: []
model: sonnet
runs: 3
---
(You don't have access to my project here — answer from general knowledge.)

Why does this return undefined?

```js
var total = 0
function sumPrices(items) {
  items.forEach(function (item) {
    total = total + item.price
  })
  total
}
console.log(sumPrices([{price: 2}, {price: 3}]))
```
