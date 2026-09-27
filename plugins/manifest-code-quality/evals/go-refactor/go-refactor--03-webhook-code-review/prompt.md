---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Here's the diff for our new webhook signature check and the HTTP client it uses to call out to the provider. Can you take a look before I approve the PR?

```go
// internal/webhook/verify.go
package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
)

func Verify(payload, signature, secret []byte) bool {
	mac := hmac.New(sha256.New, secret)
	mac.Write(payload)
	expected := mac.Sum(nil)
	return string(expected) == string(signature)
}
```

```go
// internal/webhook/client.go
package webhook

import "net/http"

func NewClient() *http.Client {
	return &http.Client{}
}
```
