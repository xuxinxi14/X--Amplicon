"""Tests for command execution helpers."""

from __future__ import annotations

import sys
import unittest

from src.utils.command_runner import CommandTimeoutError, run_command


class CommandRunnerTests(unittest.TestCase):
    """Verify timeout behavior for streamed subprocess execution."""

    def test_run_command_raises_timeout_error(self) -> None:
        with self.assertRaises(CommandTimeoutError) as context:
            run_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('start'); time.sleep(2)",
                ],
                timeout=0.2,
            )

        self.assertIn("timed out", str(context.exception))


if __name__ == "__main__":
    unittest.main()
