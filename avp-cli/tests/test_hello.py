"""`avp hello-world`: its eval, and a run on one agent against a real
container engine and the mock model."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp_cli import engine, hello, paths
from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.eval import share as sharing
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.results import EvalResults
from avp_cli.eval.schemas import Eval


def engine_answers() -> bool:
    try:
        engine.client()
    except Failed:
        return False
    return True


def test_the_mock_has_a_reply_for_every_prompt_the_eval_sends() -> None:
    file = hello.eval_file(list(hello.AGENTS), {"credential": {"proxy": hello.PROVIDER}})
    config = EvalConfig.from_eval(Eval.model_validate(file), Path.cwd())
    replies = {
        hello.PROMPT.format(country=country): capital for country, capital in hello.CAPITALS.items()
    }
    cases = list(config)
    assert len(cases) == len(hello.AGENTS) * len(hello.CAPITALS)
    for case in cases:
        assert replies[case.built.prompt] == case.item.model_dump()["answer"]


@pytest.mark.skipif(not engine_answers(), reason="no container engine answers")
def test_hello_world_installs_its_agent_and_every_run_passes(
    avp_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hello, "AGENTS", ("pydantic-ai",))
    uploads: list[Path] = []

    def share(directory: Path, results: EvalResults, site: str) -> sharing.Shared:
        uploads.append(directory)
        sharing.payload(directory, results)
        return sharing.Shared(
            id="abcdefghij",
            url="https://site.test/eval/abcdefghij",
            delete_token="token",
            expires_at=datetime(2026, 2, 1, tzinfo=UTC),
            site=site,
        )

    monkeypatch.setattr(sharing, "share", share)
    runner = CliRunner()
    result = runner.invoke(app, ["hello-world"])
    try:
        assert result.exit_code == 0, result.output
        [directory] = paths.evals().iterdir()
        saved = json.loads((directory / paths.RESULTS).read_text())
        assert len(saved["runs"]) == len(hello.CAPITALS)
        assert all(run["score"]["passed"] for run in saved["runs"]), saved
        # The saved eval is the one for a real model, which the output points to.
        kept = json.loads((directory / paths.EVAL).read_text())
        assert kept["commission"]["model"] == {
            "provider": hello.PROVIDER,
            "id": hello.MODEL,
            "credential": {"proxy": hello.PROVIDER},
        }
        assert uploads == [directory]
        assert result.output.rstrip().endswith("https://site.test/eval/abcdefghij")
        quiet = runner.invoke(app, ["hello-world", "--no-share"])
        assert quiet.exit_code == 0, quiet.output
        assert len(uploads) == 1
        assert "site.test" not in quiet.output
    finally:
        runner.invoke(app, ["agent", "uninstall", "pydantic-ai"])
