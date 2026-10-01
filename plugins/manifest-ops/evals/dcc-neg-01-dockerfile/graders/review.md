---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gives Dockerfile-specific advice: pin the base image (e.g. python:3.12-slim), copy requirements first for layer caching, use --no-cache-dir, add a non-root USER, add .dockerignore, and exec-form CMD.
2. It does NOT cite docker-compose commandment IDs (DC-NNN) or review compose-specific concerns.
