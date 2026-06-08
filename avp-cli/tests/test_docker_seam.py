"""The real-sandbox seam (gated: `-m docker`, needs a Docker daemon).

Everything the unit tests simulate, for real: the managed server comes up, a
sandbox boots from a stock image, the agent run contract executes inside it,
the trajectory crosses the bind mount while the run is live (the tail-loop
latency assumption), the derived-image cache works, and default-deny egress
actually blocks. Run via `make test-docker`.
"""

from __future__ import annotations

import subprocess

import pytest

from avp_cli import environment as env_mod
from avp_cli import images, osb
from avp_cli.agent import SandboxContext, SandboxedAgent, run_agent

# The Docker probe lives in the `server` fixture (every test here uses it), not
# in an import-time skipif: collection must stay instant for `-m "not docker"`.
pytestmark = pytest.mark.docker

_TEST_PORT = 18799  # not the CLI's default: a dev's real server may own that one
_IMAGE = "alpine:3.20"  # tiny; has /bin/sh, tail, busybox wget

# A dependency-free "agent" honoring the run contract. It parses --out from its
# argv, then emits NDJSON in two beats so the host tail loop must observe the
# file *while the run is still live* — the bind-mount latency assumption. The
# events are vendor-namespaced (`x.test`): a well-formed CloudEvent envelope +
# span triple parses as UnknownEvent and passes through (spec §4).
_AGENT_SH = """\
#!/bin/sh
while [ $# -gt 0 ]; do
  if [ "$1" = "--out" ]; then out=$2; fi
  shift
done
emit() {
  printf '{"specversion":"1.0","id":"e%s","source":"urn:seam-test","type":"x.test",' "$1"
  printf '"subject":"seam","time":"2026-01-01T00:00:00Z","data":{'
  printf '"trace_id":"0af7651916cd43dd8448eb211c80319c","span_id":"b7ad6b716920333%s",' "$1"
  printf '"parent_span_id":"0000000000000000","beat":%s}}\\n' "$1"
}
emit 1 > "$out"
sleep 1
emit 2 >> "$out"
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """An isolated managed server: own AVP_HOME, own port, stopped afterwards."""
    import os

    diagnosis = osb.docker_available()
    if diagnosis is not None:
        pytest.skip(diagnosis)
    home = tmp_path_factory.mktemp("avp-home")
    old_home, old_port = os.environ.get("AVP_HOME"), osb.DEFAULT_PORT
    os.environ["AVP_HOME"] = str(home)
    osb.DEFAULT_PORT = _TEST_PORT
    try:
        yield osb.ensure_server()
    finally:
        osb.stop_server()
        osb.DEFAULT_PORT = old_port
        if old_home is None:
            os.environ.pop("AVP_HOME", None)
        else:
            os.environ["AVP_HOME"] = old_home


def _ctx(server, workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    return SandboxContext(connection=server, workspace=workspace)


def test_trajectory_streams_through_the_bind_mount(server, tmp_path) -> None:
    from avp_cli import paths

    ws = paths.avp_home() / "runs" / "seam" / "workspace"
    ctx = _ctx(server, ws)
    (ws / "agent.sh").write_text(_AGENT_SH)

    from avp.commission import Commission

    agent = SandboxedAgent(name="fake", image=_IMAGE, command=("sh", "/avp/workspace/agent.sh"))
    commission = Commission(
        schema_version="0.1",
        run_id="seam",
        model="anthropic/claude-haiku-4-5-20251001",
        prompt="hi",
    )
    out = paths.avp_home() / "runs" / "seam" / "trajectory.ndjson"

    def beat(e) -> int:
        return e.data.beat if hasattr(e.data, "beat") else e.data["beat"]

    live_beats: list[int] = []
    events, err = run_agent(
        agent,
        ctx,
        commission,
        out_path=out,
        timeout_s=120.0,
        on_event=lambda e: live_beats.append(beat(e)),
    )

    assert err is None, err
    assert [beat(e) for e in events] == [1, 2]  # authoritative re-parse of the file
    # the tail saw the first beat while the agent was still sleeping inside the
    # sandbox: writes propagate host-ward through the bind mount during the run
    assert live_beats == [1, 2]
    assert out.is_file()


def test_nonzero_exit_reports_stderr_tail(server) -> None:
    from avp.commission import Commission
    from avp_cli import paths

    ws = paths.avp_home() / "runs" / "fail" / "workspace"
    ctx = _ctx(server, ws)
    (ws / "agent.sh").write_text("#!/bin/sh\necho boom-diagnostic >&2\nexit 3\n")

    agent = SandboxedAgent(name="fake", image=_IMAGE, command=("sh", "/avp/workspace/agent.sh"))
    events, err = run_agent(
        agent,
        ctx,
        Commission(
            schema_version="0.1",
            run_id="fail",
            model="anthropic/claude-haiku-4-5-20251001",
            prompt="hi",
        ),
        out_path=paths.avp_home() / "runs" / "fail" / "t.ndjson",
        timeout_s=120.0,
    )
    assert events is None
    assert "exit 3" in err and "boom-diagnostic" in err


def test_default_deny_egress_blocks_unlisted_domains(server) -> None:
    """Egress enforcement is host-dependent: OpenSandbox's sidecar disables
    itself (with a warning, not an error) when it can't get its netfilter
    hooks on the host kernel — observed on GitHub Actions runners, while
    Docker Desktop's VM enforces fine. So a reachable denied domain is a SKIP
    with evidence by default, and a hard failure where we know the host
    enforces: `make test-docker` sets AVP_REQUIRE_EGRESS_ENFORCEMENT=1."""
    import os
    from datetime import timedelta

    from opensandbox import SandboxSync
    from opensandbox.models.execd import RunCommandOpts

    box = SandboxSync.create(
        _IMAGE,
        connection_config=server.config(),
        network_policy=osb.network_policy(["dl-cdn.alpinelinux.org"]),
        timeout=timedelta(minutes=5),
    )
    try:
        denied = box.commands.run(
            "wget -T 8 -q -O /dev/null http://example.com && echo REACHED || echo BLOCKED",
            opts=RunCommandOpts(timeout=timedelta(seconds=30)),
        )
        logs = "".join(log.text for log in denied.logs.stdout or [])
        if "BLOCKED" not in logs and not os.environ.get("AVP_REQUIRE_EGRESS_ENFORCEMENT"):
            try:
                policy = box.get_egress_policy()
            except Exception as exc:  # sidecar not even reachable
                policy = f"(egress policy API unreachable: {exc})"
            pytest.skip(
                "egress sidecar is not enforcing on this host (upstream degrades "
                f"silently without its netfilter hooks). got {logs!r}, policy: {policy}"
            )
        assert "BLOCKED" in logs  # example.com is not on the allow-list
    finally:
        box.kill()


def test_ensure_image_builds_once_then_caches(server) -> None:
    env = env_mod.Environment.parse({"image": _IMAGE})
    recipe = images.ContainerRecipe(install=("echo marker > /marker",), command=("sh",))
    tag = images.ensure_image(env, recipe)
    assert tag.startswith("avp-env:")
    # the layer ran: the marker is in the image
    seen = subprocess.run(
        ["docker", "run", "--rm", tag, "cat", "/marker"], capture_output=True, text=True
    )
    assert seen.stdout.strip() == "marker"
    # second call is a cache probe, no rebuild (same content-addressed tag)
    assert images.ensure_image(env, recipe) == tag
