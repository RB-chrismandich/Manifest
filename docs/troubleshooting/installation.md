# Installation Problems

> Bootstrap, CLI installs, and PATH failures.

**Last Updated**: 2026-08-20

## Installation Issues

### Bootstrap Fails with "Permission denied"

**Symptom:**

```bash
./bootstrap.sh
-bash: ./bootstrap.sh: Permission denied
```

**Solution:**

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

**Cause:** Script not marked as executable

---

### Homebrew Installation Fails (macOS)

**Symptom:**

```text
Error: Homebrew installation failed
```

**Solution:**

```bash
# Install Homebrew manually
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Re-run bootstrap
./bootstrap.sh --skip-install
```

**Alternative:** Use `--skip-install` flag and install dependencies manually

---

### npm Install Fails

**Symptom:**

```text
npm ERR! code EACCES
npm ERR! syscall access
npm ERR! path /usr/local/lib/node_modules
```

**Solution:**

```bash
# Option 1: Use sudo (not recommended)
sudo npm install -g @anthropic-ai/claude-code
sudo npm install -g @google/gemini-cli

# Option 2: Fix npm permissions (recommended)
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc

# Retry installation
npm install -g @anthropic-ai/claude-code
npm install -g @google/gemini-cli
```

---

### Node.js Not Found (Linux)

**Symptom:**

```text
Error: Node.js not found
```

**Solution:**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nodejs npm

# RHEL/Fedora
sudo dnf install nodejs npm

# Arch
sudo pacman -S nodejs npm

# Verify installation
node --version
npm --version
```

---

---

[← Troubleshooting](README.md)
