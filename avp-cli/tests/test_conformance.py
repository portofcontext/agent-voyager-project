"""Conformance through the eval engine, with `dispatch` faked to write a saved
Trajectory, so no sandbox starts. test_agent.py runs a case against a real agent."""

import json
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from conftest import DESCRIPTOR, event, no_sandbox
from typer.testing import CliRunner

from avp.commission import AgentSettings, Commission, McpServerHttp, McpServerStdio
from avp.descriptor import AgentDescriptor, McpServer, Tool
from avp.descriptor import Skill as DescriptorSkill
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.cli import app
from avp_cli.conformance import check, cli, mock
from avp_cli.conformance.cases import (
    CASES,
    NO_SUCH_ITEM,
    NO_SUCH_PROVIDER,
    OTHER_SKILL_NAME,
    RUN_ID,
    SERVER_ID,
    SKILL_NAME,
    Case,
    Context,
    Skip,
)
from avp_cli.conformance.rules import RULES
from avp_cli.console import Failed
from avp_cli.eval import engine
from avp_cli.eval.scoring import Run
from avp_cli.runs import environment, network
from avp_cli.runs.dispatch import Finished, Options

MODEL = check.model("anthropic/claude-haiku-4-5")
CONTEXT = Context(descriptor=DESCRIPTOR, model=MODEL)
[AGENTS_WITHOUT_ENTRY] = [c for c in CASES if c.name == "agents-without-entry"]

REQUESTED = event(1, "run_requested", {})
DESCRIBED = event(2, "agent_described", {"descriptor": DESCRIPTOR.model_dump(exclude_none=True)})
REFUSED = event(3, "error_occurred", {"error_code": "invalid_commission", "error_message": "x"})
REFUSAL = [REQUESTED, DESCRIBED, REFUSED]


class FakeDispatch:
    """Writes `lines` as each run's Trajectory, or raises `error`."""

    def __init__(self) -> None:
        self.lines: Sequence[dict | str] | None = [*REFUSAL]
        self.exit_code = 0
        self.error: Failed | None = None
        self.commissions: list[Commission] = []
        self.options: list[Options] = []
        self.serving = FakeServing()

    def __call__(
        self, agent: store.Agent, entrypoint: list[str], commission: Commission, options: Options
    ) -> Finished:
        self.commissions.append(commission)
        self.options.append(options)
        if self.error:
            raise self.error
        assert options.directory is not None
        options.directory.mkdir(parents=True)
        if self.lines is not None:
            text = "\n".join(e if isinstance(e, str) else json.dumps(e) for e in self.lines)
            (options.directory / paths.TRAJECTORY).write_text(text + "\n")
        return Finished(options.directory, self.exit_code, "")


class FakeServing:
    """Stands in for `mock.serving`, and keeps what each start was given."""

    URL = "http://10.0.0.9:4010"

    def __init__(self) -> None:
        self.started: list[tuple[list[Case], str]] = []
        self.open = False

    @contextmanager
    def __call__(self, cases: list[Case], image: str = mock.IMAGE) -> Generator[str]:
        self.started.append((cases, image))
        self.open = True
        yield self.URL
        self.open = False


@pytest.fixture(autouse=True)
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeDispatch:
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "home"))
    fake = FakeDispatch()
    no_sandbox(monkeypatch)
    monkeypatch.setattr(engine, "dispatch", fake)
    monkeypatch.setattr(mock, "serving", fake.serving)
    return fake


def case(name: str = "a-case", level: str = "MUST", **change: object) -> Case:
    fields: dict = {
        "name": name,
        "rule": "commission.5.1",
        "level": level,
        "about": "x",
        "commission": lambda context: Commission(
            avp_version="0.1", run_id=RUN_ID, model=context.model, prompt="Say hello."
        ),
        "check": lambda run: [],
        **change,
    }
    return Case(**fields)


def test_every_case_names_a_known_rule_and_a_unique_name() -> None:
    assert all(c.rule in RULES for c in CASES)
    assert len({c.name for c in CASES}) == len(CASES)


def test_agents_without_entry_names_another_agent() -> None:
    commission = AGENTS_WITHOUT_ENTRY.commission(CONTEXT)
    assert commission.agents is not None
    assert DESCRIPTOR.agent_name not in commission.agents
    assert commission.model.credential is not None


FULL = AgentDescriptor.model_validate(
    {
        "avp_version": "0.1",
        "agent_name": "full-agent",
        "agent_version": "1.2.0",
        "tools": [
            {"name": "bash", "inputSchema": {"type": "object"}},
            {"name": "search", "inputSchema": {"type": "object"}, "mcp_server_id": "issues"},
        ],
        "mcp_servers": [{"id": "issues"}],
        "skills": [{"name": "triage", "description": "x"}],
    }
)
FULL_CONTEXT = Context(descriptor=FULL, model=MODEL)


def by_name(name: str) -> Case:
    return next(c for c in CASES if c.name == name)


def entry(name: str) -> AgentSettings:
    agents = by_name(name).commission(FULL_CONTEXT).agents
    assert agents is not None
    return agents[FULL.agent_name]


def test_version_differs_names_another_version() -> None:
    assert entry("version-differs").version not in (None, FULL.agent_version)


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("unknown-enabled-tool", "enabled_tools"),
        ("unknown-enabled-subagent", "enabled_subagents"),
        ("unknown-enabled-skill", "enabled_skills"),
        ("unknown-enabled-mcp-server", "enabled_mcp_servers"),
    ],
)
def test_unknown_item_cases_set_only_their_list(name: str, field: str) -> None:
    assert entry(name).model_dump(exclude_none=True) == {field: [NO_SUCH_ITEM]}


def test_enabled_tools_names_a_tool_only_an_mcp_server_has() -> None:
    assert entry("enabled-tools-names-mcp-tool").enabled_tools == ["search"]


def test_enabled_tools_case_skips_a_name_a_built_in_tool_also_has() -> None:
    tools = [
        {"name": "search", "inputSchema": {"type": "object"}},
        {"name": "search", "inputSchema": {"type": "object"}, "mcp_server_id": "issues"},
    ]
    descriptor = FULL.model_copy(update={"tools": [Tool.model_validate(t) for t in tools]})
    with pytest.raises(Skip):
        by_name("enabled-tools-names-mcp-tool").commission(Context(descriptor, MODEL))


def test_skill_name_differs_from_its_frontmatter() -> None:
    [skill] = by_name("skill-name-differs").commission(FULL_CONTEXT).skills or []
    assert skill.name == SKILL_NAME
    assert f"name: {OTHER_SKILL_NAME}\n" in skill.files["SKILL.md"]


def test_unknown_provider_has_no_base_url() -> None:
    model = by_name("unknown-provider").commission(FULL_CONTEXT).model
    assert (model.provider, model.base_url) == (NO_SUCH_PROVIDER, None)
    assert model.credential == MODEL.credential


def test_added_items_take_a_built_in_name() -> None:
    [server] = by_name("added-server-id-taken").commission(FULL_CONTEXT).mcp_servers or []
    assert server.id == "issues"
    [skill] = by_name("added-skill-name-taken").commission(FULL_CONTEXT).skills or []
    assert skill.name == "triage"
    assert "name: triage\n" in skill.files["SKILL.md"]


@pytest.mark.parametrize(
    "name", ["enabled-tools-names-mcp-tool", "added-server-id-taken", "added-skill-name-taken"]
)
def test_cases_skip_an_agent_without_the_item(name: str) -> None:
    with pytest.raises(Skip):
        by_name(name).commission(CONTEXT)


@pytest.mark.parametrize(
    ("name", "update"),
    [
        ("added-server-id-taken", {"mcp_servers": [McpServer(id="Not Valid")]}),
        (
            "added-skill-name-taken",
            {"skills": [DescriptorSkill(name="Not Valid", description="x")]},
        ),
    ],
)
def test_taken_name_cases_skip_a_name_no_commission_can_use(name: str, update: dict) -> None:
    context = Context(descriptor=FULL.model_copy(update=update), model=MODEL)
    with pytest.raises(Skip, match="Not Valid"):
        by_name(name).commission(context)


def test_connect_failure_cases_add_a_server_that_cannot_connect() -> None:
    [stdio] = by_name("stdio-server-wont-start").commission(FULL_CONTEXT).mcp_servers or []
    [http] = by_name("http-server-wont-connect").commission(FULL_CONTEXT).mcp_servers or []
    assert isinstance(stdio, McpServerStdio) and isinstance(http, McpServerHttp)
    assert http.url.startswith("http://") and ".invalid/" in http.url


def test_a_commission_without_a_real_host_can_still_be_dispatched() -> None:
    commission = by_name("http-server-wont-connect").commission(FULL_CONTEXT)
    assert "mcp.conformance.invalid" in network.allowed_hosts(commission, [])
    environment.check(commission, {check.KEY: check.STAND_IN})
    no_host = by_name("unknown-provider").commission(FULL_CONTEXT)
    assert network.allowed_hosts(no_host, []) == {}
    environment.check(no_host, {check.KEY: check.STAND_IN})


def connect_failed(message: str = f"can't connect to {SERVER_ID}") -> dict:
    return event(
        3, "error_occurred", {"error_code": "mcp_connect_failed", "error_message": message}
    )


def test_every_case_runs_through_the_engine(
    fake: FakeDispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each case's Commission survives the eval item's JSON and reaches the agent."""
    monkeypatch.setattr(
        command, "describe_in_sandbox", lambda agent, entrypoint, volumes=None: FULL
    )
    outcomes = check.check("pd", CASES, MODEL)
    by_rule = {o.case: (o.rule, o.status) for o in outcomes}
    assert len(fake.commissions) == len(CASES)
    assert all(status == "pass" for rule, status in by_rule.values() if rule == "commission.5.1"), (
        by_rule
    )
    assert all(status == "fail" for rule, status in by_rule.values() if rule == "commission.5.4"), (
        by_rule
    )
    # A skill whose `name` differs from its frontmatter is what the case sends.
    sent = {c.run_id.split("-", 1)[1]: c for c in fake.commissions}
    [skill] = sent["conformance-pd-skill-name-differs"].skills or []
    assert f"name: {OTHER_SKILL_NAME}\n" in skill.files["SKILL.md"]


@pytest.mark.parametrize(
    ("error", "status", "reason"),
    [
        (connect_failed(), "pass", None),
        (
            connect_failed("can't connect"),
            "fail",
            f"error_occurred's message doesn't name {SERVER_ID}",
        ),
        (REFUSED, "fail", "error_occurred has the code invalid_commission, not mcp_connect_failed"),
    ],
)
def test_a_connect_failure_must_have_its_code_and_name_the_server(
    fake: FakeDispatch, error: dict, status: str, reason: str | None
) -> None:
    fake.lines = [REQUESTED, DESCRIBED, error]
    [outcome] = check.check("pd", [by_name("stdio-server-wont-start")], MODEL)
    assert outcome.status == status
    assert outcome.reasons == ([reason] if reason else [])


def test_a_connect_failure_fails_when_the_run_started_anyway(fake: FakeDispatch) -> None:
    model = {"provider": "anthropic", "id": "claude-haiku-4-5"}
    fake.lines = [REQUESTED, DESCRIBED, event(3, "agent_started", {"prompt": "x", "model": model})]
    [outcome] = check.check("pd", [by_name("http-server-wont-connect")], MODEL)
    assert outcome.status == "fail"
    assert outcome.reasons[0].startswith("the events are run_requested")


def test_a_should_case_that_fails_exits_0(
    fake: FakeDispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.lines = [REQUESTED, DESCRIBED, connect_failed("issues")]
    monkeypatch.setattr(
        command, "describe_in_sandbox", lambda agent, entrypoint, volumes=None: FULL
    )
    result = CliRunner().invoke(
        app, ["conformance", "check", "--agent", "pd", "--case", "added-server-id-taken", "--json"]
    )
    assert result.exit_code == 0, result.output
    [outcome] = json.loads(result.output[result.output.index("[") :])
    assert (outcome["level"], outcome["status"]) == ("SHOULD", "fail")


def test_a_refusal_passes() -> None:
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert (outcome.status, outcome.reasons) == ("pass", [])
    assert outcome.run_directory is not None
    assert (outcome.run_directory / paths.TRAJECTORY).is_file()
    assert outcome.run_directory.is_relative_to(paths.conformance())


@pytest.mark.parametrize(
    ("lines", "problem"),
    [
        (
            [REQUESTED, DESCRIBED, event(3, "agent_started", {"prompt": "x"})],
            "the events are run_requested",
        ),
        (
            [
                REQUESTED,
                DESCRIBED,
                event(3, "error_occurred", {"error_code": "agent_crash", "error_message": "x"}),
            ],
            "error_occurred has the code agent_crash",
        ),
        ([REQUESTED, REFUSED], "the events are run_requested, error_occurred"),
        ([*REFUSAL, "not json"], "not a valid event: not json"),
        ([*REFUSAL, event(4, "from_the_future", {})], "not a valid event: {"),
        (None, "the agent wrote no Trajectory"),
    ],
)
def test_a_refusal_fails(fake: FakeDispatch, lines: list[dict | str] | None, problem: str) -> None:
    fake.lines = lines
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert outcome.status == "fail"
    assert any(r.startswith(problem) for r in outcome.reasons), outcome.reasons


def test_a_failed_exit_fails(fake: FakeDispatch) -> None:
    fake.exit_code = 3
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert (outcome.status, outcome.reasons) == ("fail", ["the agent exited with 3"])


def test_outcomes_keep_the_cases_order() -> None:
    def skip(context: Context) -> Commission:
        raise Skip("the agent has no subagents")

    def wrong(run: Run) -> list[str]:
        return ["wrong"]

    chosen = [case("one", check=wrong), case("two", commission=skip), case("three")]
    outcomes = check.check("pd", chosen, MODEL)
    assert [(o.case, o.status, o.reasons) for o in outcomes] == [
        ("one", "fail", ["wrong"]),
        ("two", "skip", ["the agent has no subagents"]),
        ("three", "pass", []),
    ]
    assert outcomes[1].run_directory is None


def test_only_skipped_cases_start_no_run(fake: FakeDispatch) -> None:
    def skip(context: Context) -> Commission:
        raise Skip("no")

    [outcome] = check.check("pd", [case(commission=skip)], MODEL)
    assert outcome.status == "skip"
    assert fake.commissions == []


def test_a_run_that_did_not_start_fails_with_why(fake: FakeDispatch) -> None:
    fake.error = Failed("OpenSandbox couldn't start a sandbox")
    [outcome] = check.check("pd", [case()], MODEL)
    assert outcome.status == "fail"
    assert outcome.reasons == ["the run didn't start: OpenSandbox couldn't start a sandbox"]
    assert outcome.run_directory is None


def test_a_check_that_raises_fails_with_why() -> None:
    def broken(run: Run) -> list[str]:
        raise KeyError("bug")

    [outcome] = check.check("pd", [case(check=broken)], MODEL)
    assert outcome.status == "fail"
    assert outcome.reasons == ["scorer failed: KeyError: 'bug'"]


def test_runs_get_the_stand_in_and_the_url_that_never_resolves(fake: FakeDispatch) -> None:
    check.check("pd", [case()], MODEL)
    [commission] = fake.commissions
    [options] = fake.options
    assert commission.model.base_url == check.BASE_URL
    assert commission.run_id.endswith("-conformance-pd-a-case")
    assert commission.supervisor is not None
    assert options.env == {check.KEY: check.STAND_IN}


SCRIPTED = ({"content": "x"},)
STARTED = [
    REQUESTED,
    DESCRIBED,
    event(
        3,
        "agent_started",
        {"prompt": "x", "model": {"provider": "anthropic", "id": "claude-haiku-4-5"}},
    ),
    event(
        4,
        "assistant_message",
        {
            "content": [{"type": "text", "text": "x"}],
            "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
            "duration_ms": 10,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0,
                "cost_source": "unknown",
            },
        },
    ),
    event(5, "agent_stopped", {"reason": "converged"}),
]


def test_a_case_without_responses_starts_no_mock(
    fake: FakeDispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    check.check("pd", [case()], MODEL)
    assert fake.serving.started == []


def test_only_a_case_with_responses_gets_the_mock_and_its_prompt(fake: FakeDispatch) -> None:
    def commission(context: Context) -> Commission:
        return Commission(
            avp_version="0.1", run_id=RUN_ID, model=context.model, prompt=context.prompt
        )

    scripted = case("scripted", commission=commission, responses=SCRIPTED)
    check.check("pd", [case("plain", commission=commission), scripted], MODEL, mock_image="mine")
    assert fake.serving.started == [([scripted], "mine")]
    sent = {c.run_id.split("-", 1)[1]: c for c in fake.commissions}
    assert sent["conformance-pd-plain"].model.base_url == check.BASE_URL
    assert sent["conformance-pd-plain"].prompt == "Say hello."
    assert sent["conformance-pd-scripted"].model.base_url == FakeServing.URL
    assert sent["conformance-pd-scripted"].prompt == scripted.prompt
    assert network.allowed_hosts(sent["conformance-pd-scripted"], []) == {
        "10.0.0.9": [network.MODEL]
    }


def test_the_mock_stays_up_until_the_runs_finish(
    fake: FakeDispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_during_run = []
    dispatch = engine.dispatch

    def watching(
        agent: store.Agent, entrypoint: list[str], commission: Commission, options: Options
    ) -> Finished:
        open_during_run.append(fake.serving.open)
        return dispatch(agent, entrypoint, commission, options)

    monkeypatch.setattr(engine, "dispatch", watching)
    check.check("pd", [case(responses=SCRIPTED)], MODEL)
    assert open_during_run == [True]
    assert fake.serving.open is False


@pytest.mark.parametrize(
    ("slug", "url"),
    [
        ("anthropic/claude-haiku-4-5", FakeServing.URL),
        ("google/gemini-3.1-flash-lite", FakeServing.URL),
        ("openai/gpt-5-mini", f"{FakeServing.URL}/v1"),
    ],
)
def test_each_provider_gets_the_path_its_sdk_needs(fake: FakeDispatch, slug: str, url: str) -> None:
    check.check("pd", [case(responses=SCRIPTED)], check.model(slug))
    assert fake.commissions[0].model.base_url == url


def test_a_provider_the_mock_cannot_serve_fails_before_it_starts(fake: FakeDispatch) -> None:
    with pytest.raises(Failed, match="can't serve 'mistral'"):
        check.check("pd", [case(responses=SCRIPTED)], check.model("mistral/large"))
    assert fake.serving.started == []


def test_a_provider_the_mock_cannot_serve_only_matters_to_a_case_with_responses() -> None:
    [outcome] = check.check("pd", [case()], check.model("mistral/large"))
    assert outcome.status == "pass"


def test_fixtures_match_each_response_on_the_prompt_and_its_turn() -> None:
    two = case("two", responses=({"content": "a"}, {"content": "b"}))
    one = case("one", responses=SCRIPTED)
    assert mock.fixtures([two, one]) == {
        "fixtures": [
            {"match": {"userMessage": two.prompt, "turnIndex": 0}, "response": {"content": "a"}},
            {"match": {"userMessage": two.prompt, "turnIndex": 1}, "response": {"content": "b"}},
            {"match": {"userMessage": one.prompt, "turnIndex": 0}, "response": {"content": "x"}},
        ]
    }


def test_no_prompt_matches_inside_another_case() -> None:
    assert case("a-case").prompt not in case("a-case-2").prompt


@pytest.mark.parametrize(
    ("patterns", "supported"),
    [
        (None, True),
        ([{"provider": "anthropic", "id": "*"}], True),
        ([{"provider": "*", "id": "claude-*"}], True),
        ([{"provider": "openai", "id": "*"}], False),
        ([{"provider": "anthropic", "id": "gpt-*"}], False),
        ([], False),
    ],
)
def test_a_model_the_agent_does_not_support_stops_the_check(
    fake: FakeDispatch,
    monkeypatch: pytest.MonkeyPatch,
    patterns: list[dict] | None,
    supported: bool,
) -> None:
    descriptor = AgentDescriptor.model_validate(
        {
            "avp_version": "0.1",
            "agent_name": "a",
            "agent_version": "1",
            **({} if patterns is None else {"supported_models": patterns}),
        }
    )
    monkeypatch.setattr(
        command, "describe_in_sandbox", lambda agent, entrypoint, volumes=None: descriptor
    )
    if supported:
        check.check("pd", [case()], MODEL)
        assert len(fake.commissions) == 1
    else:
        with pytest.raises(Failed, match="doesn't support anthropic/claude-haiku-4-5"):
            check.check("pd", [case()], MODEL)
        assert fake.commissions == []


def test_events_in_order_passes_a_run_with_a_model_response(fake: FakeDispatch) -> None:
    fake.lines = STARTED
    [outcome] = check.check("pd", [by_name("events-in-order")], MODEL)
    assert (outcome.status, outcome.reasons) == ("pass", [])


@pytest.mark.parametrize(
    ("lines", "problem"),
    [
        ([STARTED[0], STARTED[2], *STARTED[1:2], *STARTED[3:]], "the events start"),
        (STARTED[:-1], "agent_stopped isn't last"),
        ([*STARTED, STARTED[3]], "agent_stopped isn't last"),
        ([*STARTED[:3], STARTED[4]], "no assistant_message"),
    ],
)
def test_events_in_order_fails(fake: FakeDispatch, lines: list[dict], problem: str) -> None:
    fake.lines = lines
    [outcome] = check.check("pd", [by_name("events-in-order")], MODEL)
    assert outcome.status == "fail"
    assert any(problem in reason for reason in outcome.reasons), outcome.reasons


def test_mock_image_reaches_the_check(fake: FakeDispatch, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "CASES", [case(responses=SCRIPTED, check=lambda run: [])])
    args = ["conformance", "check", "--agent", "pd", "--json", "--mock-image", "mine"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    [(_, image)] = fake.serving.started
    assert image == "mine"


def test_model_must_be_provider_slash_id() -> None:
    assert check.model("openai/gpt-5-mini").model_dump(exclude_none=True) == {
        "provider": "openai",
        "id": "gpt-5-mini",
        "base_url": check.BASE_URL,
        "credential": {"env": check.KEY},
    }
    with pytest.raises(Failed, match="isn't provider/model"):
        check.model("gpt-5-mini")


@pytest.mark.parametrize(("level", "exit_code"), [("MUST", 1), ("SHOULD", 0)])
def test_only_a_must_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, level: str, exit_code: int
) -> None:
    def wrong(run: Run) -> list[str]:
        return ["wrong"]

    monkeypatch.setattr(cli, "CASES", [case(level=level, check=wrong)])
    result = CliRunner().invoke(app, ["conformance", "check", "--agent", "pd", "--json"])
    assert result.exit_code == exit_code, result.output
    [outcome] = json.loads(result.output[result.output.index("[") :])
    assert (outcome["status"], outcome["reasons"]) == ("fail", ["wrong"])


def test_volumes_and_entrypoint_reach_describe_and_each_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeDispatch
) -> None:
    described = no_sandbox(monkeypatch)
    monkeypatch.setattr(engine, "dispatch", fake)
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "check",
            "--agent",
            "pd",
            "--case",
            "agents-without-entry",
            "-v",
            f"{tmp_path}:/src:ro",
            "--entrypoint",
            "cargo run -q --",
        ],
    )
    assert result.exit_code == 0, result.output
    [options] = fake.options
    assert options.entrypoint == ["cargo", "run", "-q", "--"]
    assert described.entrypoint == ["cargo", "run", "-q", "--"]
    assert described == ["pd", "pd"]
    assert [v.mount_path for v in options.volumes] == ["/src"]
    assert described.volumes == options.volumes


@pytest.mark.parametrize("entrypoint", ["", "'unclosed"])
def test_a_bad_entrypoint_fails(entrypoint: str) -> None:
    result = CliRunner().invoke(
        app, ["conformance", "check", "--agent", "pd", "--entrypoint", entrypoint]
    )
    assert result.exit_code == 1
    assert "--entrypoint" in str(result.exception)


def test_list_shows_each_rule_and_its_cases() -> None:
    result = CliRunner().invoke(app, ["conformance", "list", "--rule", "commission.5.1"])
    assert result.exit_code == 0, result.output
    assert "agents-without-entry" in result.output
    assert "trajectory.4.5" not in result.output


def test_unknown_rule_fails() -> None:
    result = CliRunner().invoke(app, ["conformance", "check", "--agent", "pd", "--rule", "x.1"])
    assert result.exit_code == 1
    assert "no rule x.1" in str(result.exception)
