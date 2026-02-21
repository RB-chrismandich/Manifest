import asyncio
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Mock external dependencies before import
sys.modules["rich"] = MagicMock()
sys.modules["rich.console"] = MagicMock()
sys.modules["rich.table"] = MagicMock()
sys.modules["rich.progress"] = MagicMock()
sys.modules["rich.live"] = MagicMock()
sys.modules["rich.panel"] = MagicMock()
sys.modules["yaml"] = MagicMock()
sys.modules["anthropic"] = MagicMock()
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()

# Since test is in the same directory as the module, we don't need to adjust sys.path if running from project root properly,
# but to be safe and consistent with test execution, we can ensure the current directory is in path.
# parallel_agent is in configs/claude/scripts/
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

# Now import
from parallel_agent import CursorAgent, CodexAgent, Config

class TestAgentSecurity(unittest.TestCase):
    def setUp(self):
        # Patch yaml.safe_load to return empty config
        self.yaml_patcher = patch('yaml.safe_load', return_value={})
        self.yaml_patcher.start()

        # Patch built-in open to avoid file not found errors when Config loads
        self.open_patcher = patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="{}")
        self.open_patcher.start()

        # Create config with mocked open/yaml
        self.config = Config()
        self.config.config = {} # Empty config

    def tearDown(self):
        self.yaml_patcher.stop()
        self.open_patcher.stop()

    def test_cursor_argument_injection_prevention(self):
        """Test that CursorAgent prevents argument injection"""
        # Use AsyncMock for create_subprocess_exec
        with patch('parallel_agent.asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            with patch('parallel_agent.CursorAgent._check_cursor_available', return_value=True):
                agent = CursorAgent(config=self.config)

                # Mock subprocess object returned by create_subprocess_exec
                mock_proc = MagicMock()
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_proc.returncode = 0
                mock_exec.return_value = mock_proc

                # Run agent
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                loop.run_until_complete(agent._execute_impl("--help", "prompt"))

                # Check arguments passed to create_subprocess_exec
                call_args = mock_exec.call_args
                if not call_args:
                    self.fail("create_subprocess_exec was not called")

                args = call_args[0] # positional args

                print(f"DEBUG: Cursor args: {args}")

                # We assert that "--" is present in the arguments list before the prompt
                self.assertIn("--", args, "CursorAgent missing '--' delimiter for prompt")

                # Verify prompt is after --
                dash_index = args.index("--")
                # Find index of prompt ("--help")
                try:
                    # Find last occurrence
                    prompt_index = len(args) - 1 - args[::-1].index("--help")
                except ValueError:
                    self.fail("Prompt '--help' not found in arguments")

                self.assertGreater(prompt_index, dash_index, "Prompt must come after '--'")

    def test_codex_argument_injection_prevention(self):
        """Test that CodexAgent prevents argument injection"""
        with patch('parallel_agent.asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
            with patch('shutil.which', return_value="/usr/bin/codex"):
                # Mock tempfile.NamedTemporaryFile
                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp_obj = MagicMock()
                    mock_temp_obj.__enter__.return_value.name = "/tmp/codex_out_123.txt"
                    mock_temp.return_value = mock_temp_obj

                    agent = CodexAgent(config=self.config)

                    # Mock subprocess
                    mock_proc = MagicMock()
                    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                    mock_proc.returncode = 0
                    mock_exec.return_value = mock_proc

                    # Run agent
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    loop.run_until_complete(agent._execute_impl("--help", "prompt"))

                    # Check arguments passed to create_subprocess_exec
                    call_args = mock_exec.call_args
                    if not call_args:
                        self.fail("create_subprocess_exec was not called")

                    args = call_args[0] # positional args

                    print(f"DEBUG: Codex args: {args}")

                    # We assert that "--" is present in the arguments list before the prompt
                    self.assertIn("--", args, "CodexAgent missing '--' delimiter for prompt")

                    # Verify prompt is after --
                    dash_index = args.index("--")
                    try:
                        prompt_index = len(args) - 1 - args[::-1].index("--help")
                    except ValueError:
                        self.fail("Prompt '--help' not found in arguments")

                    self.assertGreater(prompt_index, dash_index, "Prompt must come after '--'")

if __name__ == '__main__':
    unittest.main()
