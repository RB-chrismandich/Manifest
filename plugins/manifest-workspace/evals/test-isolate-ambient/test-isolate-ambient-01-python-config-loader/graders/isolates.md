---
type: llm
focus: {source: file, path: test_configload.py}
weight: 2
---
Pass only if ALL hold:
1. Every test controls BOTH ambient inputs: `XDG_CONFIG_HOME` (set to a tmp fixture or deleted) AND the home directory (`HOME` set to a tmp dir via monkeypatch or `mock.patch.dict(os.environ, ...)`, or `Path.home` patched to a tmp path), so the real config can never be read. Controlling only one is a fail, because the code falls back from one to the other.
2. There is a test for the missing-config case asserting the explicit degraded result (`status == "degraded"`), with the fixture dir empty.
3. There is a test for the present-config case that writes a fixture config and asserts values from it.
4. It varies the decisive input (config present vs absent) inside the tests rather than depending on what exists on the machine.
