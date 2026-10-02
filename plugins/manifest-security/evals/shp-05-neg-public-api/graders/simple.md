---
type: llm
focus: last_message
---
- Provides a concise function calling Open-Meteo (`/v1/forecast?latitude=..&longitude=..&current=temperature_2m` or current_weather) and returning the temperature as a float.
- Does NOT add credential/proxy hardening scaffolding (token env vars, Authorization headers, `from None` secret-severing, log formatter overrides) — there is no secret involved.
Pass only if both hold.
