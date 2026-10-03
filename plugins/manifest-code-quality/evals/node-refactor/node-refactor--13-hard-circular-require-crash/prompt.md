---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our server's `index.js` does `require("./services/orderService")` first, at the very top, to wire up the order routes before anything else loads; `notificationService` only gets required indirectly through that, at the top of `orderService.js`. A retry cron job elsewhere in that same process does `const { retryFailedOrder } = require("./services/notificationService")` and calls it on a timer -- every single call throws `TypeError: createOrder is not a function`, even though `createOrder` is clearly defined and exported from `orderService.js`. Can you figure out what's going on and do a broader pass on these two files?

```javascript
// src/services/orderService.js
const { notifyUser } = require("./notificationService");

function createOrder(order) {
  const record = { ...order, status: "created" };
  notifyUser(record.userId, "Order created");
  return record;
}

module.exports = { createOrder };
```

```javascript
// src/services/notificationService.js
const { createOrder } = require("./orderService");

function notifyUser(userId, message) {
  console.log(`notify ${userId}: ${message}`);
}

function retryFailedOrder(order) {
  console.log("retrying order", order.id);
  return createOrder(order);
}

module.exports = { notifyUser, retryFailedOrder };
```
