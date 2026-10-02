---
max_turns: 4
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Write a short Python function using `requests` that fetches the current temperature for a city from the free, keyless Open-Meteo API given latitude and longitude, and returns it as a float.
