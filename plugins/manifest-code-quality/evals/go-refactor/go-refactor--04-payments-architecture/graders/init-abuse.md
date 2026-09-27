---
type: llm
weight: 1
---
Score 1 only if the answer flags the `init()` function calling `loadPaymentConfig()` as an instance of init()-function abuse (implicit, hard-to-test package initialization / hidden side effects at import time), AND recommends moving config loading into an explicit constructor or setup function called by the caller instead of an implicit `init()`. Score 0 otherwise.
