#!/usr/bin/env bash
set -euo pipefail
cat > modal.html <<'EOF'
<!doctype html>
<html lang="en">
<head><title>Account settings</title><link rel="stylesheet" href="modal.css"></head>
<body>
  <div class="modal" role="dialog" aria-labelledby="title">
    <h2 id="title">Account settings</h2>
    <img src="avatar.png">
    <div class="save" onclick="saveSettings()">Save</div>
    <p class="hint">Changes may take a moment to appear.</p>
  </div>
</body>
</html>
EOF
cat > modal.css <<'EOF'
.hint { color: #888888; background: #ffffff; }
EOF
