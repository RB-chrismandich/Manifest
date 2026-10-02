---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
All unit tests pass for the vendor-matching step. We just turned it on against
the real AP export and one vendor that should obviously match the registry is
coming back unmatched — here's the code, the test file, and the real records.
What's going on?

`test_match_vendor.py`:
```python
from match_vendor import enrich, build_index

def test_enrich_matches_known_vendor():
    registry = [{"vendor_name": "Acme Corp", "vendor_id": "V100"}]
    records = [{"vendor": "Acme Corp"}]
    index = build_index(registry)
    out = enrich(records, index)
    assert out[0]["vendor_id"] == "V100"
```

`match_vendor.py`:
```python
def normalize(name: str) -> str:
    return name.strip().lower()

def build_index(registry: list[dict]) -> dict:
    return {normalize(r["vendor_name"]): r["vendor_id"] for r in registry}

def enrich(records: list[dict], index: dict) -> list[dict]:
    out = []
    for r in records:
        vendor_id = index.get(normalize(r["vendor"]))
        out.append({**r, "vendor_id": vendor_id})
    return out
```

Real registry record:
```python
registry = [{"vendor_name": "O'Brien Consulting", "vendor_id": "V301"}]
```

Real AP export record (pulled straight from the legacy accounts-payable system,
where vendor names are typed in by hand):
```python
records = [{"vendor": "O’Brien Consulting"}]
```
Printed, both look like "O'Brien Consulting" to me, so I assumed the join would
work.
