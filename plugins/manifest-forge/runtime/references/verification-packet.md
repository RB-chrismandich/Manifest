# Verification reviewer packet boundary

`verification_gate.sh review` requires Python 3, the shipped audit redactor,
packet verifier and detector configuration, and **Gitleaks on PATH**. The
repository pins and tests Gitleaks 8.30.1 in `config/toolchain.lock.json`; install
that version through your trusted tool provisioning before using this gate.
The pure `decide` subcommand does not require Gitleaks.

The gate scrubs complete JSON credential fields (including escaped field names),
then applies the existing audit redactor. Unstructured credential assignments (including YAML and shell assignments)
require local review before any regex can erase their context. Before invoking the reviewer, Gitleaks scans the exact
sanitized packet and an additional JSON-decoded, diff-prefix-normalized view.
Built-in rules and a low-entropy credential-field rule apply. Project allowlists,
ignore files, inline `gitleaks:allow` comments and Gitleaks environment overrides
cannot waive this handoff check. Only explicit redaction markers are exempted
from the extra credential-field rule.

A missing control, detector error/timeout, malformed report, or residual finding
returns the existing `BLOCKED` / `reviewer_error:true` result without invoking the
reviewer. Diagnostic output does not print packet contents or detector findings.
The packet and intermediate stay in a private temporary directory and are removed
on return. There is no fallback that sends the original packet.

This is a finite detection policy, **not proof that arbitrary text is secret-free**.
Unknown credential formats, encodings beyond the detector's decoding depth, and
context-dependent secrets can evade detection. Keep credentials out of issues and
diffs; review sensitive material locally. The configured reviewer command and
installed tools are trusted. Existing audit-log behavior outside this gate is
unchanged.
