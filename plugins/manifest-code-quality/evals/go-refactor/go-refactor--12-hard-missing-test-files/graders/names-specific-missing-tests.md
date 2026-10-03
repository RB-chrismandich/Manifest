---
type: llm
weight: 1
---
The package listing shows `discount.go` has a matching `discount_test.go`, but `invoice.go` and `refund.go` do not have any `invoice_test.go` / `refund_test.go`. Score 1 only if the answer explicitly names BOTH `invoice.go` and `refund.go` (by filename, or by their exported functions `NewInvoice`/`Invoice.String`/`Refund`) as lacking a corresponding test file, ideally by contrast with `discount.go`/`discount_test.go` which does follow the pattern. Score 0 if the answer only gives a generic "add more tests" / "test coverage could be improved" recommendation without identifying by name which specific files are missing tests, or if it names only one of the two.
