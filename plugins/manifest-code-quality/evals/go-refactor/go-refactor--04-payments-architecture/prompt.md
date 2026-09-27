---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our payments package works but every new provider we add means touching half the package. Can you give this a holistic audit -- architecture and anything else you spot?

```go
// internal/payments/processor.go
package payments

const stripeSecretKey = "sk_live_FAKE1234567890" // gitleaks:allow

type Processor interface {
	Charge(amount int) error
}

func NewProcessor() Processor {
	return &stripeProcessor{}
}

type stripeProcessor struct{}

func (s *stripeProcessor) Charge(amount int) error { return nil }

func init() {
	loadPaymentConfig()
}

func loadPaymentConfig() {
	// reads config from disk and sets package-level state
}
```
