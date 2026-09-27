---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Here's a small email-validation helper I wrote for our signup form. Anything to flag before I open the PR?

```go
// internal/validate/email.go
package validate

import (
	"errors"
	"fmt"
	"strings"
	"unicode"
)

// maxEmailLen is the RFC 5321 limit on a forward-path address.
const maxEmailLen = 254

// ErrInvalidEmail is wrapped by every validation failure so callers can use errors.Is.
var ErrInvalidEmail = errors.New("invalid email")

// Email reports an error wrapping ErrInvalidEmail unless s has exactly one '@',
// a non-empty local part, a dotted domain with non-empty labels, no whitespace
// or control characters, and at most maxEmailLen bytes.
func Email(s string) error {
	if len(s) == 0 || len(s) > maxEmailLen {
		return fmt.Errorf("%w: length %d out of range 1..%d", ErrInvalidEmail, len(s), maxEmailLen)
	}
	if strings.IndexFunc(s, func(r rune) bool { return unicode.IsSpace(r) || unicode.IsControl(r) }) >= 0 {
		return fmt.Errorf("%w: contains whitespace or control characters", ErrInvalidEmail)
	}
	local, domain, ok := strings.Cut(s, "@")
	if !ok || local == "" || strings.Contains(domain, "@") {
		return fmt.Errorf("%w: need exactly one '@' with a non-empty local part", ErrInvalidEmail)
	}
	labels := strings.Split(domain, ".")
	if len(labels) < 2 {
		return fmt.Errorf("%w: domain %q has no dot", ErrInvalidEmail, domain)
	}
	for _, l := range labels {
		if l == "" {
			return fmt.Errorf("%w: domain %q has an empty label", ErrInvalidEmail, domain)
		}
	}
	return nil
}
```
