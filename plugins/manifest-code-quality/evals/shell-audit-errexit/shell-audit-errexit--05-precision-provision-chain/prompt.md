---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
New machine provisioning script, sources three helper libs. Please audit it for `set -e`/`pipefail` footguns before we roll it out to the fleet.

provision.sh:
```bash
#!/usr/bin/env bash
set -euo pipefail

source lib/os_detect.sh
source lib/pkg_install.sh
source lib/user_setup.sh

os="$(detect_os)" || { echo "provision: could not detect OS" >&2; exit 1; }
echo "detected OS: $os"

install_packages "$os"
setup_admin_user "deploy"

echo "provisioning complete"
```

lib/os_detect.sh:
```bash
detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "$ID"
  else
    echo "unknown"
  fi
}
```

lib/pkg_install.sh:
```bash
install_packages() {
  local os="$1"
  local count=0
  for pkg in curl git jq; do
    echo "installing $pkg for $os"
    count=$((count + 1))
  done
  echo "installed $count packages"
}
```

lib/user_setup.sh:
```bash
setup_admin_user() {
  local user="$1"
  id "$user" &>/dev/null && return 0
  useradd -m "$user"
  echo "created user $user"
}
```
