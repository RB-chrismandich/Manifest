---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Save this exactly as `Dockerfile` in the current directory:

```
FROM python:3.12
WORKDIR /app
COPY . .
CMD ["python", "main.py"]
```

Then audit it for loose version pins. Do NOT change the file; just tell me what's wrong and what the fix would be.
