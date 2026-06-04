"""Declarative environments: parse the image-first block, seed the workspace,
and compile (env, agent recipe) to a cached Dockerfile.

Environments are a CLI-side concept (the spec never learns the word): they
describe the container world an agent runs in. Nothing here touches Docker;
the real-build path is covered by the docker-gated seam test."""

from __future__ import annotations

import pytest

from avp_cli import environment as env
from avp_cli import images

# ── parse ─────────────────────────────────────────────────────────────────────


def test_parse_minimal_defaults_image() -> None:
    e = env.Environment.parse({})
    assert e.image == env.DEFAULT_IMAGE
    assert e.packages == {} and e.files == {} and e.setup == []
    assert e.net == [] and e.resources == {}


def test_parse_full_block() -> None:
    e = env.Environment.parse(
        {
            "image": "python:3.12-slim",
            "packages": {"apt": ["git"], "pip": ["six"]},
            "files": {"a.txt": "hi"},
            "setup": ["pip install -e ."],
            "net": ["api.x.test"],
            "resources": {"cpu": "2", "memory": "4Gi"},
        }
    )
    assert e.image == "python:3.12-slim"
    assert e.packages == {"apt": ["git"], "pip": ["six"]}
    assert e.files == {"a.txt": "hi"}
    assert e.setup == ["pip install -e ."]
    assert e.net == ["api.x.test"]
    assert e.resources == {"cpu": "2", "memory": "4Gi"}


def test_parse_rejects_non_object() -> None:
    with pytest.raises(env.EnvError):
        env.Environment.parse([])  # type: ignore[arg-type]


def test_parse_rejects_unknown_key() -> None:
    with pytest.raises(env.EnvError, match="unknown"):
        env.Environment.parse({"nope": 1})


def test_parse_points_old_specs_at_the_new_model() -> None:
    # The pre-container shape gets a teaching error, not a generic "unknown key".
    with pytest.raises(env.EnvError, match="container images now"):
        env.Environment.parse({"runtimes": ["python@3.12"]})
    with pytest.raises(env.EnvError, match="'net' instead of 'expose'"):
        env.Environment.parse({"expose": {"write": ["./out"]}})


def test_parse_rejects_unknown_ecosystem_and_resource() -> None:
    with pytest.raises(env.EnvError, match="ecosystem"):
        env.Environment.parse({"packages": {"npm": ["left-pad"]}})
    with pytest.raises(env.EnvError, match="resource"):
        env.Environment.parse({"resources": {"gpu": "1"}})


# ── seed_workspace / seed_files ───────────────────────────────────────────────


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


def test_seed_workspace_copies_a_directory_tree(tmp_path) -> None:
    src = tmp_path / "code" / "pkg"
    src.mkdir(parents=True)
    (src.parent / "main.py").write_text("print('hi')")
    (src / "util.py").write_text("x = 1")
    e = env.Environment.parse({"paths": [str(tmp_path / "code")]})
    ws = env.seed_workspace(e, tmp_path / "run" / "work", base_dir=tmp_path)
    assert (ws / "main.py").read_text() == "print('hi')"
    assert (ws / "pkg" / "util.py").read_text() == "x = 1"  # tree preserved


def test_seed_workspace_copies_a_single_file(tmp_path) -> None:
    (tmp_path / "notes.md").write_text("hello")
    e = env.Environment.parse({"paths": [str(tmp_path / "notes.md")]})
    ws = env.seed_workspace(e, tmp_path / "work", base_dir=tmp_path)
    assert (ws / "notes.md").read_text() == "hello"


def test_seed_workspace_path_missing_errors(tmp_path) -> None:
    e = env.Environment.parse({"paths": ["does-not-exist"]})
    with pytest.raises(env.EnvError, match="not found"):
        env.seed_workspace(e, tmp_path / "work", base_dir=tmp_path)


def test_seed_workspace_skips_noise(tmp_path) -> None:
    src = tmp_path / "repo"
    (src / "pkg").mkdir(parents=True)
    (src / "main.py").write_text("x")
    (src / "pkg" / "util.py").write_text("y")
    for noise in (".git/config", "node_modules/dep/index.js", "__pycache__/m.pyc", ".venv/bin/py"):
        f = src / noise
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("noise")
    (src / "stale.pyc").write_text("z")
    e = env.Environment.parse({"paths": [str(src)]})
    ws = env.seed_workspace(e, tmp_path / "work", base_dir=tmp_path)
    assert (ws / "main.py").is_file() and (ws / "pkg" / "util.py").is_file()  # code copied
    for skipped in (".git", "node_modules", "__pycache__", ".venv", "stale.pyc"):
        assert not (ws / skipped).exists(), f"{skipped} should have been ignored"


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
        image="python:3.12-slim",
        apt=("git",),
        pip=("pandas",),
        files=("a.py=import pandas",),
        net=("api.x.test",),
        cpu="2",
    )
    assert block == {
        "image": "python:3.12-slim",
        "packages": {"apt": ["git"], "pip": ["pandas"]},
        "files": {"a.py": "import pandas"},
        "net": ["api.x.test"],
        "resources": {"cpu": "2"},
    }


def test_build_block_empty_is_valid() -> None:
    assert env.build_block() == {}


def test_build_block_paths() -> None:
    assert env.build_block(paths=("/abs/code",)) == {"paths": ["/abs/code"]}


# ── dockerfile compilation + tag hashing ──────────────────────────────────────

_RECIPE = images.ContainerRecipe(
    install=("curl -L https://example.test/agent -o /usr/local/bin/agent",),
    command=("agent",),
)


def test_dockerfile_layers_in_cache_stable_order() -> None:
    e = env.Environment.parse(
        {"image": "python:3.12-slim", "packages": {"apt": ["git"], "pip": ["six"]}}
    )
    df = images.dockerfile(e, _RECIPE)
    lines = df.strip().splitlines()
    assert lines[0] == "FROM python:3.12-slim"
    assert "apt-get install -y --no-install-recommends git" in lines[1]
    assert lines[2] == "RUN pip install --no-cache-dir six"
    assert lines[3].startswith("RUN curl -L")  # agent install is the last layer


def test_dockerfile_omits_empty_layers() -> None:
    df = images.dockerfile(env.Environment.parse({}), _RECIPE)
    assert "apt-get" not in df and "pip install" not in df


def test_image_tag_is_content_addressed() -> None:
    a = env.Environment.parse({"packages": {"pip": ["six"]}})
    b = env.Environment.parse({"packages": {"pip": ["six"]}})
    c = env.Environment.parse({"packages": {"pip": ["seven"]}})
    assert images.image_tag(a, _RECIPE) == images.image_tag(b, _RECIPE)  # same shape, same tag
    assert images.image_tag(a, _RECIPE) != images.image_tag(c, _RECIPE)  # content change, new tag
    other = images.ContainerRecipe(install=("true",), command=("agent",))
    assert images.image_tag(a, _RECIPE) != images.image_tag(a, other)  # agent change, new tag


def test_ensure_image_reuses_existing_tag(monkeypatch) -> None:
    e = env.Environment.parse({})
    calls: list[list[str]] = []

    class FakeDone:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeDone()

    monkeypatch.setattr(images.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(images.subprocess, "run", fake_run)
    tag = images.ensure_image(e, _RECIPE)
    assert tag == images.image_tag(e, _RECIPE)
    assert calls and calls[0][1:3] == ["image", "inspect"]  # cache probe only, no build
