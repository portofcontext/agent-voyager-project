"""Confine an agent subprocess with srt (@anthropic-ai/sandbox-runtime).

**Onboarding contract: the only new dependency is `srt` itself.** `mode="auto"`
(the default) sandboxes when `srt` is on PATH and runs unsandboxed otherwise, so a
fresh clone works with no extra setup and runs become confined the moment someone
runs `npm install -g @anthropic-ai/sandbox-runtime`. `mode="on"` requires srt
(errors if missing, for CI / locked-down use); `mode="off"` never wraps.

The job here is to stop a model-driven agent from trashing the machine, not to
contain a determined adversary. The lever is WRITES: deny-by-default, allowing
only the run's own surface (its `--out` dir, the agent's install dir + HOME state,
an OS-temp scratch). Reads stay open minus a curated credential denylist. The
network is an allow-list (srt mandates one) seeded with the major model-provider
APIs so a sandboxed eval still reaches its model; the provider key travels in the
environment (srt passes env through), so auth is unaffected.

srt is macOS (Seatbelt) and Linux (bubblewrap) only; that matches AVP's
prebuilt-agent targets.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# srt forbids a bare "*", so the network allow-list is explicit. It's seeded with
# the major model-provider APIs (the agent calls whatever the commission's model
# resolves to) plus GitHub, since network is not the security lever here (writes
# are) and a too-narrow list would just break otherwise-valid runs.
DEFAULT_ALLOW_DOMAINS: tuple[str, ...] = (
    "api.anthropic.com",
    "*.anthropic.com",
    "api.openai.com",
    "*.openai.com",
    "generativelanguage.googleapis.com",
    "*.googleapis.com",
    "api.mistral.ai",
    "openrouter.ai",
    "github.com",
    "*.githubusercontent.com",
)

# macOS native-tls clients resolve cert trust via this Mach service; srt blocks it
# by default, so allow it or a sandboxed agent can't establish TLS. Linux ignores it.
_MACOS_TRUST_MACH_SERVICE = "com.apple.trustd.agent"

# Curated credential stores blocked from reads. Reads are otherwise open (locking
# all of $HOME fights uv / the agent runtimes); this just keeps obvious secrets out.
_DENY_READ = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.kube",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/.docker/config.json",
    "~/.config/gcloud",
    "~/.config/op",
    "~/Library/Keychains",
)


class SandboxUnavailable(Exception):
    """`--sandbox on` was requested but `srt` isn't installed."""


def available() -> bool:
    """True if the `srt` CLI is on PATH."""
    return shutil.which("srt") is not None


def decide(mode: str) -> tuple[bool, str | None]:
    """Resolve a `--sandbox` mode to (enabled, one-line note for the user).

    `off` -> never. `on` -> require srt (raises `SandboxUnavailable` if missing).
    `auto` -> sandbox iff srt is present; otherwise run unsandboxed and say so.
    """
    if mode == "off":
        return False, None
    if available():
        return True, "runs are sandboxed via srt"
    if mode == "on":
        raise SandboxUnavailable(
            "--sandbox on needs the `srt` CLI: npm install -g @anthropic-ai/sandbox-runtime"
        )
    return False, (
        "srt not installed — running unsandboxed. To confine agent runs: "
        "npm install -g @anthropic-ai/sandbox-runtime"
    )


def home_state_dirs() -> list[str]:
    """Existing HOME state roots an agent writes to at runtime (config / cache /
    data / the claude CLI's dir). Allowing these lets the agent manage its own
    state while the project dir and the rest of the machine stay read-only."""
    home = Path.home()
    candidates = [home / ".config", home / ".cache", home / ".local", home / ".claude"]
    return [str(p) for p in candidates if p.exists()]


def settings_file(
    directory: Path,
    *,
    write_paths: list[str],
    allow_domains: list[str] | None = None,
) -> Path:
    """Write an srt settings JSON into `directory` and return its path.

    Write paths are canonicalized (symlinks resolved) so the policy matches the
    real path the OS sees: on macOS the temp/workspace dirs live under `/var/...`,
    a symlink to `/private/var/...`, and Seatbelt evaluates the resolved path, so
    an unresolved entry would silently deny legitimate writes."""
    allow_write = list(dict.fromkeys(os.path.realpath(p) for p in write_paths))
    profile: dict = {
        "network": {
            "allowedDomains": list(dict.fromkeys([*DEFAULT_ALLOW_DOMAINS, *(allow_domains or [])])),
            "deniedDomains": [],
        },
        "filesystem": {
            "denyRead": list(_DENY_READ),
            "allowRead": [],
            "allowWrite": allow_write,
            "denyWrite": [],
        },
    }
    if sys.platform == "darwin":
        profile["network"]["allowMachLookup"] = [_MACOS_TRUST_MACH_SERVICE]
    path = directory / "srt-settings.json"
    path.write_text(json.dumps(profile))
    return path


def prefix(settings_path: Path) -> list[str]:
    """The `srt --settings <file> --` argv prefix. `--` stops srt's own option
    parsing so the agent command's flags (e.g. `--out`) pass through untouched."""
    srt = shutil.which("srt")
    if srt is None:  # caller resolved with decide(); this is a belt-and-suspenders guard
        raise SandboxUnavailable("srt not found on PATH")
    return [srt, "--settings", str(settings_path), "--"]


__all__ = [
    "DEFAULT_ALLOW_DOMAINS",
    "SandboxUnavailable",
    "available",
    "decide",
    "home_state_dirs",
    "prefix",
    "settings_file",
]
