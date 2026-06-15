"""`local_models` — staging local-inference model files for a run.

The seam under test: a commission that asks for a local model must end up with
the GGUF in a host cache and a manifest whose path is the IN-SANDBOX mount path
(so the agent resolves it inside the container), and the mount must bind that
cache at the env-root location the agent reads from. Network (HF API + download)
is mocked; the path/manifest logic is real.
"""

from __future__ import annotations

import json
from pathlib import Path

from avp.commission import Commission
from avp_cli import local_models


def _commission(model: str, *, provider: bool) -> Commission:
    data: dict = {"schema_version": "0.1", "run_id": "t", "prompt": "{input}", "model": model}
    if provider:
        data["provider"] = {"id": "local"}
    return Commission.model_validate(data)


def test_is_local_detects_provider_block_and_slug_origin() -> None:
    assert local_models.is_local(_commission("local/bartowski/M-GGUF:Q4_K_M", provider=True))
    # No provider block: the model slug's `local/` origin is enough.
    assert local_models.is_local(_commission("local/bartowski/M-GGUF:Q4_K_M", provider=False))
    # Hosted providers are not local.
    assert not local_models.is_local(_commission("anthropic/claude-haiku-4-5", provider=False))
    assert not local_models.is_local(_commission("ollama/llama3.2:3b", provider=False))


def test_spec_splits_repo_and_quant() -> None:
    assert local_models._spec("local/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M") == (
        "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "Q4_K_M",
    )


def test_spec_rejects_missing_quant() -> None:
    import pytest

    with pytest.raises(local_models.LocalModelError):
        local_models._spec("local/bartowski/Llama-3.2-1B-Instruct-GGUF")


def test_provision_caches_gguf_and_writes_sandbox_pathed_registry(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(local_models.paths, "avp_home", lambda: tmp_path)
    monkeypatch.setattr(local_models, "_resolve_gguf_filename", lambda repo, quant: "M-Q4_K_M.gguf")

    def fake_download(url: str, dest: Path, notify) -> None:
        dest.write_bytes(b"\x00" * 16)  # stand in for the GGUF

    monkeypatch.setattr(local_models, "_download", fake_download)

    cache = local_models.provision("local/bartowski/M-GGUF:Q4_K_M")

    assert cache == tmp_path / "models"
    assert (cache / "M-Q4_K_M.gguf").exists()
    reg = json.loads((cache / "registry.json").read_text())
    entry = reg["models"][0]
    # native id = slug with the `local/` origin stripped
    assert entry["id"] == "bartowski/M-GGUF:Q4_K_M"
    # local_path is the IN-SANDBOX mount path, not the host cache path
    assert entry["local_path"] == f"{local_models.SANDBOX_MODELS_DIR}/M-Q4_K_M.gguf"
    assert entry["size_bytes"] == 16


def test_provision_reuses_cached_gguf(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(local_models.paths, "avp_home", lambda: tmp_path)
    monkeypatch.setattr(local_models, "_resolve_gguf_filename", lambda repo, quant: "M-Q4_K_M.gguf")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "M-Q4_K_M.gguf").write_bytes(b"cached")

    def boom(*a, **k):
        raise AssertionError("must not re-download a cached model")

    monkeypatch.setattr(local_models, "_download", boom)
    local_models.provision("local/bartowski/M-GGUF:Q4_K_M")  # no download


def test_volume_binds_cache_at_sandbox_models_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(local_models.paths, "avp_home", lambda: tmp_path)
    monkeypatch.setattr(local_models, "_resolve_gguf_filename", lambda repo, quant: "M-Q4_K_M.gguf")
    monkeypatch.setattr(local_models, "_download", lambda url, dest, notify: dest.write_bytes(b"x"))

    vol = local_models.volume(_commission("local/bartowski/M-GGUF:Q4_K_M", provider=True))
    assert vol is not None
    assert vol.mount_path == local_models.SANDBOX_MODELS_DIR
    assert vol.host.path == str((tmp_path / "models").resolve())

    # A hosted-provider commission needs no models volume.
    assert local_models.volume(_commission("anthropic/claude-haiku-4-5", provider=False)) is None
