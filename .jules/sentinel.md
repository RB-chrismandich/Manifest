## 2026-02-04 - Config File Eval Command Injection
**Vulnerability:** Evaluated parsed dynamic configuration variables using the `eval` command directly (e.g. `eval "$config_settings"`).
**Learning:** The `eval` pattern was used as a shortcut to inject dynamic settings parsed from user-controlled files (`.yml` configs) into the bash environment. This pattern introduces severe command injection risk if the configuration file is externally controlled.
**Prevention:** Instead of using `eval`, configuration parsed by commands like `awk` or Python should be parsed using a safe `while IFS='=' read -r var val; do` loop, utilizing `printf -v "$var" "%s" "$val"` and explicitly whitelisting allowed variables in a `case` statement.
