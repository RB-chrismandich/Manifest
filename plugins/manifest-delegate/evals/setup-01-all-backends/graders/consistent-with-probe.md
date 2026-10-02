---
type: llm
focus: trace
---
Pass only if ALL of these hold:
1. The trace shows at least one readiness probe was actually executed in this run (the plugin's `delegate.py setup`, or per-backend version/login checks).
2. Every backend state the final answer asserts is supported by probe output visible in the trace. If a probe errored or could not run, the answer says so plainly for the affected backends instead of asserting a state for them.
3. The answer does not claim any backend is ready/usable without probe evidence of readiness (installed AND authenticated AND enabled).
4. Remediation steps are tied to what the probe actually showed (the exact error, a named missing command, or a named config file); generic "check your installation" advice for a backend with no evidence fails.
