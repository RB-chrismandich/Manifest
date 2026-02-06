## 2026-02-06 - [Insecure Secret Storage in Shell Profiles]
**Vulnerability:** The `bootstrap.sh` script was appending the Gemini API key directly to the user's shell profile (e.g., `.zshrc`) in plaintext.
**Learning:** Shell profile files often have relaxed permissions (e.g., 644) and are frequently committed to dotfiles repositories, making them unsuitable for storing unencrypted secrets.
**Prevention:** Always write secrets to a dedicated file with restricted permissions (600) and `source` that file from the shell profile.
