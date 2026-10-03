---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's our billing package. Can you do a pass on it?

```
billing/
  discount.go
  discount_test.go
  invoice.go
  refund.go
```

```go
// billing/discount.go
package billing

func ApplyDiscount(amount int64, pct float64) int64 {
	if pct < 0 || pct > 100 {
		return amount
	}
	return amount - int64(float64(amount)*pct/100)
}
```

```go
// billing/discount_test.go
package billing

import "testing"

func TestApplyDiscount(t *testing.T) {
	got := ApplyDiscount(1000, 10)
	if got != 900 {
		t.Fatalf("got %d, want 900", got)
	}
}
```

```go
// billing/invoice.go
package billing

import "fmt"

type Invoice struct {
	ID     string
	Amount int64
}

func NewInvoice(id string, amount int64) *Invoice {
	return &Invoice{ID: id, Amount: amount}
}

func (i *Invoice) String() string {
	return fmt.Sprintf("invoice %s: %d", i.ID, i.Amount)
}
```

```go
// billing/refund.go
package billing

import "fmt"

func Refund(inv *Invoice, amount int64) (*Invoice, error) {
	if amount > inv.Amount {
		return nil, fmt.Errorf("refund %d exceeds invoice amount %d", amount, inv.Amount)
	}
	inv.Amount -= amount
	return inv, nil
}
```
