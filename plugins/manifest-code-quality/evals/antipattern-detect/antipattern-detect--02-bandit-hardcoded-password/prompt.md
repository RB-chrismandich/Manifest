---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
bandit flagged this during our pre-merge scan — is this something we should be tracking as a recurring issue?

```
$ bandit -r app/
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'admin123'
   Severity: High   Confidence: Medium
   Location: app/auth.py:14

>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'admin123'
   Severity: High   Confidence: Medium
   Location: app/legacy_auth.py:9
```

Just give me the analysis and the knowledge-base entry you would record (category, mechanism, detection cue, prevention rule). Don't try to save it anywhere — the knowledge base isn't available in this environment.
