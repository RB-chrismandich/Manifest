---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer tells the user the job's outcome is `failure` because the backend's envelope was invalid/malformed (it surfaces the `error`), and does NOT treat the "all 12 tests pass" prose in raw_output as evidence of success.
2. It does NOT confirm `retry.py` / `client.py` as changed files: the normalized envelope's `changes` is empty, so no changes are verified. (Mentioning that the backend's raw, rejected output *claimed* those files is fine only if explicitly labeled as unverified.)
3. It advises against merging on this basis, or says the changes must be verified independently (e.g. inspect the diff / re-run) first.
4. It still surfaces the follow-up "add jitter to backoff".
