---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This payments service works but adding a new provider means editing this file in five places. Can you take a full pass -- not just architecture?

```ts
// src/services/payments.ts
export let currentProvider = "stripe";

export function charge(amount: number, cardToken: string) {
  if (currentProvider === "stripe") {
    return stripeCharge(amount, cardToken);
  } else if (currentProvider === "paypal") {
    return paypalCharge(amount, cardToken);
  }
}

function stripeCharge(amount: number, cardToken: string) {
  return fetch("https://api.stripe.com/v1/charges", {
    method: "POST",
    headers: { Authorization: "Bearer sk_live_51EXAMPLEKEY0000" }, // gitleaks:allow
    body: `amount=${amount}&source=${cardToken}`,
  });
}

function paypalCharge(amount: number, cardToken: string) {
  return fetch("https://api.paypal.com/v2/payments", {
    method: "POST",
    body: `amount=${amount}&source=${cardToken}`,
  });
}
```
