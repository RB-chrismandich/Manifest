# Domain Vocabulary

> The allowed domain prefixes and what each one covers.

## Domain Vocabulary

The first token(s) of every skill name must appear in this list. The conformance test
parses the fenced block between the markers — keep one token per line.

<!-- skill-naming:domains -->
```text
a11y
ai-code
antipattern
api
branch
cache
ci
cli
code
config
data
delegate
deploy
design
docker
docs
env
git
go
issue
learning
lifecycle
llm
mcp
memory
metrics
node
performance
plan
pr
premise
print
process
project
prompt
python
repo
security
session
shell
skill
smoke
spec
speckit
terraform
test
token
ux
version
```
<!-- /skill-naming:domains -->

### Adding a new domain token

Add a token only when a skill genuinely fits no existing domain. Add it to the block
above (alphabetical), justify it in the PR description, and prefer reusing an existing
altitude (e.g. a new language gets its own token, like `go`; a new artifact type joins
an existing domain if one fits).

---

[← Skill Naming](../SKILL-NAMING.md)
