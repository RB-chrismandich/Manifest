---
name: verify-api-schema-before-trust
description: Use after building parsers/clients against assumed or probed API response shapes, and before depending on them — verify the real endpoint path, field names, and date semantics against the live API.
---
# Verify API Schema Against the Live API Before Trusting Parsers

Parsers built from documentation, a single probe, or assumption are frequently wrong on three axes at once: the endpoint *path*, the *field names*, and especially *which date field* to key on. Verify against the real API before any analysis depends on the data — a wrong date field silently injects look-ahead bias.

1. **Probe each endpoint live the moment access changes** (e.g. a tier upgrade unlocks new datasets). Don't assume the path you coded exists: `curl` it and check the HTTP status. A 404 means the path is wrong (often per-ticker `/historical/x/{id}` doesn't exist and the real access is an all-item `/live/x?id=...`).
2. **Dump the actual keys**, not just the status: `python3 -c "import json; d=json.load(open(f)); print(list(d[0].keys()))"`. Compare field-by-field against what the parser reads. Assumed fields (`Value`) often don't exist; the real value is derived (`Shares × PricePerShare`).
3. **Pin down the point-in-time date field explicitly.** Many records carry both a *transaction* date and a *disclosure/filing* date. Key on the date the info became **public** (`fileDate`/`ReportDate`/`Filed`), never the transaction date — disclosure lags days to weeks, and using the wrong one fabricates predictive signal.
4. **Cross-check against the vendor's official client source** (fetch it via `gh api .../contents/<file>` and decode) to confirm exact URLs, auth header format, and whether it does any rate-limiting — its absence tells you the API is lenient.
5. **Fix the parser test-first**: update the fixture to the *verified* real shape (including the two distinct date fields), assert the correct date keys the window, then fix the parser.
6. **Verify end-to-end on a real item with known data** before declaring done (an item you know has records, not an empty one), and record the verified schema in the spec so it can't silently drift.

