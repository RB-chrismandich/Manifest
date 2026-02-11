#!/bin/bash
# Fix Python user scripts PATH issue

PYTHON_USER_BIN="$HOME/Library/Python/3.9/bin"
SHELL_RC=""

# Detect shell
if [[ -n "$ZSH_VERSION" ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -n "$BASH_VERSION" ]]; then
    SHELL_RC="$HOME/.bashrc"
    # macOS uses .bash_profile for login shells
    if [[ "$(uname)" == "Darwin" ]] && [[ -f "$HOME/.bash_profile" ]]; then
        SHELL_RC="$HOME/.bash_profile"
    fi
fi

echo "Fixing Python PATH..."
echo ""

# Check if already in PATH
if echo "$PATH" | grep -q "$PYTHON_USER_BIN"; then
    echo "✓ Python user bin already in PATH"
    exit 0
fi

# Add to shell RC file
if [[ -n "$SHELL_RC" ]]; then
    echo "Adding to $SHELL_RC..."
    echo "" >> "$SHELL_RC"
    echo "# Python user scripts (added by fix_python_path.sh)" >> "$SHELL_RC"
    echo "export PATH=\"\$HOME/Library/Python/3.9/bin:\$PATH\"" >> "$SHELL_RC"
    echo "✓ Added to $SHELL_RC"
    echo ""
    echo "Run: source $SHELL_RC"
    echo "Or: Open a new terminal"
else
    echo "⚠ Could not detect shell RC file"
    echo ""
    echo "Manually add this to your shell profile:"
    echo "  export PATH=\"\$HOME/Library/Python/3.9/bin:\$PATH\""
fi
