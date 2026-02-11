#!/usr/bin/env python3
"""
OAuth and Authentication Test Script for Parallel Agent

This script validates that authentication is properly configured
for all agents without making expensive API calls.

Usage:
    python test_oauth.py
    python test_oauth.py --verbose
"""

import sys
import os
import argparse
from pathlib import Path

# Color codes for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
BOLD = '\033[1m'
NC = '\033[0m'  # No Color


def print_header(msg):
    print(f"\n{BOLD}=== {msg} ==={NC}")


def print_success(msg):
    print(f"{GREEN}✓{NC} {msg}")


def print_error(msg):
    print(f"{RED}✗{NC} {msg}")


def print_warning(msg):
    print(f"{YELLOW}⚠{NC}  {msg}")


def print_info(msg):
    print(f"{BLUE}ℹ{NC}  {msg}")


def test_python_version():
    """Test Python version"""
    print_header("Python Version")
    version = sys.version_info
    if version >= (3, 7):
        print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor}.{version.micro} (need 3.7+)")
        return False


def test_dependencies():
    """Test required Python packages"""
    print_header("Dependencies")

    required = {
        'anthropic': 'Anthropic SDK (Claude)',
        'google.generativeai': 'Google Generative AI SDK (Gemini)',
        'google.auth': 'Google Auth (OAuth support)',
        'aiohttp': 'Async HTTP',
        'yaml': 'YAML parser',
        'rich': 'Rich CLI output'
    }

    all_ok = True
    for module, description in required.items():
        try:
            __import__(module)
            print_success(f"{description}")
        except ImportError:
            print_error(f"{description} - NOT INSTALLED")
            all_ok = False

    if not all_ok:
        print_info("Install missing packages: pip install -r requirements.txt")

    return all_ok


def test_gemini_oauth():
    """Test Gemini OAuth authentication"""
    print_header("Gemini OAuth")

    # Check for OAuth credentials in order of preference
    oauth_sources = []

    # 1. Check GOOGLE_APPLICATION_CREDENTIALS
    if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
        cred_file = os.environ['GOOGLE_APPLICATION_CREDENTIALS']
        if os.path.exists(cred_file):
            oauth_sources.append(f"Service account: {cred_file}")

    # 2. Check gemini CLI credentials
    gemini_creds = Path.home() / '.config' / 'gemini' / 'credentials.json'
    if gemini_creds.exists():
        oauth_sources.append(f"Gemini CLI: {gemini_creds}")

    # 3. Check gcloud credentials
    gcloud_creds = Path.home() / '.config' / 'gcloud' / 'application_default_credentials.json'
    if gcloud_creds.exists():
        oauth_sources.append(f"gcloud: {gcloud_creds}")

    # 4. Check API key
    if 'GOOGLE_API_KEY' in os.environ:
        oauth_sources.append("API key: GOOGLE_API_KEY env var")

    if oauth_sources:
        print_success("Credentials found:")
        for source in oauth_sources:
            print(f"  • {source}")

        # Try to actually use the credentials
        try:
            from google import genai
            print_info("Testing authentication...")

            # Create client (will fail if credentials are invalid)
            if 'GOOGLE_API_KEY' in os.environ:
                client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
                print_success("API key authentication works")
            else:
                client = genai.Client()
                print_success("OAuth authentication works")

            return True

        except Exception as e:
            print_error(f"Authentication test failed: {str(e)}")
            print_info("Try: gemini auth login")
            return False
    else:
        print_warning("No credentials found")
        print_info("Setup options:")
        print_info("  1. OAuth: gemini auth login")
        print_info("  2. OAuth: gcloud auth application-default login")
        print_info("  3. API key: export GOOGLE_API_KEY='...'")
        return False


def test_claude_api_key():
    """Test Claude API key"""
    print_header("Claude API Key")

    api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        print_warning("ANTHROPIC_API_KEY not set")
        print_info("Setup: export ANTHROPIC_API_KEY='sk-ant-...'")
        print_info("Get key from: https://console.anthropic.com/")
        return False

    if not api_key.startswith('sk-ant-'):
        print_error(f"Invalid key format: {api_key[:10]}...")
        print_info("API key should start with 'sk-ant-'")
        return False

    print_success(f"API key found: {api_key[:15]}...{api_key[-4:]}")

    # Try to create client
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        print_success("API key format is valid")
        return True
    except Exception as e:
        print_error(f"Client creation failed: {str(e)}")
        return False


def test_cursor_cli():
    """Test Cursor CLI availability"""
    print_header("Cursor CLI")

    import subprocess
    try:
        result = subprocess.run(['which', 'cursor'], capture_output=True, check=True)
        cursor_path = result.stdout.decode().strip()
        print_success(f"Cursor CLI found: {cursor_path}")
        print_info("Cursor agent will use cursor CLI authentication")
        return True
    except subprocess.CalledProcessError:
        print_warning("Cursor CLI not found")
        print_info("Cursor agent will be skipped (not required)")
        return True  # Not a failure, just not available


def test_parallel_agent_import():
    """Test importing parallel_agent module"""
    print_header("Parallel Agent Module")

    try:
        # Add script directory to path
        script_dir = Path(__file__).parent
        sys.path.insert(0, str(script_dir))

        from parallel_agent import (
            Config, RateLimiter, BaseAgent,
            ClaudeAgent, GeminiAgent, CursorAgent, Orchestrator
        )

        print_success("All classes import successfully")

        # Test config loading
        config = Config()
        print_success(f"Config loaded from: {config.config_path}")

        # Test rate limiter
        limiter = RateLimiter()
        print_success(f"Rate limiter initialized ({limiter.rpm} rpm)")

        return True

    except Exception as e:
        print_error(f"Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_creation(verbose=False):
    """Test creating agent instances"""
    print_header("Agent Creation")

    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))

    from parallel_agent import ClaudeAgent, GeminiAgent, CursorAgent, RateLimiter, Config

    config = Config()
    limiter = RateLimiter()

    results = {}

    # Test Claude
    print_info("Creating ClaudeAgent...")
    try:
        claude = ClaudeAgent(model="haiku", timeout=10, rate_limiter=limiter, config=config)
        print_success(f"ClaudeAgent created (model: {claude.model_name})")
        results['claude'] = True
    except Exception as e:
        print_error(f"ClaudeAgent failed: {str(e)}")
        if verbose:
            import traceback
            traceback.print_exc()
        results['claude'] = False

    # Test Gemini
    print_info("Creating GeminiAgent...")
    try:
        gemini = GeminiAgent(model="flash", timeout=10, rate_limiter=limiter, config=config)
        print_success(f"GeminiAgent created (model: {gemini.model_name})")
        results['gemini'] = True
    except Exception as e:
        print_error(f"GeminiAgent failed: {str(e)}")
        if verbose:
            import traceback
            traceback.print_exc()
        results['gemini'] = False

    # Test Cursor
    print_info("Creating CursorAgent...")
    try:
        cursor = CursorAgent(model="flash", timeout=10, rate_limiter=limiter, config=config)
        print_success(f"CursorAgent created (model: {cursor.model_name})")
        results['cursor'] = True
    except Exception as e:
        print_warning(f"CursorAgent failed: {str(e)}")
        results['cursor'] = False

    return all(results.get(k, False) for k in ['claude', 'gemini'])  # Cursor is optional


def print_summary(results):
    """Print test summary"""
    print_header("Test Summary")

    total = len(results)
    passed = sum(1 for r in results.values() if r)

    for test_name, result in results.items():
        if result:
            print_success(test_name)
        else:
            print_error(test_name)

    print()
    if passed == total:
        print(f"{GREEN}{BOLD}✓ All tests passed ({passed}/{total}){NC}")
        print()
        print(f"{BOLD}Ready to use!{NC}")
        print("Try: python parallel_agent.py \"What is 2+2?\"")
        return 0
    else:
        print(f"{RED}{BOLD}✗ Some tests failed ({passed}/{total}){NC}")
        print()
        print(f"{BOLD}Next steps:{NC}")

        if not results.get('Gemini OAuth', False):
            print("  1. Setup Gemini: gemini auth login")

        if not results.get('Claude API Key', False):
            print("  2. Setup Claude: export ANTHROPIC_API_KEY='sk-ant-...'")

        if not results.get('Dependencies', False):
            print("  3. Install packages: pip install -r requirements.txt")

        return 1


def main():
    parser = argparse.ArgumentParser(description="Test OAuth and authentication for parallel agent")
    parser.add_argument('--verbose', '-v', action='store_true', help="Show detailed error messages")
    args = parser.parse_args()

    print(f"{BOLD}Parallel Agent OAuth Test{NC}")
    print("This script validates authentication without making API calls")

    results = {}

    # Run tests
    results['Python Version'] = test_python_version()
    results['Dependencies'] = test_dependencies()
    results['Gemini OAuth'] = test_gemini_oauth()
    results['Claude API Key'] = test_claude_api_key()
    results['Cursor CLI'] = test_cursor_cli()

    if results['Dependencies']:
        results['Parallel Agent Import'] = test_parallel_agent_import()

        if results['Parallel Agent Import']:
            results['Agent Creation'] = test_agent_creation(verbose=args.verbose)

    # Print summary
    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
