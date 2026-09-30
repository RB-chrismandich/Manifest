---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our employer-enrichment step is returning almost no matches against the employer
registry, even though the data looks fine when I eyeball it. All the unit tests
pass. Here's the matching code plus a real slice of donor records and the employer
registry — what's going wrong?

`match_employer.py`:
```python
def normalize(name: str) -> str:
    return name.strip()

def build_registry_index(registry: list[dict]) -> dict:
    return {normalize(r["employer_name"]): r["employer_id"] for r in registry}

def enrich(records: list[dict], registry_index: dict) -> list[dict]:
    out = []
    for r in records:
        employer_id = registry_index.get(normalize(r["employer"]))
        out.append({**r, "employer_id": employer_id})
    return out
```

Real donor records:
```python
records = [
    {"last_name": "Diaz", "employer": "Acme Corp."},
    {"last_name": "Lopez", "employer": "Acme Corp"},
    {"last_name": "Kim", "employer": "SMITH & JONES LLP"},
]
```

Real employer registry:
```python
registry = [
    {"employer_name": "Acme Corp", "employer_id": "E100"},
    {"employer_name": "Smith and Jones LLP", "employer_id": "E200"},
]
```
