---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Review this Dockerfile for best practices:

```dockerfile
FROM python:3
COPY . /app
RUN pip install -r /app/requirements.txt
CMD python /app/main.py
```
