#!/bin/bash
# Sync Phase 3 Changes from Deployed Location to Project Repository
# This ensures all Phase 3 changes are version controlled

set -e

REPO_ROOT="/Users/charlemagne/Documents/GitHub/Manifest"
DEPLOYED_ROOT="$HOME/.claude"

# Colors (used in echo -e throughout)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Syncing Phase 3 Changes to Project Repo     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════╝${NC}"
echo ""

# Track changes
CHANGES_MADE=0

# Function to sync file
sync_file() {
    local src="$1"
    local dst="$2"

    if [[ ! -f "$src" ]]; then
        echo -e "${YELLOW}⚠ Source not found: $src${NC}"
        return
    fi

    # Create destination directory if needed
    mkdir -p "$(dirname "$dst")"

    # Check if file differs
    if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
        echo -e "  ${GREEN}✓${NC} Already synced: $(basename "$dst")"
    else
        cp "$src" "$dst"
        chmod --reference="$src" "$dst" 2> /dev/null || chmod 644 "$dst"
        ((CHANGES_MADE++))
        echo -e "  ${BLUE}→${NC} Synced: $(basename "$dst")"
    fi
}

# Function to show file size comparison
compare_files() {
    local file1="$1"
    local file2="$2"

    if [[ -f "$file1" ]] && [[ -f "$file2" ]]; then
        local lines1
        lines1=$(wc -l < "$file1")
        local lines2
        lines2=$(wc -l < "$file2")
        local diff=$((lines2 - lines1))

        if [[ $diff -gt 0 ]]; then
            echo -e "    ${YELLOW}Project: $lines1 lines → Deployed: $lines2 lines (+$diff)${NC}"
        fi
    fi
}

echo -e "${BLUE}[1/4] Syncing Core Scripts${NC}"
echo ""

# Main parallel_agent.py (Phase 3 version)
echo "Syncing: parallel_agent.py"
compare_files \
    "$REPO_ROOT/.claude/scripts/parallel_agent.py" \
    "$DEPLOYED_ROOT/scripts/parallel_agent.py"
sync_file \
    "$DEPLOYED_ROOT/scripts/parallel_agent.py" \
    "$REPO_ROOT/.claude/scripts/parallel_agent.py"

# Updated requirements.txt
echo "Syncing: requirements.txt"
sync_file \
    "$DEPLOYED_ROOT/scripts/requirements.txt" \
    "$REPO_ROOT/.claude/scripts/requirements.txt"

# Test files
echo "Syncing: test_parallel_agent.py"
sync_file \
    "$DEPLOYED_ROOT/scripts/test_parallel_agent.py" \
    "$REPO_ROOT/.claude/scripts/test_parallel_agent.py"

echo ""
echo -e "${BLUE}[2/4] Syncing Configuration Files${NC}"
echo ""

# Updated parallel_agent.yml (with synthesis + streaming sections)
echo "Syncing: parallel_agent.yml"
sync_file \
    "$DEPLOYED_ROOT/config/parallel_agent.yml" \
    "$REPO_ROOT/.claude/config/parallel_agent.yml"

echo ""
echo -e "${BLUE}[3/4] Syncing Testing Documentation${NC}"
echo ""

# Testing documentation
echo "Syncing: E2E_TESTING_GUIDE.md"
sync_file \
    "$DEPLOYED_ROOT/scripts/E2E_TESTING_GUIDE.md" \
    "$REPO_ROOT/.claude/scripts/E2E_TESTING_GUIDE.md"

echo "Syncing: TESTING_QUICK_START.md"
sync_file \
    "$DEPLOYED_ROOT/scripts/TESTING_QUICK_START.md" \
    "$REPO_ROOT/.claude/scripts/TESTING_QUICK_START.md"

echo "Syncing: README_TESTING.md"
sync_file \
    "$DEPLOYED_ROOT/scripts/README_TESTING.md" \
    "$REPO_ROOT/.claude/scripts/README_TESTING.md"

echo "Syncing: PYTHON_PHASE3_COMPLETE.md"
sync_file \
    "$DEPLOYED_ROOT/scripts/PYTHON_PHASE3_COMPLETE.md" \
    "$REPO_ROOT/.claude/scripts/PYTHON_PHASE3_COMPLETE.md"

echo "Syncing: run_e2e_tests.sh"
sync_file \
    "$DEPLOYED_ROOT/scripts/run_e2e_tests.sh" \
    "$REPO_ROOT/.claude/scripts/run_e2e_tests.sh"

echo ""
echo -e "${BLUE}[4/4] Verification${NC}"
echo ""

# Verify key files
echo "Verifying synced files..."

FILES_TO_CHECK=(
    ".claude/scripts/parallel_agent.py"
    ".claude/scripts/requirements.txt"
    ".claude/scripts/test_parallel_agent.py"
    ".claude/config/parallel_agent.yml"
    ".claude/scripts/E2E_TESTING_GUIDE.md"
    ".claude/scripts/TESTING_QUICK_START.md"
    ".claude/scripts/README_TESTING.md"
    ".claude/scripts/PYTHON_PHASE3_COMPLETE.md"
    ".claude/scripts/run_e2e_tests.sh"
)

ALL_PRESENT=true
for file in "${FILES_TO_CHECK[@]}"; do
    if [[ -f "$REPO_ROOT/$file" ]]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${YELLOW}✗${NC} $file (missing)"
        ALL_PRESENT=false
    fi
done

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

if $ALL_PRESENT; then
    echo -e "${GREEN}✅ All Phase 3 files synced to project repository${NC}"
else
    echo -e "${YELLOW}⚠ Some files missing, check output above${NC}"
fi

echo -e "Files updated: ${BLUE}$CHANGES_MADE${NC}"
echo ""

# Check if we're in a git repo
if git -C "$REPO_ROOT" rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${BLUE}Git Status:${NC}"
    echo ""

    cd "$REPO_ROOT"

    # Show modified files
    if git diff --name-only | grep -q '.claude'; then
        echo "Modified files:"
        git diff --name-only | grep '.claude' | sed 's/^/  /'
        echo ""
    fi

    # Show new files
    if git ls-files --others --exclude-standard | grep -q '.claude'; then
        echo "New files:"
        git ls-files --others --exclude-standard | grep '.claude' | sed 's/^/  /'
        echo ""
    fi

    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Review changes: git diff .claude/"
    echo "  2. Stage changes: git add .claude/"
    echo "  3. Commit: git commit -m 'feat: Phase 3 implementation - logging, validation, synthesis, streaming'"
    echo "  4. Push: git push"
else
    echo -e "${YELLOW}Not a git repository, skipping git status${NC}"
fi

echo ""
echo -e "${GREEN}✓ Sync complete!${NC}"
