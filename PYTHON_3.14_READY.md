# ✅ Bootstrap Updated for Python 3.14

**Date**: 2026-02-10
**Status**: Bootstrap now prefers Python 3.14 (latest stable)
**File Modified**: `bootstrap/lib/install.sh`

---

## 🎯 What Changed

### Before (Old Logic)

```bash
# Only recognized Python 3.9-3.13 as "good"
if [[ "$major" -eq 3 ]] && [[ "$minor" -ge 9 ]] && [[ "$minor" -le 13 ]]; then

# Generic candidates list
python_candidates=(
    "/usr/bin/python3"           # System Python first
    "/usr/local/bin/python3"     # Generic Homebrew
    "python3"
    "python"
)
```

**Result**: Preferred system Python 3.9.6 over newer versions

---

### After (New Logic)

```bash
# Now recognizes Python 3.9-3.20 as "good" (future-proof)
if [[ "$major" -eq 3 ]] && [[ "$minor" -ge 9 ]] && [[ "$minor" -le 20 ]]; then
    score=$((score + 100))
    # Bonus for Python 3.12+ (newer features, better performance)
    if [[ "$minor" -ge 12 ]]; then
        score=$((score + 10))
    fi
fi

# Specific stable versions checked first (highest priority)
python_candidates=(
    "/usr/local/bin/python3.14"  # Latest stable (Feb 2026)
    "/usr/local/bin/python3.13"  # Also stable
    "/usr/local/bin/python3.12"  # Very stable
    "/usr/bin/python3"           # System Python (fallback)
    "/usr/local/bin/python3"     # Generic Homebrew
    "python3"                    # PATH python3
    "python"                     # PATH python
)
```

**Result**: Will prefer Python 3.14 → 3.13 → 3.12 → system 3.9

---

## 🚀 How to Use

### Option 1: Install Python 3.14 and Re-run Bootstrap

```bash
# 1. Install Python 3.14
brew install python@3.14

# 2. Re-run bootstrap (will auto-detect 3.14)
cd /Users/charlemagne/Documents/GitHub/Manifest
./bootstrap.sh

# 3. Bootstrap will now use Python 3.14!
```

**Expected output**:

```text
→ Checking for Python...
✓ Python is installed (3.14.0)
ℹ Using: /usr/local/bin/python3.14
→ Installing Python dependencies for parallel_agent.py...
✓ Python dependencies installed
```

---

### Option 2: Just Install Python 3.14 (Manual)

```bash
# 1. Install Python 3.14
brew install python@3.14

# 2. Install dependencies
python3.14 -m pip install -r ~/.claude/scripts/requirements.txt --user

# 3. Test it works
python3.14 ~/.claude/scripts/parallel_agent.py --help

# 4. Use it directly
python3.14 ~/.claude/scripts/parallel_agent.py "test" --timeout 30
```

---

## 📊 Python Version Priority (After Update)

Bootstrap will choose Python in this order (highest to lowest score):

| Python | Location | Score | Status | Notes |
|--------|----------|-------|--------|-------|
| **3.14** | `/usr/local/bin/python3.14` | **110** | ⭐ Best | Latest stable, checked first |
| **3.13** | `/usr/local/bin/python3.13` | **110** | ✅ Great | Also very good |
| **3.12** | `/usr/local/bin/python3.12` | **110** | ✅ Great | Very stable |
| **3.11** | `/usr/local/bin/python3.11` | 100 | ✅ Good | Still supported |
| **3.10** | `/usr/local/bin/python3.10` | 100 | ✅ Good | Still supported |
| **3.9** | `/usr/bin/python3` | 110 | ⚠️ OK | EOL but works (+10 for /usr/bin) |
| **3.15a5** | `/usr/local/bin/python3` | **-900** | ❌ Avoid | Alpha = -1000 penalty |

**Key scoring rules**:

- ✅ Python 3.9-3.20: +100 points
- ✅ Python 3.12+: +10 bonus points
- ✅ `/usr/bin/python3`: +10 stability bonus
- ❌ Alpha/beta/rc: **-1000 penalty** (avoids unstable versions)

---

## ✅ What This Fixes

### Before (Using Python 3.9.6)

- ⚠️ Python 3.9 is past end-of-life
- ⚠️ FutureWarning messages
- ⚠️ No access to modern Python features

### After (Using Python 3.14)

- ✅ Latest stable Python (released Oct 2025)
- ✅ No EOL warnings
- ✅ Better performance
- ✅ Modern features
- ✅ Supported until Oct 2030

---

## 🧪 Test the Update

### Test 1: Verify Bootstrap Detects 3.14

```bash
# Install Python 3.14
brew install python@3.14

# Check bootstrap will find it
cd /Users/charlemagne/Documents/GitHub/Manifest
./bootstrap.sh --skip-install --skip-auth

# Look for this output:
# ✓ Python is installed (3.14.0)
# ℹ Using: /usr/local/bin/python3.14
```

---

### Test 2: Verify Alpha Versions Are Avoided

```bash
# If you have Python 3.15 alpha installed
ls -la /usr/local/bin/python3.15

# Bootstrap should SKIP it and use 3.14 or 3.9 instead
./bootstrap.sh --skip-install --skip-auth

# Should NOT see: "Using: /usr/local/bin/python3.15"
# Should see: "Using: /usr/local/bin/python3.14" or "Using: /usr/bin/python3"
```

---

### Test 3: Full Bootstrap with Python 3.14

```bash
# Complete bootstrap with Python 3.14
cd /Users/charlemagne/Documents/GitHub/Manifest

# Install Python 3.14 first
brew install python@3.14

# Run bootstrap
./bootstrap.sh

# Verify Phase 3 works
cd ~/.claude/scripts
./run_e2e_tests.sh
```

---

## 📝 Changes Summary

**Files Modified**: 1

- `bootstrap/lib/install.sh` (lines 99-141)

**Changes**:

1. Added specific Python version candidates (3.14, 3.13, 3.12)
2. Expanded supported version range to 3.9-3.20
3. Added bonus scoring for Python 3.12+
4. Reordered candidates to check specific versions first

**Impact**:

- ✅ Bootstrap will now prefer Python 3.14 (if installed)
- ✅ Still works with Python 3.9-3.13
- ✅ Avoids alpha/beta/rc versions (-1000 penalty)
- ✅ Future-proof for Python 3.15+ when stable

**Backward Compatibility**: ✅ Full

- Still works with Python 3.9+
- No breaking changes
- Falls back to system Python if needed

---

## 🎯 Recommended Action

### Immediate (5 minutes)

```bash
# Install Python 3.14
brew install python@3.14

# Re-run bootstrap
cd /Users/charlemagne/Documents/GitHub/Manifest
./bootstrap.sh

# Test Phase 3
cd ~/.claude/scripts
./run_e2e_tests.sh
```

### After Installation

```bash
# Verify Python version in use
python3.14 --version
# Python 3.14.0

# Test parallel agent
python3.14 ~/.claude/scripts/parallel_agent.py --check-credits

# No more EOL warnings! 🎉
```

---

## ✅ Summary

**Question**: What about Python 3.14?

**Answer**: ✅ **Python 3.14 is perfect!**

- Released Oct 2025 (stable for 4 months)
- Supported until Oct 2030
- Bootstrap now prefers it automatically

**Status**: Bootstrap updated and ready for Python 3.14

**Action**:

```bash
brew install python@3.14
./bootstrap.sh
```

**Result**: Phase 3 will use Python 3.14 (no EOL warnings, modern features, better performance) 🚀
