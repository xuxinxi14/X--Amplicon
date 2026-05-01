"""Helpers for running external commands with streamed output."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import IO, Mapping, Optional, Sequence


@dataclass
class CommandResult:
    """Container for a completed command execution."""

    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str


class CommandExecutionError(RuntimeError):
    """Raised when an external command cannot be executed successfully."""

    def __init__(
        self,
        command: Sequence[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        message: Optional[str] = None,
    ) -> None:
        rendered_command = format_command(command)
        error_message = message or (
            f"Command failed with exit code {returncode}: {rendered_command}"
        )
        super().__init__(error_message)
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CommandTimeoutError(CommandExecutionError):
    """Raised when an external command exceeds the configured timeout."""

    def __init__(
        self,
        command: Sequence[str],
        timeout: float,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        timeout_text = f"{timeout:g}"
        super().__init__(
            command,
            returncode,
            stdout=stdout,
            stderr=stderr,
            message=(
                f"Command timed out after {timeout_text} seconds: "
                f"{format_command(command)}"
            ),
        )
        self.timeout = timeout


def format_command(command: Sequence[str]) -> str:
    """Render a command list as a printable string."""

    normalized = [str(part) for part in command]
    try:
        return shlex.join(normalized)
    except AttributeError:
        return " ".join(normalized)


def _stream_pipe(
    stream: Optional[IO[str]],
    sink: IO[str],
    buffer: list[str],
) -> None:
    """Continuously forward a subprocess stream into a local output stream."""

    if stream is None:
        return

    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            sink.write(line)
            sink.flush()
            buffer.append(line)
    finally:
        stream.close()


def run_command(
    command: Sequence[str],
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    check: bool = True,
    timeout: Optional[float] = None,
) -> CommandResult:
    """Run an external command and stream stdout/stderr in real time."""

    if not command:
        raise ValueError("Command list cannot be empty.")

    resolved_timeout: Optional[float] = None
    if timeout is not None:
        try:
            resolved_timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a positive number of seconds.") from exc
        if resolved_timeout <= 0:
            raise ValueError("timeout must be a positive number of seconds.")

    normalized_command = [str(part) for part in command]
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(key): str(value) for key, value in env.items()})

    print(f"[command_runner] Running command: {format_command(normalized_command)}")

    process: Optional[subprocess.Popen[str]] = None
    stdout_buffer: list[str] = []
    stderr_buffer: list[str] = []

    try:
        process = subprocess.Popen(
            normalized_command,
            cwd=cwd,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise CommandExecutionError(
            normalized_command,
            -1,
            message=(
                f"Command not found: {normalized_command[0]}. "
                "Please ensure it is installed and available on PATH."
            ),
        ) from exc
    except OSError as exc:
        raise CommandExecutionError(
            normalized_command,
            -1,
            message=f"Unable to start command: {format_command(normalized_command)}",
        ) from exc

    stdout_thread = threading.Thread(
        target=_stream_pipe,
        args=(process.stdout, sys.stdout, stdout_buffer),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_pipe,
        args=(process.stderr, sys.stderr, stderr_buffer),
        daemon=True,
    )

    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    try:
        return_code = process.wait(timeout=resolved_timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        raise
    finally:
        stdout_thread.join()
        stderr_thread.join()

    if timed_out:
        raise CommandTimeoutError(
            normalized_command,
            resolved_timeout if resolved_timeout is not None else 0.0,
            return_code,
            stdout="".join(stdout_buffer),
            stderr="".join(stderr_buffer),
        )

    result = CommandResult(
        command=tuple(normalized_command),
        returncode=return_code,
        stdout="".join(stdout_buffer),
        stderr="".join(stderr_buffer),
    )

    if check and result.returncode != 0:
        raise CommandExecutionError(
            result.command,
            result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result
