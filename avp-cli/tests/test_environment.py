"""Declarative environments: parse the block, seed files, materialize a prefix.

Environments are a CLI-side concept (the spec never learns the word): they
provision a user-space toolchain prefix + a seeded workspace, then the agent
runs against it under srt. These tests cover parse / file-seeding / the
materialize dispatch with the provisioner stubbed; a real uv-backed smoke lives
in `test_environment_smoke.py`.
"""

from __future__ import annotations

import pytest

from avp_cli import environment as env

# ── parse ─────────────────────────────────────────────────────────────────────


def test_parse_minimal_is_all_empty() -> None:
    e = env.Environment.parse({})
    assert e.runtimes == [] and e.packages == {} and e.files == {}
    assert e.setup == [] and e.expose.write == [] and e.expose.net == []


def test_parse_full_block() -> None:
    e = env.Environment.parse(
        {
            "runtimes": ["python@3.12"],
            "packages": {"pip": ["six"]},
            "files": {"a.txt": "hi"},
            "setup": ["echo hi"],
            "expose": {"write": ["./out"], "net": ["api.x.test"]},
        }
    )
    assert e.runtimes == ["python@3.12"]
    assert e.packages == {"pip": ["six"]}
    assert e.files == {"a.txt": "hi"}
    assert e.setup == ["echo hi"]
    assert e.expose.write == ["./out"] and e.expose.net == ["api.x.test"]


def test_parse_rejects_non_object() -> None:
    with pytest.raises(env.EnvError):
        env.Environment.parse([])  # type: ignore[arg-type]


def test_parse_rejects_unknown_key() -> None:
    with pytest.raises(env.EnvError, match="unknown"):
        env.Environment.parse({"nope": 1})


# ── tool spec ─────────────────────────────────────────────────────────────────


def test_parse_runtime_with_and_without_version() -> None:
    assert env.parse_runtime("python@3.12") == ("python", "3.12")
    assert env.parse_runtime("python") == ("python", None)


def test_parse_runtime_accepts_known_unimplemented_langs() -> None:
    # The schema is language-agnostic: node/go validate even before we ship their
    # provisioner. materialize() is where "not implemented yet" surfaces.
    assert env.parse_runtime("node@20") == ("node", "20")


def test_parse_runtime_rejects_unknown_lang() -> None:
    with pytest.raises(env.EnvError, match="unsupported"):
        env.parse_runtime("cobol@85")


# ── seed_files ────────────────────────────────────────────────────────────────


def test_seed_files_inline_and_nested(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    env.seed_files({"config.toml": "key = 1\n", "data/seed.csv": "a,b\n"}, ws, base_dir=tmp_path)
    assert (ws / "config.toml").read_text() == "key = 1\n"
    assert (ws / "data/seed.csv").read_text() == "a,b\n"  # nested dir created


def test_seed_files_copies_from_local(tmp_path) -> None:
    src = tmp_path / "fixtures" / "seed.csv"
    src.parent.mkdir(parents=True)
    src.write_text("x,y\n1,2\n")
    ws = tmp_path / "ws"
    ws.mkdir()
    env.seed_files({"data.csv": {"from": "fixtures/seed.csv"}}, ws, base_dir=tmp_path)
    assert (ws / "data.csv").read_text() == "x,y\n1,2\n"


def test_seed_files_missing_source_errors(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(env.EnvError, match="not found"):
        env.seed_files({"x": {"from": "nope.csv"}}, ws, base_dir=tmp_path)


def test_seed_files_blocks_escape_from_workspace(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(env.EnvError, match="escapes"):
        env.seed_files({"../evil.txt": "x"}, ws, base_dir=tmp_path)


# ── materialize dispatch (provisioner stubbed; no uv) ─────────────────────────


def test_materialize_seeds_files_and_view(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_python(prefix, version, pip, mat):
        calls.append(("python", version))
        mat.path_additions.append(str(prefix / "python" / "bin"))

    monkeypatch.setitem(env._PROVISIONERS, "python", fake_python)

    e = env.Environment.parse(
        {
            "runtimes": ["python@3.12"],
            "packages": {"pip": ["six"]},
            "files": {"hello.txt": "hi"},
            "expose": {"write": ["./out"], "net": ["api.x.test"]},
        }
    )
    root = tmp_path / "env"
    mat = env.materialize(e, root, base_dir=tmp_path)

    assert calls == [("python", "3.12")]  # provisioner dispatched with the version
    assert (mat.workspace / "hello.txt").read_text() == "hi"  # files seeded
    assert str(mat.workspace) in mat.write_paths  # workspace always writable
    assert any("out" in p for p in mat.write_paths)  # expose.write folded in
    assert "api.x.test" in mat.net
    assert any(p.endswith("python/bin") for p in mat.path_additions)


def test_materialize_unimplemented_tool_errors(tmp_path) -> None:
    e = env.Environment.parse({"runtimes": ["node@20"]})
    with pytest.raises(env.EnvError, match="not implemented"):
        env.materialize(e, tmp_path / "env", base_dir=tmp_path)


# ── run_agent runs inside a materialized env (machinery stubbed) ──────────────


def test_run_agent_launches_into_env(tmp_path, monkeypatch) -> None:
    from avp_conformance.manifest import AgentManifest

    from avp.commission import Commission
    from avp_cli import agent as agent_mod

    cap: dict = {}
    seen: dict = {}

    def fake_blocking(cmd, cwd, run_env, timeout_s):
        cap["cmd"], cap["cwd"], cap["env"] = cmd, cwd, run_env
        from pathlib import Path

        Path(cmd[cmd.index("--out") + 1]).write_text("")
        return None

    def fake_settings(directory, *, write_paths, allow_domains):
        seen["write"], seen["allow"] = write_paths, allow_domains
        from pathlib import Path

        p = Path(directory) / "s.json"
        p.write_text("{}")
        return p

    monkeypatch.setattr(agent_mod, "_run_blocking", fake_blocking)
    monkeypatch.setattr(agent_mod.sandbox_mod, "settings_file", fake_settings)
    monkeypatch.setattr(agent_mod.sandbox_mod, "prefix", lambda _s: ["SRT", "--"])

    ws = tmp_path / "ws"
    ws.mkdir()
    bindir = str(tmp_path / "prefix" / "python" / "bin")
    mat = env.Materialized(
        prefix=tmp_path / "prefix",
        workspace=ws,
        path_additions=[bindir],
        env_vars={"VIRTUAL_ENV": str(tmp_path / "prefix" / "python")},
        write_paths=[str(ws), str(tmp_path / "out")],
        net=["api.x.test"],
    )
    manifest = AgentManifest(command=["my-agent"], cwd=".", env={})
    commission = Commission(schema_version="0.1", run_id="r", prompt="hi")

    agent_mod.run_agent(
        manifest, tmp_path, commission, out_path=tmp_path / "t.ndjson", sandbox=True, env_mat=mat
    )

    assert cap["cwd"] == ws  # runs in the env workspace, not the manifest dir
    assert cap["env"]["AVP_WORKSPACE"] == str(ws)  # working tree the agent roots into
    assert cap["env"]["AVP_ENV_ROOT"] == str(ws.parent)  # env home for the agent's run state
    assert cap["env"]["VIRTUAL_ENV"].endswith("python")
    assert cap["env"]["PATH"].split(":")[0] == bindir  # prefix bin on PATH first
    assert cap["cmd"][:2] == ["SRT", "--"]  # sandbox wrap present
    assert str(ws) in seen["write"] and str(tmp_path / "out") in seen["write"]
    import tempfile

    assert tempfile.gettempdir() in seen["write"]  # whole OS temp (agents scratch under it)
    assert str(tmp_path) in seen["write"]  # env root (workspace.parent) for the agent's run state
    assert "api.x.test" in seen["allow"]  # env network folded into the srt view


# ── build_block / parse_file_arg (the `avp env create` builder) ───────────────


def test_parse_file_arg_inline_and_from() -> None:
    assert env.parse_file_arg("a.py=print(1)") == ("a.py", "print(1)")
    assert env.parse_file_arg("d.csv=@fixtures/x.csv") == ("d.csv", {"from": "fixtures/x.csv"})
    assert env.parse_file_arg("k=a=b") == ("k", "a=b")  # split on the first '='


def test_parse_file_arg_rejects_no_equals() -> None:
    with pytest.raises(env.EnvError, match="PATH=CONTENT"):
        env.parse_file_arg("nope")


def test_build_block_assembles_and_validates() -> None:
    block = env.build_block(
        runtimes=["python@3.12"], pip=["pandas"], files=["a.py=import pandas"], net=["api.x.test"]
    )
    assert block == {
        "runtimes": ["python@3.12"],
        "packages": {"pip": ["pandas"]},
        "files": {"a.py": "import pandas"},
        "expose": {"net": ["api.x.test"]},
    }


def test_build_block_validates_tool_names() -> None:
    with pytest.raises(env.EnvError, match="unsupported"):
        env.build_block(runtimes=["cobol@85"])


def test_build_block_empty_is_valid() -> None:
    assert env.build_block() == {}


def test_build_block_paths() -> None:
    assert env.build_block(paths=("/abs/code",)) == {"paths": ["/abs/code"]}


# ── paths: copy a local dir/file into the workspace ───────────────────────────


def test_parse_paths() -> None:
    assert env.Environment.parse({"paths": ["code", "data"]}).paths == ["code", "data"]


def test_materialize_copies_a_directory_tree(tmp_path) -> None:
    src = tmp_path / "code" / "pkg"
    src.mkdir(parents=True)
    (src.parent / "main.py").write_text("print('hi')")
    (src / "util.py").write_text("x = 1")
    e = env.Environment.parse({"paths": [str(tmp_path / "code")]})
    mat = env.materialize(e, tmp_path / "env", base_dir=tmp_path)
    assert (mat.workspace / "main.py").read_text() == "print('hi')"
    assert (mat.workspace / "pkg" / "util.py").read_text() == "x = 1"  # tree preserved


def test_materialize_copies_a_single_file(tmp_path) -> None:
    (tmp_path / "notes.md").write_text("hello")
    e = env.Environment.parse({"paths": [str(tmp_path / "notes.md")]})
    mat = env.materialize(e, tmp_path / "env", base_dir=tmp_path)
    assert (mat.workspace / "notes.md").read_text() == "hello"


def test_materialize_path_missing_errors(tmp_path) -> None:
    e = env.Environment.parse({"paths": ["does-not-exist"]})
    with pytest.raises(env.EnvError, match="not found"):
        env.materialize(e, tmp_path / "env", base_dir=tmp_path)


def test_materialize_path_skips_noise(tmp_path) -> None:
    src = tmp_path / "repo"
    (src / "pkg").mkdir(parents=True)
    (src / "main.py").write_text("x")
    (src / "pkg" / "util.py").write_text("y")
    for noise in (".git/config", "node_modules/dep/index.js", "__pycache__/m.pyc", ".venv/bin/py"):
        f = src / noise
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("noise")
    (src / "stale.pyc").write_text("z")
    mat = env.materialize(
        env.Environment.parse({"paths": [str(src)]}), tmp_path / "e", base_dir=tmp_path
    )
    ws = mat.workspace
    assert (ws / "main.py").is_file() and (ws / "pkg" / "util.py").is_file()  # code copied
    for skipped in (".git", "node_modules", "__pycache__", ".venv", "stale.pyc"):
        assert not (ws / skipped).exists(), f"{skipped} should have been ignored"


def test_launch_env_sets_cwd_path_and_vars(tmp_path) -> None:
    bindir = str(tmp_path / "p" / "python" / "bin")
    mat = env.Materialized(
        prefix=tmp_path / "p",
        workspace=tmp_path / "ws",
        path_additions=[bindir],
        env_vars={"VIRTUAL_ENV": str(tmp_path / "p" / "python")},
    )
    argv, cwd, proc_env = env.launch_env(["python", "-c", "1"], mat)
    assert argv == ["python", "-c", "1"]
    assert cwd == tmp_path / "ws"
    assert proc_env["PATH"].split(":")[0] == bindir  # prefix bin first
    assert proc_env["VIRTUAL_ENV"].endswith("python")
