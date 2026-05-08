"""ShellTools — a minimal local ToolDriver that gives the LLM a real bash /
read_file / write_file surface.

The agent is supposed to ship its own built-ins (per SPEC.md §8 the agent's
local-impl tools are agent-specific and not declared in Commission.tools). This
module is what avp-anthropic's CLI registers by default. Names match what the
simple-supervisor profiles expect:

  - bash         : run a shell command, capture stdout/stderr
  - read_file    : read a file by path
  - write_file   : write content to a path (overwrites)

All three are intentionally simple. Real-world supervisors will want sandboxing,
timeouts, path restrictions, line-limit pagination, etc. — out of scope for the
reference agent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from avp.agent.drivers import ToolDriver, ToolOutcome

# JSON Schemas suitable for passing to the Anthropic Messages API as tools[].
SHELL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "description": (
            "Run a shell command in the agent's working directory. Returns combined "
            "stdout+stderr (truncated at 8KB). Non-zero exit codes return the output "
            "with an error indicator."
        ),
        "input_schema": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a file's contents. Returns the file as a string.",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "description": "Path to read."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a path, overwriting any existing file. Creates parent dirs.",
        "input_schema": {
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string", "description": "Path to write."},
                "content": {"type": "string", "description": "Full file contents."},
            },
            "additionalProperties": False,
        },
    },
]

_LOCAL_NAMES = {schema["name"] for schema in SHELL_TOOL_SCHEMAS}

# Public tuple of shell-tool names. Commission authors building
# `commission.exposed` import this when they want to expose every
# shell built-in (`list(SHELL_TOOL_NAMES) + my_rpc_tool_names`) without
# duplicating the names by hand. Kept in sync with SHELL_TOOL_SCHEMAS.
SHELL_TOOL_NAMES: tuple[str, ...] = tuple(schema["name"] for schema in SHELL_TOOL_SCHEMAS)


class ShellTools(ToolDriver):
    """Local ToolDriver that handles bash / read_file / write_file."""

    def __init__(self, *, timeout_s: float = 30.0, max_output_bytes: int = 8192) -> None:
        self.timeout_s = timeout_s
        self.max_output_bytes = max_output_bytes

    def is_local(self, tool: str) -> bool:
        return tool in _LOCAL_NAMES

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        if tool == "bash":
            return self._run_bash(str(input.get("command", "")))
        if tool == "read_file":
            return self._read_file(str(input.get("path", "")))
        if tool == "write_file":
            return self._write_file(str(input.get("path", "")), str(input.get("content", "")))
        return ToolOutcome(error=f"shell_tools: unknown tool {tool!r}")

    def _run_bash(self, command: str) -> ToolOutcome:
        if not command:
            return ToolOutcome(error="bash: missing 'command' input")
        try:
            result = subprocess.run(
                ["sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ToolOutcome(error=f"bash: command exceeded {self.timeout_s}s timeout")
        out = (result.stdout or "") + (("\nSTDERR:\n" + result.stderr) if result.stderr else "")
        if len(out) > self.max_output_bytes:
            out = (
                out[: self.max_output_bytes] + f"\n... [truncated at {self.max_output_bytes} bytes]"
            )
        if result.returncode != 0:
            return ToolOutcome(
                output=f"(exit {result.returncode})\n{out}",
                duration_ms=1,
            )
        return ToolOutcome(output=out, duration_ms=1)

    def _read_file(self, path: str) -> ToolOutcome:
        if not path:
            return ToolOutcome(error="read_file: missing 'path' input")
        try:
            content = Path(path).read_text()
        except FileNotFoundError:
            return ToolOutcome(error=f"read_file: file not found: {path}")
        except OSError as e:
            return ToolOutcome(error=f"read_file: {e}")
        if len(content) > self.max_output_bytes:
            content = (
                content[: self.max_output_bytes]
                + f"\n... [truncated at {self.max_output_bytes} bytes]"
            )
        return ToolOutcome(output=content, duration_ms=1)

    def _write_file(self, path: str, content: str) -> ToolOutcome:
        if not path:
            return ToolOutcome(error="write_file: missing 'path' input")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        except OSError as e:
            return ToolOutcome(error=f"write_file: {e}")
        return ToolOutcome(output=f"wrote {len(content)} chars to {path}", duration_ms=1)
