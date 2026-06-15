"""Stage a local-inference model for a run, host-side.

A commission can ask for in-process local inference by naming the `local`
provider with a `local/<hf-repo>:<quant>` model slug (e.g.
`local/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M`). The agent runs that model
itself rather than calling a hosted API, but it does not fetch the weights: it
expects them already staged under the run's env root and listed in a manifest,
and fails the run if they are absent. So the supervisor stages them.

`provision()` downloads the GGUF from Hugging Face once into a host cache
(`~/.avp/models`, reused across runs) and writes the manifest next to it.
`volume()` binds that cache into the sandbox at the env-root location the agent
reads from. Doing the fetch host-side keeps the run deterministic and needs no
in-sandbox network. This is the only model format avp stages today; the slug's
`local` origin is the opt-in.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from opensandbox.models.sandboxes import Host, Volume

from avp.commission import Commission
from avp_cli import paths

# Where the agent reads its staged model manifest + files in-sandbox: an
# env-root-relative path (AVP_ENV_ROOT is mounted at /avp, models under data/).
SANDBOX_MODELS_DIR = "/avp/data/models"

# Context window recorded in the manifest; the agent uses it for the model's
# context limit. 8192 is a safe default for the small instruct models people run
# locally; revisit if we expose a per-commission override.
_DEFAULT_CONTEXT_SIZE = 8192

_HF_API = "https://huggingface.co/api/models"
_HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{filename}"
_LOCK_STALE_S = 3600.0  # a download lock older than this is treated as abandoned


class LocalModelError(Exception):
    """Provisioning a `local` model failed (bad slug, unknown file, download)."""


def is_local(commission: Commission) -> bool:
    """True iff this commission asks for an in-process local model.

    Detected via the provider block (`provider.id == "local"`) or, when no block
    is set, the model slug's origin segment (`local/...`) — matching the agent's
    own origin-based provider routing.
    """
    if commission.provider is not None:
        return commission.provider.id == "local"
    return (commission.model or "").split("/", 1)[0] == "local"


def models_cache_dir() -> Path:
    return paths.avp_home() / "models"


def _spec(commission_model: str) -> tuple[str, str]:
    """Split `local/<repo>:<quant>` into (`<repo>`, `<quant>`).

    The model slug's origin segment is the provider (`local`); the remainder is
    the native spec `<hf-repo>:<quant>`, where the repo itself contains `/`.
    """
    native = commission_model.split("/", 1)[1] if "/" in commission_model else commission_model
    repo, sep, quant = native.rpartition(":")
    if not sep or not repo:
        raise LocalModelError(
            f"model {commission_model!r} is not a valid local spec "
            "(expected local/<hf-repo>:<quant>, e.g. "
            "local/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M)"
        )
    return repo, quant


def _resolve_gguf_filename(repo_id: str, quant: str) -> str:
    """Find the single GGUF file in `repo_id` for `quant` via the HF API.

    Matches the file whose name ends `-<quant>.gguf` (case-insensitive). Sharded
    models (`-00001-of-000NN`) are not handled yet and raise a clear error.
    """
    url = f"{_HF_API}/{repo_id}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
    except Exception as exc:  # network, 404, JSON
        raise LocalModelError(f"could not query Hugging Face for {repo_id!r}: {exc}") from exc
    files = [s.get("rfilename", "") for s in data.get("siblings", [])]
    suffix = f"-{quant}.gguf".lower()
    matches = [f for f in files if f.lower().endswith(suffix)]
    if not matches:
        raise LocalModelError(
            f"no GGUF for quant {quant!r} in {repo_id!r} "
            f"(available: {', '.join(f for f in files if f.endswith('.gguf')) or 'none'})"
        )
    if any("-of-" in f for f in matches):
        raise LocalModelError(
            f"{repo_id!r} {quant!r} is a sharded GGUF; multi-shard local models are not "
            "provisioned yet. Pick a single-file quantization."
        )
    return matches[0]


def _download(url: str, dest: Path, notify: Callable[[str], None] | None) -> None:
    """Stream `url` to `dest` atomically (temp + rename), with a serialized lock.

    Eval matrices run cells concurrently; a per-file lock means the first worker
    downloads while the rest wait, then all hit the cache.
    """
    lock = dest.with_suffix(dest.suffix + ".lock")
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if dest.exists():
                return  # another worker finished it while we waited
            if lock.stat().st_mtime < time.time() - _LOCK_STALE_S:
                lock.unlink(missing_ok=True)  # abandoned; reclaim
                continue
            time.sleep(2.0)
    try:
        if dest.exists():
            return
        if notify:
            notify(f"downloading {dest.name} from Hugging Face (one time; cached in {dest.parent})")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        lock.unlink(missing_ok=True)


def provision(commission_model: str, *, notify: Callable[[str], None] | None = None) -> Path:
    """Cache the model on the host and write the manifest that lists it.

    Idempotent: a cached GGUF is reused. Returns the host models dir to mount at
    `SANDBOX_MODELS_DIR`. The manifest names the file by its IN-SANDBOX path (the
    host file is mounted there), so it resolves inside the container.
    """
    repo_id, quant = _spec(commission_model)
    cache = models_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    filename = _resolve_gguf_filename(repo_id, quant)
    dest = cache / filename
    if not dest.exists():
        _download(_HF_RESOLVE.format(repo=repo_id, filename=filename), dest, notify)
    _write_registry(cache, commission_model, repo_id, quant, filename, dest.stat().st_size)
    return cache


def _write_registry(
    cache: Path, model_id_origin: str, repo_id: str, quant: str, filename: str, size: int
) -> None:
    """Write the manifest (`registry.json`) the agent's local provider reads: one
    entry naming the staged file by its in-sandbox path and how it was fetched."""
    native = model_id_origin.split("/", 1)[1] if "/" in model_id_origin else model_id_origin
    entry = {
        "id": native,  # the agent's native model id (slug with the `local/` origin stripped)
        "repo_id": repo_id,
        "filename": filename,
        "quantization": quant,
        "local_path": f"{SANDBOX_MODELS_DIR}/{filename}",
        "source_url": _HF_RESOLVE.format(repo=repo_id, filename=filename),
        "settings": {"context_size": _DEFAULT_CONTEXT_SIZE, "native_tool_calling": False},
        "size_bytes": size,
    }
    (cache / "registry.json").write_text(json.dumps({"models": [entry]}, indent=2))


def volume(commission: Commission, *, notify: Callable[[str], None] | None = None) -> Volume | None:
    """The models volume to mount for a local-inference commission, else None.

    Provisions the model host-side (download if needed) and returns a Volume
    binding the host cache at `SANDBOX_MODELS_DIR` so the agent finds it.
    """
    if not is_local(commission):
        return None
    host_dir = provision(commission.model, notify=notify)
    return Volume(
        name="models",
        host=Host(path=str(host_dir.resolve())),
        mount_path=SANDBOX_MODELS_DIR,
    )
