"""Bundled catalog of Claude Code's built-in tools.

The Claude Agent SDK does NOT expose its built-in tool catalog
programmatically — the canonical descriptions and input schemas live in
the Claude Code CLI binary and in Anthropic's tools-reference docs. To
keep AVP trajectories self-describing without forcing consumers to
cross-reference external docs, we ship a bundled snapshot of the
catalog here.

This is a maintained snapshot, not authoritative truth. When the
Claude Code CLI ships new built-ins or changes a schema, this file
falls behind. Trajectory consumers can detect that by reading the
`avp.tool.schema_source` / `avp.tool.schema_snapshot_date` attributes
on each `agent_started.data.tools[]` entry; both are emitted alongside
the schema so a consumer can decide how much to trust a particular
field shape.

Update cadence: bump `SCHEMA_SNAPSHOT_DATE` whenever you edit anything
in `CLAUDE_CODE_BUILTIN_TOOL_CATALOG` or in `CLAUDE_CODE_PRESET_TOOLS`.

Reference: https://code.claude.com/docs/en/tools-reference.md
"""

from __future__ import annotations

from typing import Any

# The version stamp callers receive on the wire. Increment the date when
# anything in this file changes so consumers can detect staleness.
SCHEMA_SOURCE = "avp-claude-agent-bundled"
SCHEMA_SNAPSHOT_DATE = "2026-05-11"


# Snapshot of the SDK's built-in tools that AVP surfaces on
# `agent_started.data.tools[]`. We omit a few tools deliberately:
#
#   - `PowerShell`: gated behind CLAUDE_CODE_USE_POWERSHELL_TOOL=1, not
#     part of the default surface.
#   - `Agent` (and its pre-2.1.63 alias `Task`): subagent dispatch is
#     surfaced via the dedicated `subagent_invoked` / `subagent_returned`
#     events, not as a dispatchable tool on the catalog.
#   - `EnterWorktree` / `ExitWorktree`: worktree lifecycle, not a
#     model-facing tool.
#   - Interactive-only tools (`AskUserQuestion`, `EnterPlanMode`,
#     `TaskCreate` / `TaskGet` / `TaskList` / `TaskUpdate`, etc.):
#     unavailable to the Agent SDK / headless context this package
#     wraps. The Agent SDK uses `TodoWrite` for session task tracking.
#
# This tuple is exported publicly so a Commission author writing
# `enabled_builtin_tools` can `from avp_claude_agent import
# CLAUDE_CODE_PRESET_TOOLS` and filter the list.
CLAUDE_CODE_PRESET_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "NotebookEdit",
)


# Per-tool entry: short description + JSON Schema input shape. Keys
# match `CLAUDE_CODE_PRESET_TOOLS`. Schemas use draft-2020-12 conventions
# (the same shape AVP's other schemas use); consumers needing strict
# validation should still treat these as best-effort, hence the
# `schema_source` tag on every emission.
CLAUDE_CODE_BUILTIN_TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "Read": {
        "description": "Reads the contents of a file. Returns text with line numbers. Handles images, PDFs, and Jupyter notebooks specially.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional line number to start reading from.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional number of lines to read.",
                },
                "pages": {
                    "type": "string",
                    "description": 'Page range for PDFs, e.g. "1-5". Up to 20 pages per call.',
                },
            },
            "required": ["file_path"],
        },
    },
    "Write": {
        "description": "Creates a new file or overwrites an existing one with the given content. Read-before-overwrite applies to existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content to write.",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    "Edit": {
        "description": "Performs exact string replacement in a file. Old string must appear once unless replace_all is set. Read-before-edit applies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find. Must match a single occurrence unless replace_all is true.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace every occurrence of old_string instead of requiring uniqueness.",
                    "default": False,
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    "Glob": {
        "description": "Finds files by name pattern (standard glob syntax including ** for recursion). Results sorted by mtime, capped at 100.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": 'Glob pattern, e.g. "**/*.ts" or "src/**/*.{js,ts}".',
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search under. Defaults to the working directory.",
                },
            },
            "required": ["pattern"],
        },
    },
    "Grep": {
        "description": "Searches file contents using ripgrep regex syntax. Respects .gitignore.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Ripgrep regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search. Defaults to the working directory.",
                },
                "glob": {
                    "type": "string",
                    "description": 'Filter results by glob, e.g. "*.py".',
                },
                "type": {
                    "type": "string",
                    "description": 'Filter by file type (ripgrep --type), e.g. "py" or "rust".',
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["files_with_matches", "content", "count"],
                    "description": "Result format. Defaults to files_with_matches.",
                },
                "-i": {
                    "type": "boolean",
                    "description": "Case-insensitive search.",
                },
                "-n": {
                    "type": "boolean",
                    "description": "Include line numbers (only meaningful with output_mode=content).",
                },
                "-A": {
                    "type": "integer",
                    "description": "Lines of context after each match.",
                },
                "-B": {
                    "type": "integer",
                    "description": "Lines of context before each match.",
                },
                "-C": {
                    "type": "integer",
                    "description": "Lines of context on each side of a match.",
                },
                "head_limit": {
                    "type": "integer",
                    "description": "Cap on results returned.",
                },
                "multiline": {
                    "type": "boolean",
                    "description": "Allow patterns to span line boundaries.",
                },
            },
            "required": ["pattern"],
        },
    },
    "Bash": {
        "description": "Executes a shell command. 2 minute default timeout (up to 10 minutes), 30k character output cap (up to 150k).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
                "description": {
                    "type": "string",
                    "description": "Short human-readable description of what the command does.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds. Max 600000 (10 minutes).",
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Run the command in the background and return a task handle instead of waiting.",
                    "default": False,
                },
            },
            "required": ["command"],
        },
    },
    "WebFetch": {
        "description": "Fetches a URL, converts HTML to Markdown, and runs a small model with the given prompt over the result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "Fully qualified URL. HTTP is auto-upgraded to HTTPS.",
                },
                "prompt": {
                    "type": "string",
                    "description": "What to extract from the page. The fetched content is processed against this prompt before reaching Claude.",
                },
            },
            "required": ["url", "prompt"],
        },
    },
    "WebSearch": {
        "description": "Runs a web search and returns titles + URLs. Does not fetch the result pages; pair with WebFetch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 2,
                    "description": "Search query.",
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict results to these domains. Cannot be combined with blocked_domains.",
                },
                "blocked_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude these domains. Cannot be combined with allowed_domains.",
                },
            },
            "required": ["query"],
        },
    },
    "TodoWrite": {
        "description": "Manages the session task checklist. Replaces the full todo list each call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The task description (imperative form).",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current task status.",
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "Present-continuous form shown in the spinner when status is in_progress.",
                            },
                        },
                        "required": ["content", "status", "activeForm"],
                    },
                    "description": "Full replacement list of tasks for the session.",
                },
            },
            "required": ["todos"],
        },
    },
    "NotebookEdit": {
        "description": "Modifies a Jupyter notebook one cell at a time. Replace, insert, or delete a cell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Absolute path to the .ipynb file.",
                },
                "new_source": {
                    "type": "string",
                    "description": "New cell source (for replace/insert).",
                },
                "cell_id": {
                    "type": "string",
                    "description": 'Target cell id. Omitted with edit_mode=insert means "insert at the start."',
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "Required when edit_mode is insert.",
                },
                "edit_mode": {
                    "type": "string",
                    "enum": ["replace", "insert", "delete"],
                    "description": "What to do with the target cell. Defaults to replace.",
                    "default": "replace",
                },
            },
            "required": ["notebook_path", "new_source"],
        },
    },
}


# Sanity check: every preset name has a catalog entry and vice versa.
# Drift between the two would mean we silently emit name-only entries
# for a tool we *do* have schema data for, or claim a schema for a tool
# we don't surface. Fail at import rather than at the wire.
_preset_set = set(CLAUDE_CODE_PRESET_TOOLS)
_catalog_set = set(CLAUDE_CODE_BUILTIN_TOOL_CATALOG.keys())
if _preset_set != _catalog_set:
    missing_in_catalog = _preset_set - _catalog_set
    missing_in_preset = _catalog_set - _preset_set
    raise RuntimeError(
        f"avp_claude_agent.builtin_tools: preset / catalog mismatch. "
        f"In preset but missing from catalog: {sorted(missing_in_catalog)}. "
        f"In catalog but missing from preset: {sorted(missing_in_preset)}."
    )
