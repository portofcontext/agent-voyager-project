"""`avp` - the local AVP CLI for building, running, and iterating on Commissions.

    avp                              getting-started + agent routing (no args)
    avp init [KEY] [--dir D]         scaffold an eval (in place) + its commissions (to ~/.avp)
    avp eval run CONFIG              run an eval config, print a ranked board
    avp eval list                    list recent eval runs (with their ids)
    avp eval view [ID]               open an eval on agentvoyagerproject.com (default: most recent)
    avp eval delete ID [--all]       delete one recorded run by id (or --all for every run)
    avp run "TASK" --agent A [--env E]   commission an agent to do a task (in a sandbox)
    avp agent install NAME           install a prebuilt agent (release, or --binary/--wheel local)
    avp env create NAME [flags]      create a declarative environment (--image/--pip/--file/--net ...)
    avp env run NAME -- CMD          run a command inside a declarative environment (sandboxed)
    avp sandbox status|stop          inspect or stop the managed sandbox server
    avp cm create ID --agent A   generate a complete commission (full surface; edit the JSON)
    avp cm list              list your portable commission library
    avp cm describe ID       render a library commission by id
    avp cm check ID|FILE     check a library commission, or a Commission JSON file
    avp cm delete ID         remove a commission from your library

An eval is a JSON config file authored in place (no code); commissions are
portable artifacts in ~/.avp/commissions referenced by id. The CLI is the engine.
Every run executes inside an OpenSandbox container (Docker is the one
prerequisite; the CLI manages the rest); provider credentials forward from the
host environment into the sandbox. When the sandbox stack can't run, exit is 2.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import webbrowser
from pathlib import Path

import questionary

from avp_cli import (
    brand,
    catalog,
    config,
    console,
    images,
    library,
    live,
    local_models,
    osb,
    paths,
    run_manifest,
    runtime,
    state,
    viz,
)
from avp_cli import commission as commission_mod
from avp_cli.agent import SandboxContext, SandboxedAgent
from avp_cli.agents import (
    DEFAULT_AGENT,
    NoContainerRecipe,
    container_recipe,
    known_agents,
    preflight,
    resolve_agent,
)
from avp_cli.eval.engine import Eval, RunObserver, RunResult, run_matrix, setups_for
from avp_cli.eval.report import board_table, comparison_table, dump_json, failures
from avp_cli.observability import tool_tally
from avp_cli.onboarding import welcome

_SKIP = 2  # the sandbox stack / agent can't run here; skip cleanly rather than error

# Branded picker palette: sail-gold marker/pointer/answer, sky highlight, and
# gold titles with dim descriptions in the choice rows.
# `noreverse` on highlighted/selected: convey state with the pointer and the
# filled circle (●) + gold text, not a reversed background block.
_PICKER_STYLE = questionary.Style(
    [
        ("qmark", f"fg:{brand.SAIL} bold"),
        ("question", "bold"),
        ("pointer", f"fg:{brand.SAIL} bold noreverse"),
        ("highlighted", f"fg:{brand.SKY} bold noreverse"),
        ("selected", f"fg:{brand.SAIL} noreverse"),
        ("answer", f"fg:{brand.SAIL} bold"),
        ("instruction", "fg:#7fa0b3"),
        ("ben-title", f"fg:{brand.SAIL} bold"),
        ("ben-desc", "fg:#7fa0b3"),
        ("ben-needs", f"fg:{brand.HULL}"),
    ]
)


def _default_out_dir() -> Path:
    return paths.runs_dir()


def _tilde(p: Path) -> str:
    """Render a path with $HOME collapsed to ~ for tidy display."""
    home = Path.home()
    return f"~/{p.relative_to(home)}" if p.is_relative_to(home) else str(p)


def _run_and_report(
    ev: Eval,
    *,
    run_id: str,
    agent_specs: list[str],
    out: Path,
    json_path: str | None,
    max_items: int | None,
    model: str | None,
    quiet: bool,
    sandbox_ctx: SandboxContext,
    env_obj,
    config_path: str | None = None,
    timeout_s: float = 300.0,
    resume: bool = False,
) -> int:
    runnable = []
    for spec in agent_specs:
        agent = resolve_agent(spec)
        prepared = _prepare_agent(agent, env_obj, quiet=quiet, runtime_name=sandbox_ctx.runtime)
        if prepared is not None:
            runnable.append(prepared)
    if not runnable:
        console.warn("no runnable agents; nothing to do.")
        return _SKIP

    # Snapshot what this run uses BEFORE the matrix, so a crashed run still records
    # its inputs and the record is immune to later edits of the library commissions.
    run_manifest.write(
        out,
        run_id=run_id,
        setups=ev.setups,
        eval_config_path=config_path,
        agents=[a.name for a in runnable],
        model_override=model,
        max_items=max_items,
        threshold_override=getattr(ev.scorer, "threshold", None),
    )

    compare = len(runnable) > 1  # multiple agents -> interleave by task + head-to-head
    n_items = max_items or len(ev.dataset)
    total = n_items * sum(len(setups_for(ev.setups, a.name)) for a in runnable)
    label = " vs ".join(a.name for a in runnable)
    # Live voyage when we have an interactive terminal; plain note lines otherwise.
    live_mode = not quiet and console.err.is_terminal

    if live_mode:
        with live.VoyageLive(label, total, compare=compare) as vl:
            boards = run_matrix(
                ev,
                runnable,
                sandbox_ctx,
                out_dir=out,
                max_items=max_items,
                model=model,
                timeout_s=timeout_s,
                observer=vl.observer(),
                compare=compare,
                resume=resume,
            )
    else:
        observer = None if quiet else _note_observer(total, compare=compare)
        boards = run_matrix(
            ev,
            runnable,
            sandbox_ctx,
            out_dir=out,
            max_items=max_items,
            model=model,
            timeout_s=timeout_s,
            observer=observer,
            compare=compare,
            resume=resume,
        )

    for board in boards:
        console.out.print(board_table(board))
        if board.interrupted:
            console.warn("stopped early (Ctrl-C) — board reflects only the runs that finished")
        fails = failures(board)
        if fails:
            console.diag("failures", "\n".join(fails))
        if json_path:
            path = (
                json_path
                if len(boards) == 1
                else f"{json_path.rsplit('.', 1)[0]}.{board.agent_label}.json"
            )
            dump_json(board, path)
            console.note(f"wrote machine-readable board to {path}")

    if compare and len(boards) > 1:
        console.out.print(comparison_table(boards))

    _finish_run(ev, boards, out, run_id)
    return 0


def _agent_identity(agent) -> tuple[str | None, str | None]:
    """The agent's self-declared `descriptor.agent_name`: registry metadata
    for known agents (free), one host-side `describe` for manifest-path
    agents. This is the ONE public identity that keys Commission
    `enabled_builtin_*` / `agent_versions` maps, eval per-agent bindings,
    and board labels; the resolution spec (alias or path) is just a locator."""
    if agent.agent_name:
        return agent.agent_name, None
    from avp_cli.agent import describe_agent

    descriptor, err = describe_agent(agent.manifest, agent.manifest_cwd)
    if descriptor is None:
        return None, err
    return descriptor.agent_name, None


def _prepare_agent(
    agent, env_obj, *, quiet: bool, runtime_name: str = "opensandbox"
) -> SandboxedAgent | None:
    """Resolve one agent to its sandbox form: identity (descriptor agent_name)
    + recipe + derived image (built or reused). Returns None (with a warning)
    when the agent can't run."""
    agent_name, err = _agent_identity(agent)
    if agent_name is None:
        console.warn(
            f"skipping agent '{agent.name}': couldn't learn its identity via "
            f"describe ({err}). Per-agent Commission maps and eval bindings key "
            "on descriptor.agent_name, so a describable agent is required."
        )
        return None
    try:
        recipe = container_recipe(agent)
    except NoContainerRecipe as exc:
        console.warn(f"skipping agent '{agent.name}': {exc}")
        return None
    # The libkrun backend runs a prebuilt GPU image (goose's `vulkan` build on a
    # Venus runtime) from the podman machine's own storage; the env-derived Docker
    # image build doesn't apply. AVP_LIBKRUN_IMAGE names it. (A first-class GPU
    # agent-image recipe + release is the follow-up; this unblocks the path now.)
    libkrun_image = os.environ.get("AVP_LIBKRUN_IMAGE")
    if runtime_name == "libkrun" and libkrun_image:
        built = libkrun_image
    else:
        tag = images.image_tag(env_obj, recipe)

        def _emit(line: str) -> None:
            console.err.print(line, style="dim", markup=False, highlight=False)

        on_line = None if quiet else _emit
        try:
            built = images.ensure_image(env_obj, recipe, on_line=on_line)
        except images.ImageBuildError as exc:
            console.warn(f"skipping agent '{agent.name}': {exc}")
            return None
        if built == tag and not quiet:
            console.note(f"sandbox image for {agent.name}: {built}")
    return SandboxedAgent(
        name=agent_name,
        image=built,
        command=recipe.command,
        env={**dict(recipe.env), **agent.manifest.env},
    )


def _prepare_sandbox(
    env_spec: str | None, workspace_root: Path, *, runtime_name: str = "opensandbox"
):
    """Parse the env (or the default), bring up the sandbox backend, and seed the
    run workspace. Returns (env_obj, SandboxContext); raises EnvError /
    SandboxUnavailable / OSError / JSONDecodeError."""
    from avp_cli import environment as env_mod

    if env_spec:
        p = _resolve_env_file(env_spec)
        env_obj = env_mod.Environment.parse(json.loads(p.read_text()))
        base_dir = p.parent
    else:
        env_obj = env_mod.Environment.parse({})
        base_dir = Path.cwd()
    # The libkrun backend runs on a podman machine, not the Docker-based
    # OpenSandbox server, so skip standing it up; the connection is unused there.
    if runtime_name == "libkrun":
        conn = osb.Connection(domain="127.0.0.1:0", api_key="unused-by-libkrun")
    else:
        conn = osb.ensure_server()
    workspace = env_mod.seed_workspace(env_obj, workspace_root / "workspace", base_dir=base_dir)
    return env_obj, SandboxContext(
        connection=conn,
        workspace=workspace,
        setup=env_obj.setup,
        net=env_obj.net,
        resources=env_obj.resources,
        runtime=runtime_name,
    )


def _workspace_root(out: Path, run_id: str) -> Path:
    """Where the run's workspace lives: under `out` when that's inside ~/.avp
    (the sandbox server only bind-mounts paths there), else under ~/.avp/runs."""
    home = paths.avp_home().resolve()
    o = out.resolve()
    return o if o.is_relative_to(home) else paths.runs_dir() / run_id


def _finish_run(ev: Eval, boards: list, out: Path, run_id: str) -> None:
    """Write each agent's trajectories.json, record the run, and print its id.

    The CLI produces the data, the site renders it: `trajectories.json` (one per
    agent, the site's `by_commission` shape + a `commissions` config block) is
    what `avp eval view <id>` opens. The run is recorded so `view` / `list` find
    it by id even when `--out` was used.
    """
    from datetime import datetime

    if not boards or not any(b.rows for b in boards):
        return
    eval_version = datetime.now().strftime("%Y%m%d-%H%M%S")

    out.mkdir(parents=True, exist_ok=True)
    for board in boards:
        payload = viz.to_trajectories_payload(board, eval_version=eval_version, ev=ev)
        name = "trajectories.json" if len(boards) == 1 else f"trajectories.{board.agent_label}.json"
        (out / name).write_text(json.dumps(payload, indent=2))

    state.record_run(
        run_id=run_id,
        out_dir=out,
        dataset=ev.dataset.name,
        agents=[b.agent_label for b in boards],
        commissions=list(dict.fromkeys(s.id for s in ev.setups)),
    )

    console.out.print()
    console.out.print(
        f"  [bold {brand.SAIL}]{brand.SAILBOAT} {run_id}[/]   "
        f"view it: [bold]avp eval view {run_id}[/bold]"
    )


def _note_observer(total: int, *, compare: bool) -> RunObserver:
    """Plain stderr progress (one line per run start/end) for non-TTY / piped use."""

    def on_start(n: int, _total: int, agent: str, setup: str, item: str) -> None:
        console.note(f"[{n}/{total}] {agent} / {setup} / {item} ... running")

    def on_end(n: int, _total: int, agent: str, r: RunResult) -> None:
        if r.spawn_error is not None:
            console.note(
                f"[{n}/{total}] {agent} / {r.setup_name} / {r.item_id}  ERROR: {r.spawn_error}"
            )
            return
        passed = bool(r.score and r.score.passed)
        score = f"{r.score.value:.0%}" if r.score else "—"
        cost = f"${r.summary.total_cost_usd:.4f}" if r.summary else "—"
        turns = r.summary.total_turns if r.summary else "—"
        tally = f"  {tool_tally(r.summary)}" if r.summary and tool_tally(r.summary) else ""
        console.note(
            f"[{n}/{total}] {agent} / {r.setup_name} / {r.item_id}  "
            f"{'PASS' if passed else 'fail'} score={score} {cost} {turns} turns{tally}"
        )

    def on_compare(setup: str, item: str, pairs: list[tuple[str, RunResult]]) -> None:
        parts = []
        for agent, r in pairs:
            if r.spawn_error is not None:
                parts.append(f"{agent} err")
            else:
                acc = f"{r.score.value:.0%}" if r.score else "—"
                cost = f"${r.summary.total_cost_usd:.4f}" if r.summary else "—"
                parts.append(f"{agent} {acc} {cost}")
        console.note(f"  ⚖ {setup} / {item}   " + "   ·   ".join(parts))

    return RunObserver(on_start=on_start, on_end=on_end, on_compare=on_compare if compare else None)


# ── init ─────────────────────────────────────────────────────────────────────


def _pick_entry() -> catalog.CatalogEntry:
    """Arrow-key select a benchmark. Falls back to the first entry off a TTY."""
    if not sys.stdin.isatty():
        return catalog.ENTRIES[0]
    choices = []
    for e in catalog.ENTRIES:
        # Two-tone, brand-colored row: gold title, dim description, hull "needs".
        title = [("class:ben-title", e.title), ("class:ben-desc", f"  —  {e.description}")]
        if e.needs:
            title.append(("class:ben-needs", f"  (needs --extra {' --extra '.join(e.needs)})"))
        choices.append(questionary.Choice(title=title, value=e.key))
    key = questionary.select(
        "Pick a benchmark to scaffold:",
        choices=choices,
        qmark=brand.SAILBOAT,
        pointer="»",
        instruction=" ",
        style=_PICKER_STYLE,
    ).ask()
    if key is None:  # user hit Ctrl-C / Esc
        raise SystemExit(0)
    return catalog.get(key)  # type: ignore[return-value]


def _pick_agents() -> list[str]:
    """Space-bar multiselect which agent(s) the scaffolded eval runs against.

    The chosen names are pinned into the config so `avp eval run` needs no
    `--agent`. Falls back to the default agent off a TTY.
    """
    names = known_agents()
    if not sys.stdin.isatty():
        return [DEFAULT_AGENT] if DEFAULT_AGENT in names else names[:1]
    # Nothing pre-checked: the user actively chooses, and must pick at least one.
    choices = [questionary.Choice(title=n, value=n) for n in names]
    picked = questionary.checkbox(
        "Which agent(s) should this eval run against?",
        choices=choices,
        qmark=brand.SAILBOAT,
        pointer="»",
        instruction="(space to toggle, enter to confirm)",
        validate=lambda sel: bool(sel) or "select at least one agent (space to toggle)",
        style=_PICKER_STYLE,
    ).ask()
    if picked is None:
        raise SystemExit(0)
    return picked


def _cmd_init(args: argparse.Namespace) -> int:
    if args.key:
        entry = catalog.get(args.key)
        if entry is None:
            keys = ", ".join(e.key for e in catalog.ENTRIES)
            console.error_panel("unknown benchmark", f"{args.key!r}; choose from: {keys}")
            return 1
    else:
        entry = _pick_entry()

    agents = (
        [a.strip() for a in args.agent.split(",") if a.strip()] if args.agent else _pick_agents()
    )

    result = catalog.scaffold(entry, Path(args.dir).resolve(), agents=agents)
    target = result.eval_path
    body = [f"eval file (edit me): [bold]{target}[/bold]"]
    if result.installed:
        body.append(f"commissions → library: [bold]{', '.join(result.installed)}[/bold]")
    if result.skipped:
        body.append(f"[dim]already in your library (reused): {', '.join(result.skipped)}[/dim]")
    body.append(f'agents: [bold]{", ".join(agents)}[/bold] (edit the "agents" key or pass --agent)')
    if entry.needs:
        body.append(
            f"\nthis benchmark needs: [bold]uv sync --extra {' --extra '.join(entry.needs)}[/bold]"
        )
    body.append(f"\nnext:\n  avp eval run {target.name}")
    console.panel(entry.title, "\n".join(body), style="green")
    return 0


# ── commission ────────────────────────────────────────────────────────────────


def _cmd_commission(args: argparse.Namespace) -> int:
    if args.commission_cmd == "create":
        return _cmd_commission_create(args)
    if args.commission_cmd == "list":
        return _cmd_commission_list()
    if args.commission_cmd == "check":
        return _cmd_commission_validate(args.target)
    if args.commission_cmd == "delete":
        if not library.delete(args.id):
            console.error_panel(
                f"no commission {args.id!r}",
                f"not in your library ({_tilde(paths.commissions_dir())}) — see `avp cm list`.",
            )
            return 1
        console.note(f"deleted commission {args.id}")
        return 0

    # describe: a library id (the raw wire Commission) first, else a Commission JSON file
    if library.exists(args.id):
        c = library.load(args.id)
        console.print_json(commission_mod.full_dict(c))
        console.note(
            "the raw AVP Commission. `{input}` in the prompt is filled per dataset case, "
            "and run_id + supervisor are assigned at run time."
        )
        return 0
    try:
        c = commission_mod.load_commission_file(args.id)
    except Exception as exc:
        console.error_panel(
            f"no commission {args.id!r}",
            f"not a library id (see `avp cm list`) nor a readable Commission file: {exc}",
        )
        return 1
    console.print_json(commission_mod.full_dict(c))
    return 0


_ID_RE = re.compile(r"^[a-z0-9_-]+$")


def _describe_for_create(spec: str) -> tuple[object | None, str | None]:
    """Resolve an agent spec and fetch its Descriptor; (descriptor, error)."""
    from avp_cli.agent import describe_agent

    try:
        agent = resolve_agent(spec)
    except SystemExit as exc:  # resolve_agent raises this on a missing manifest
        return None, str(exc)
    reason = preflight(agent.name)
    if reason is not None:
        return None, reason
    return describe_agent(agent.manifest, agent.manifest_cwd)


def _cmd_commission_create(args: argparse.Namespace) -> int:
    """Generate a complete wire Commission into the library; edit the JSON after.

    No wizard: `--agent` enumerates the agent's full builtin surface into the
    per-agent `enabled_builtin_*` maps, pins `agent_versions`, fills a sample
    `{input}` prompt and a runnable model, and writes the file. Restricting the
    surface is deleting lines from the JSON (a job for a coding agent), not
    answering pickers. `--from <id>` clones an existing commission instead
    (carrying its bulky fields: `output_schema`, inline `mcp_servers`/`skills`).
    """
    cid = args.id
    if not _ID_RE.match(cid):
        console.error_panel(
            "invalid commission id",
            f"{cid!r}: use lowercase letters, digits, '-' and '_' (it becomes <id>.json).",
        )
        return 1
    if library.exists(cid) and not args.force:
        console.error_panel(
            f"commission {cid!r} already exists",
            f"in {_tilde(paths.commissions_dir())} — pass --force to overwrite, or pick another id.",
        )
        return 1

    base = None
    if args.from_id:
        try:
            base = library.load(args.from_id)
        except library.CommissionError as exc:
            console.error_panel(f"can't clone {args.from_id!r}", str(exc))
            return 1

    # Generation enumerates the agent's real surface, so it needs a describable
    # agent; a partial file full of guesses would defeat the point.
    descriptor = None
    if args.agent:
        descriptor, err = _describe_for_create(args.agent)
        if descriptor is None:
            console.error_panel(
                f"couldn't describe '{args.agent}'",
                f"{err}. Generation enumerates the agent's tools/skills/subagents "
                "from its descriptor, so the agent must be installed and describable "
                "(`avp agent list`).",
            )
            return 1

    try:
        c = commission_mod.build_commission(
            cid,
            base=base,
            model=args.model,
            provider_id=args.provider_id,
            provider_base_url=args.provider_base_url,
            credential=args.credential,
            descriptor=descriptor,
        )
    except commission_mod.BuildError as exc:
        console.error_panel("can't build that commission", str(exc))
        return 1

    path = library.save(cid, c, overwrite=args.force)
    console.out.print(
        f"[green]✓[/] created [bold {brand.SAIL}]{cid}[/] in {_tilde(paths.commissions_dir())}"
    )
    console.note(f"edit it: {_tilde(path)} (delete allowlist lines to restrict the surface)")
    console.note(f"avp cm describe {cid}  ·  see the full wire Commission")
    console.note(f'reference it in an eval\'s "commissions" list as "{cid}"')
    return 0


def _cmd_commission_validate(target: str) -> int:
    """Validate a library commission by id, or a wire Commission JSON file.

    Either way it's the same check: does it parse as a valid AVP wire Commission?
    """
    if library.exists(target):
        try:
            library.load(target)
        except library.CommissionError as exc:
            console.error_panel(f"invalid commission {target!r}", str(exc))
            return 1
        console.out.print(f"[green]✓[/] commission '{target}' is a valid Commission")
        return 0
    if not Path(target).is_file():
        console.error_panel(
            f"no commission {target!r}",
            "not a library id (see `avp cm list`) nor a path to a Commission .json file.",
        )
        return 1
    ok, msg = commission_mod.validate_file(target)
    if ok:
        console.out.print(f"[green]✓[/] {target} is a valid Commission")
        return 0
    console.error_panel("invalid Commission", msg)
    return 1


def _cmd_commission_list() -> int:
    """List the portable commission library (`~/.avp/commissions/`)."""
    from rich.table import Table

    commissions = library.list_commissions()
    if not commissions:
        console.note(f"no commissions in {paths.commissions_dir()} — `avp init` scaffolds some.")
        return 0
    table = Table(title="", header_style="bold")
    table.add_column("id", style=f"bold {brand.SAIL}", no_wrap=True)
    table.add_column("model")
    table.add_column("prompt", overflow="fold")
    for cid, c in commissions:
        table.add_row(cid, c.model or "[dim](agent default)[/dim]", c.prompt or "[dim]—[/dim]")
    console.out.print(table)
    console.note(f"in {_tilde(paths.commissions_dir())}")
    console.note("avp cm describe <id>  ·  see the full Commission")
    return 0


# ── agent ───────────────────────────────────────────────────────────────────────


def _cmd_agent(args: argparse.Namespace) -> int:
    if args.agent_cmd == "list":
        return _cmd_agent_list()
    if args.agent_cmd == "install":
        return _cmd_agent_install(args)
    if args.agent_cmd == "uninstall":
        return _cmd_agent_uninstall(args)
    return _cmd_agent_describe(args.name, json_out=args.json_out)


def _cmd_agent_list() -> int:
    """List known agents: whether each is installed and ready to run."""
    from rich.table import Table

    from avp_cli import agent_install
    from avp_cli.agents import has_dev_fallback

    table = Table(title="agents", header_style="bold")
    table.add_column("name", style=f"bold {brand.SAIL}", no_wrap=True)
    table.add_column("installed")
    table.add_column("status")
    for name in known_agents():
        info = agent_install.installed_info(name)
        dev = has_dev_fallback(name)
        if info:
            installed = f"v{info.get('version', '?')} ({info.get('source', '?')})"
        elif dev:
            installed = "[dim]in-repo (dev)[/dim]"
        else:
            installed = "[yellow]not installed[/yellow]"
        if info or dev:
            reason = preflight(name)
            status = "[green]ready[/]" if reason is None else f"[yellow]{reason}[/yellow]"
        else:
            status = f"[yellow]run: avp agent install {name}[/yellow]"
        table.add_row(name, installed, status)
    console.out.print(table)
    console.note("avp agent install <name>   ·  install the prebuilt agent")
    console.note("avp agent describe <name>  ·  see its tools, models, skills")
    return 0


def _cmd_agent_install(args: argparse.Namespace) -> int:
    """Install a prebuilt agent from a release, or from local artifacts."""
    from avp_cli import agent_install

    try:
        result = agent_install.install(
            args.name,
            version=args.version,
            binary=args.binary,
            wheels=args.wheel or None,
            force=args.force,
        )
    except agent_install.InstallError as exc:
        console.error_panel(f"couldn't install '{args.name}'", str(exc))
        return 1
    console.out.print(
        f"[green]✓[/] installed [bold {brand.SAIL}]{result.name}[/] "
        f"(v{result.version}, {result.source} {result.kind}) → {_tilde(result.install_dir)}"
    )
    reason = preflight(result.name)
    if reason is not None:
        console.warn(f"runtime prerequisite still needed: {reason}")
    console.note(f"avp agent describe {result.name}  ·  verify it boots")
    return 0


def _cmd_agent_uninstall(args: argparse.Namespace) -> int:
    """Remove an installed agent from ~/.avp/agents."""
    from avp_cli import agent_install

    if agent_install.uninstall(args.name):
        console.note(f"uninstalled agent {args.name}")
        return 0
    console.error_panel(
        f"'{args.name}' is not installed",
        f"nothing at {_tilde(paths.agents_dir() / args.name)} — see `avp agent list`.",
    )
    return 1


def _cmd_agent_describe(name: str, *, json_out: bool) -> int:
    """Fetch + render an agent's AgentDescriptor via its `describe` contract."""
    from avp_cli.agent import describe_agent

    agent = resolve_agent(name)
    reason = preflight(agent.name)
    if reason is not None:
        console.error_panel(f"can't describe '{agent.name}'", reason)
        return _SKIP
    descriptor, err = describe_agent(agent.manifest, agent.manifest_cwd)
    if descriptor is None:
        console.error_panel(f"describe failed for '{agent.name}'", err or "no descriptor")
        return 1
    if json_out:
        console.print_json(descriptor.model_dump(mode="json", by_alias=True, exclude_none=True))
        return 0
    _render_descriptor(name, descriptor)
    return 0


def _render_descriptor(name: str, d) -> None:
    """A readable view of an AgentDescriptor (tools with their first-line docs)."""
    console.out.print(
        f"[bold {brand.SAIL}]{d.agent_name}[/] v{d.agent_version}  ·  spec {d.spec_version}"
    )
    if d.default_model:
        console.out.print(f"  default_model: {d.default_model}")
    if d.supported_models:
        console.out.print(f"  supported_models: {', '.join(d.supported_models)}")
    if d.system_prompt:
        console.out.print(f"  system_prompt: [dim]{d.system_prompt[:100]}[/dim]")

    tools = d.tools or []
    console.out.print(f"\n[bold]tools[/] ({len(tools)})")
    for t in tools:
        params = list((t.inputSchema or {}).get("properties", {})) if t.inputSchema else []
        first_line = (t.description or "").strip().splitlines()
        desc = first_line[0][:80] if first_line else ""
        suffix = f"  ·  via {t.mcp_server_id}" if getattr(t, "mcp_server_id", None) else ""
        console.out.print(f"  [bold {brand.SAIL}]{t.name}[/]{suffix}")
        if desc:
            console.out.print(f"    [dim]{desc}[/dim]")
        if params:
            console.out.print(f"    args: {', '.join(params)}")

    if d.skills:
        console.out.print(f"\nskills: {[s.name for s in d.skills]}")
    if d.mcp_servers:
        console.out.print(f"mcp_servers: {[m.id for m in d.mcp_servers]}")
    if d.subagents:
        console.out.print(f"subagents: {[s.name for s in d.subagents]}")
    if d.capabilities:
        console.out.print(f"capabilities: {', '.join(d.capabilities)}")
    console.note(f"avp agent describe {name} --json  ·  full tool input schemas")


# ── eval ───────────────────────────────────────────────────────────────────────

# Browsers cap total URL length (~2 MB in Chrome); budget the encoded blob under it.
_MAX_VIEW_URL = 1_900_000


def _run_trajectories(path: str | None) -> list[Path]:
    """Every `trajectories*.json` for a run (one per agent when several were compared).

    With a `path`: a voyage id from `avp eval list` (resolved via history), else a
    file as-is, else all `trajectories*.json` in that dir. Without one: the most
    recent recorded run (tracked across `--out`), else the default out dir.
    """
    if path:
        run = state.find_run(path)
        if run is None and Path(path).is_file():
            return [Path(path)]
        base = Path(run["out_dir"]) if run else Path(path)
    else:
        last = state.last_run()
        base = Path(last["out_dir"]) if last else _default_out_dir()
    return sorted(base.glob("trajectories*.json")) if base.is_dir() else []


def _cmd_eval_view(args: argparse.Namespace) -> int:
    """Open a finished eval on the site by encoding its trajectories into the URL.

    A run compared against several agents has one trajectories file per agent; this
    opens them all (a tab each) unless `--agent` narrows it to one.
    """
    files = _run_trajectories(args.path)
    if not files:
        console.error_panel(
            "no trajectories.json found",
            "run `avp eval run <config>` first, or pass a voyage id from "
            "`avp eval list` (or a path to a trajectories.json / eval out dir).",
        )
        return 1

    # Point at the immutable input snapshot for this run, if present.
    mani = run_manifest.read(files[0].parent)
    if mani:
        cids = ", ".join(mani.get("commissions", {}))
        console.note(
            f"config snapshot: {files[0].parent / run_manifest.MANIFEST_NAME}"
            + (f"  (commissions: {cids})" if cids else "")
        )

    payloads = [json.loads(f.read_text()) for f in files]
    runs = [(p.get("agent") or f.stem, p) for f, p in zip(files, payloads, strict=True)]
    available = [label for label, _ in runs]
    if args.agent:
        runs = [(label, p) for label, p in runs if label == args.agent]
        if not runs:
            console.error_panel(
                f"no trajectories for agent {args.agent!r}",
                f"this run has: {', '.join(available)}",
            )
            return 1

    # One link, all agents: the site shows them head-to-head on a single page.
    labels = [label for label, _ in runs]
    url = viz.view_url(viz.combine_payloads([p for _, p in runs]), site=args.site)
    if len(url) > _MAX_VIEW_URL:
        console.error_panel(
            "eval too large to view via link",
            f"the encoded link is ~{len(url) // 1024} KB, over the ~{_MAX_VIEW_URL // 1024} KB "
            "URL budget. Narrow it (`--agent <name>`, or fewer items/commissions) to view it.",
        )
        return 1
    if args.no_open:
        console.out.print(url)
    else:
        webbrowser.open(url)
        console.note(f"opening {args.site}/view for: {', '.join(labels)}")
    return 0


def _cmd_eval_list(args: argparse.Namespace) -> int:
    """List recent eval runs (newest first) so you can `view` one."""
    from rich.table import Table

    runs = state.recent_runs()
    if not runs:
        console.note("no recent eval runs — run `avp eval run <config>` first.")
        return 0
    table = Table(title="recent eval runs", header_style="bold")
    table.add_column("id", style=f"bold {brand.SAIL}", no_wrap=True)
    table.add_column("when")
    table.add_column("dataset")
    table.add_column("agents")
    table.add_column("commissions", justify="right")
    for r in runs:
        when = r.get("ts", "")[:19].replace("T", " ")
        table.add_row(
            r.get("id", "?"),
            when,
            r.get("dataset", "?"),
            ", ".join(r.get("agents", [])),
            str(len(r.get("commissions", []))),
        )
    console.out.print(table)
    console.note("view one:  avp eval view <id>   (no arg opens the most recent)")
    return 0


def _resolve_run_id(args: argparse.Namespace) -> str:
    """This run's voyage id: `--name`, else an interactive prompt, else autogenerated."""
    if args.name:
        return state.claim_id(args.name)
    if not args.quiet and sys.stdin.isatty() and console.err.is_terminal:
        answer = questionary.text(
            "Name this voyage (blank to autogenerate):",
            qmark=brand.SAILBOAT,
            style=_PICKER_STYLE,
        ).ask()
        if answer and answer.strip():
            return state.claim_id(answer)
    return state.new_id()


def _cmd_eval_delete(args: argparse.Namespace) -> int:
    """Delete one recorded run by id, or every run with `--all`."""
    if args.all:
        n = state.clear_runs()
        console.note(f"deleted {n} run{'s' if n != 1 else ''} from {paths.runs_dir()}")
        return 0
    if not args.name:
        console.error_panel(
            "nothing to delete",
            "name a run to delete (a voyage id from `avp eval list`), or pass --all "
            "to delete every recorded run.",
        )
        return 1
    if not state.delete_run(args.name):
        console.error_panel(
            f"no run {args.name!r}", "no recorded run with that id — see `avp eval list`."
        )
        return 1
    console.note(f"deleted run {args.name}")
    return 0


def _resolve_resume_dir(args: argparse.Namespace) -> Path | None:
    """The output dir of the run `--resume` names: an explicit `--out`, the run's
    recorded dir, or the default `<runs>/<id>`. Errors (returns None) if none exist
    on disk, since there'd be nothing to resume."""
    candidates = []
    if args.out:
        candidates.append(Path(args.out))
    rec = state.find_run(args.resume)
    if rec:
        candidates.append(Path(rec["out_dir"]))
    candidates.append(_default_out_dir() / args.resume)
    for c in candidates:
        if c.is_dir():
            return c
    console.error_panel(
        f"can't resume {args.resume!r}",
        "no run dir found. Pass an id from `avp eval list`, or `--out <dir>` "
        "pointing at the run's trajectories.",
    )
    return None


def _resume_drift(out: Path, ev: Eval) -> str | None:
    """Why resuming `out` with the current eval would be unsafe, or None if it's
    consistent. Splicing a different config into an old run dir would build one
    board from two different evals; the run manifest is the source of truth for
    what originally ran."""
    mani = run_manifest.read(out)
    if not mani:
        return None  # older run without a manifest: trust the caller
    was = set(mani.get("commissions", {}))
    now = {s.id for s in ev.setups}
    if was and was != now:
        return (
            f"this run's commissions were {sorted(was)}, but the config now has "
            f"{sorted(now)}. Resume the original config, or start a fresh run."
        )
    return None


def _cmd_eval(args: argparse.Namespace) -> int:
    if args.eval_cmd == "view":
        return _cmd_eval_view(args)
    if args.eval_cmd == "list":
        return _cmd_eval_list(args)
    if args.eval_cmd == "delete":
        return _cmd_eval_delete(args)
    try:
        ev = config.load_eval(args.path)
    except config.EvalConfigError as exc:
        console.error_panel("bad eval config", str(exc))
        return 1

    if args.threshold is not None and hasattr(ev.scorer, "threshold"):
        ev.scorer.threshold = args.threshold
    # One voyage per run: a default run lands in its own subdir (so runs don't
    # clobber each other and each has a stable home `view <id>` resolves to); an
    # explicit --out is taken literally.
    if args.resume:
        run_id = args.resume
        out = _resolve_resume_dir(args)
        if out is None:
            return 1
        drift = _resume_drift(out, ev)
        if drift is not None:
            console.error_panel("can't resume: config changed", drift)
            return 1
        console.note(f"resuming {run_id}: reusing finished cells in {_tilde(out)}")
    else:
        run_id = _resolve_run_id(args)
        out = Path(args.out) if args.out else _default_out_dir() / run_id
    # Bring up the sandbox stack once (not per cell): Docker preflight, the
    # managed server, and the seeded run workspace every cell mounts.
    try:
        env_obj, sandbox_ctx = _prepare_sandbox(
            args.env,
            _workspace_root(out, run_id),
            runtime_name=runtime.resolve_runtime_name(args.runtime),
        )
    except osb.SandboxUnavailable as exc:
        console.error_panel("sandbox unavailable", str(exc))
        return _SKIP
    except Exception as exc:
        console.error_panel(f"environment '{args.env}'", str(exc))
        return 1
    if args.env:
        console.note(f"environment: {args.env} → {_tilde(sandbox_ctx.workspace)}")
    if args.agent:
        agent_specs = [s.strip() for s in args.agent.split(",") if s.strip()]
    else:
        agent_specs = ev.agents or [DEFAULT_AGENT]
    return _run_and_report(
        ev,
        run_id=run_id,
        agent_specs=agent_specs,
        out=out,
        json_path=args.json_path,
        max_items=args.max_items,
        model=args.model,
        quiet=args.quiet,
        sandbox_ctx=sandbox_ctx,
        env_obj=env_obj,
        config_path=args.path,
        timeout_s=args.timeout,
        resume=bool(args.resume),
    )


def _resolve_env_file(spec: str) -> Path:
    """An env spec is a path to a JSON file, or a name in ~/.avp/environments."""
    from avp_cli import environment as env_mod

    p = Path(spec)
    if p.is_file():
        return p
    named = paths.environments_dir() / f"{spec}.json"
    if named.is_file():
        return named
    raise env_mod.EnvError(
        f"not a file, and no environment named {spec!r} in {_tilde(paths.environments_dir())}"
    )


# ── env ───────────────────────────────────────────────────────────────────────


def _task_event(ev) -> None:
    """Compact live progress for a single task run: one line per tool call + stop."""
    from avp.trajectory import AgentStoppedEvent, ToolInvokedEvent

    if isinstance(ev, ToolInvokedEvent):
        console.note(f"  ⚒ {ev.data.tool_name}")
    elif isinstance(ev, AgentStoppedEvent):
        console.note(f"  ■ {ev.data.reason}")


def _cmd_run(args: argparse.Namespace) -> int:
    """Commission one agent to do one task, optionally inside an environment.

    The task is the Commission prompt; the env (if given) supplies the working
    context (code via `paths`, fixtures via `files`, a runtime). The workspace
    persists so you can inspect what the agent changed.
    """
    from avp.commission import Commission
    from avp_cli.agent import run_agent
    from avp_cli.eval.engine import extract_final_output
    from avp_cli.observability import summarize

    agent = resolve_agent(args.agent)
    run_id = state.new_id()
    rundir = paths.runs_dir() / run_id
    rundir.mkdir(parents=True, exist_ok=True)

    try:
        env_obj, sandbox_ctx = _prepare_sandbox(
            args.env, rundir, runtime_name=runtime.resolve_runtime_name(args.runtime)
        )
    except osb.SandboxUnavailable as exc:
        console.error_panel("sandbox unavailable", str(exc))
        return _SKIP
    except Exception as exc:
        console.error_panel(f"environment '{args.env}'", str(exc))
        return 1
    prepared = _prepare_agent(agent, env_obj, quiet=False, runtime_name=sandbox_ctx.runtime)
    if prepared is None:
        return _SKIP

    if not args.model or "/" not in args.model:
        console.error_panel(
            "model must be a provider/model slug",
            f"got {args.model!r}; pass e.g. --model anthropic/claude-opus-4-8 "
            "or openai/gpt-4o (canonical models.dev namespace).",
        )
        return 1

    commission = Commission(
        schema_version="0.1", run_id=run_id, prompt=args.prompt, model=args.model
    )
    if local_models.is_local(commission):
        try:
            local_models.provision(commission.model, notify=console.note)
        except local_models.LocalModelError as exc:
            console.error_panel("local model", str(exc))
            return 1
    traj = rundir / "trajectory.ndjson"
    where = f" in {args.env}" if args.env else ""
    console.note(f"{agent.name} working on the task{where} …")
    events, err = run_agent(
        prepared,
        sandbox_ctx,
        commission,
        out_path=traj,
        timeout_s=args.timeout,
        on_event=_task_event,
    )
    if err is not None or events is None:
        console.error_panel(f"'{agent.name}' run failed", err or "no events")
        return 1

    summary = summarize(events)
    final = extract_final_output(events)
    console.out.print()
    if summary:
        tally = f"  {tool_tally(summary)}" if tool_tally(summary) else ""
        console.out.print(
            f"[bold {brand.SAIL}]done[/]  {summary.total_turns} turns · "
            f"${summary.total_cost_usd:.4f}{tally}"
        )
    if final.text:
        console.out.print(final.text.strip())
    console.note(f"trajectory: {_tilde(traj)}")
    console.note(f"workspace (inspect what changed): {_tilde(sandbox_ctx.workspace)}")
    return 0


def _cmd_env(args: argparse.Namespace) -> int:
    if args.env_cmd == "list":
        return _cmd_env_list()
    if args.env_cmd == "create":
        return _cmd_env_create(args)
    if args.env_cmd == "show":
        return _cmd_env_show(args.env)
    if args.env_cmd == "delete":
        return _cmd_env_delete(args.name)
    if args.env_cmd == "secret":
        return _cmd_env_secret(args)
    return _cmd_env_run(args)


def _cmd_env_secret(args: argparse.Namespace) -> int:
    """Manage the vault: secrets a Commission references by handle. The value is
    stored on the host (~/.avp/secrets.toml, 0600) and injected by the broker at
    run time, so it never enters the sandbox or the wire."""
    from avp_cli import vault

    if args.secret_cmd == "list":
        handles = vault.names()
        if not handles:
            console.note(f"no secrets stored ({_tilde(vault.secrets_path())})")
            return 0
        for handle in handles:
            console.out.print(handle)
        return 0
    if args.secret_cmd == "delete":
        if vault.remove(args.handle):
            console.note(f"removed {args.handle!r}")
            return 0
        console.error_panel("no such secret", f"{args.handle!r} is not in the vault")
        return 1
    # create
    if args.handle in vault.names() and not args.force:
        console.error_panel(
            f"secret {args.handle!r} already exists",
            "pass --force to overwrite, or pick another handle.",
        )
        return 1
    value = args.value
    if value is None:
        import getpass

        value = getpass.getpass(f"value for {args.handle!r}: ")
    try:
        vault.store(args.handle, value)
    except vault.VaultError as exc:
        console.error_panel("could not store secret", str(exc))
        return 1
    console.note(
        f'stored {args.handle!r} — reference it in a Commission as {{"vault": "{args.handle}"}}'
    )
    return 0


def _cmd_env_create(args: argparse.Namespace) -> int:
    """Write an environment to ~/.avp/environments/<name>.json from flags."""
    from avp_cli import environment as env_mod

    if not _ID_RE.match(args.name):
        console.error_panel(
            "invalid environment name", f"{args.name!r}: use lowercase letters, digits, '-', '_'."
        )
        return 1
    dest = paths.environments_dir() / f"{args.name}.json"
    if dest.exists() and not args.force:
        console.error_panel(
            f"environment {args.name!r} already exists",
            f"in {_tilde(paths.environments_dir())} — pass --force, or pick another name.",
        )
        return 1
    # Resolve --path to absolute now (so it still resolves when materialized from
    # ~/.avp later) and fail early if it's missing.
    abs_paths = []
    for p in args.path or ():
        rp = Path(p)
        if not rp.exists():
            console.error_panel("path not found", f"{p!r} does not exist")
            return 1
        abs_paths.append(str(rp.resolve()))
    try:
        block = env_mod.build_block(
            image=args.image,
            apt=tuple(args.apt or ()),
            pip=tuple(args.pip or ()),
            paths=tuple(abs_paths),
            files=tuple(args.file or ()),
            setup=tuple(args.setup or ()),
            net=tuple(args.net or ()),
            cpu=args.cpu,
            memory=args.memory,
        )
    except env_mod.EnvError as exc:
        console.error_panel("can't build that environment", str(exc))
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(block, indent=2) + "\n")
    console.out.print(
        f"[green]✓[/] created environment [bold {brand.SAIL}]{args.name}[/] → {_tilde(dest)}"
    )
    console.note(f"avp env show {args.name}   ·   avp env run {args.name} -- <command>")
    return 0


def _cmd_env_delete(name: str) -> int:
    """Remove an environment from ~/.avp/environments."""
    dest = paths.environments_dir() / f"{name}.json"
    if not dest.is_file():
        console.error_panel(
            f"no environment {name!r}", f"nothing at {_tilde(dest)} — see `avp env list`."
        )
        return 1
    dest.unlink()
    console.note(f"deleted environment {name}")
    return 0


def _cmd_env_list() -> int:
    """List named environments in ~/.avp/environments."""
    from rich.table import Table

    from avp_cli import environment as env_mod

    d = paths.environments_dir()
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        console.note(
            f"no environments in {_tilde(d)} — drop an env JSON there, "
            "or pass a path to `avp env show/run`."
        )
        return 0
    table = Table(title="environments", header_style="bold")
    table.add_column("name", style=f"bold {brand.SAIL}", no_wrap=True)
    table.add_column("image")
    table.add_column("packages")
    for f in files:
        try:
            e = env_mod.Environment.parse(json.loads(f.read_text()))
        except (env_mod.EnvError, json.JSONDecodeError, OSError):
            continue
        pkgs = ", ".join(f"{k}:{len(v)}" for k, v in e.packages.items())
        table.add_row(f.stem, e.image, pkgs or "[dim]—[/dim]")
    console.out.print(table)
    console.note("avp env show <name>   ·   avp env run <name> -- <command>")
    return 0


def _cmd_env_show(spec: str) -> int:
    """Render an environment without building it."""
    from avp_cli import environment as env_mod

    try:
        p = _resolve_env_file(spec)
        e = env_mod.Environment.parse(json.loads(p.read_text()))
    except (env_mod.EnvError, json.JSONDecodeError, OSError) as exc:
        console.error_panel(f"environment '{spec}'", str(exc))
        return 1
    console.out.print(f"[bold {brand.SAIL}]{spec}[/]  ·  {_tilde(p)}")
    console.out.print(f"  image: {e.image}")
    for eco, pkgs in e.packages.items():
        console.out.print(f"  {eco}: {', '.join(pkgs)}")
    if e.paths:
        console.out.print(f"  paths: {', '.join(e.paths)}")
    if e.files:
        console.out.print(f"  files: {', '.join(e.files)}")
    if e.setup:
        console.out.print(f"  setup: {len(e.setup)} command(s)")
    if e.net:
        console.out.print(f"  network: {', '.join(e.net)}")
    if e.resources:
        console.out.print("  resources: " + ", ".join(f"{k}={v}" for k, v in e.resources.items()))
    console.note(f"avp env run {spec} -- <command>   ·   run a command inside it")
    return 0


def _cmd_env_run(args: argparse.Namespace) -> int:
    """Run a command inside an environment's sandbox (image + workspace + egress).

    The same world an agent would get, minus the agent: the env's derived image
    (no agent recipe), the seeded workspace mounted rw, setup run, default-deny
    egress. The workspace persists under ~/.avp/runs for inspection.
    """
    import contextlib as _contextlib
    import shlex as _shlex
    from datetime import timedelta

    from opensandbox import SandboxSync
    from opensandbox.models.execd import RunCommandOpts
    from opensandbox.models.sandboxes import Host, Volume

    from avp_cli.agent import _WORKSPACE_MNT, _run_setup

    command = list(args.command)
    if command and command[0] == "--":  # argparse REMAINDER keeps the separator
        command = command[1:]
    if not command:
        console.error_panel("no command", "usage: avp env run <env> -- <command> ...")
        return 1

    run_id = state.new_id()
    rundir = paths.runs_dir() / run_id
    try:
        env_obj, ctx = _prepare_sandbox(args.env, rundir)
    except osb.SandboxUnavailable as exc:
        console.error_panel("sandbox unavailable", str(exc))
        return _SKIP
    except Exception as exc:
        console.error_panel(f"environment '{args.env}'", str(exc))
        return 1
    try:
        image = images.ensure_image(
            env_obj,
            images.ContainerRecipe(install=(), command=()),
            on_line=lambda line: console.err.print(
                line, style="dim", markup=False, highlight=False
            ),
        )
    except images.ImageBuildError as exc:
        console.error_panel(f"environment '{args.env}'", str(exc))
        return 1

    console.note(f"running in {_tilde(ctx.workspace)} (sandboxed)")
    try:
        box = SandboxSync.create(
            image,
            connection_config=ctx.connection.config(),
            volumes=[
                Volume(
                    name="workspace",
                    host=Host(path=str(ctx.workspace.resolve())),
                    mount_path=_WORKSPACE_MNT,
                )
            ],
            network_policy=osb.network_policy(ctx.net),
            resource=ctx.resources or None,
            timeout=timedelta(hours=1),
        )
    except Exception as exc:
        console.error_panel("sandbox create failed", str(exc))
        return 1
    try:
        err = _run_setup(box, ctx.setup)
        if err is not None:
            console.error_panel("setup failed", err)
            return 1
        execution = box.commands.run(
            _shlex.join(command),
            opts=RunCommandOpts(working_directory=_WORKSPACE_MNT, timeout=timedelta(hours=1)),
        )
        for log in execution.logs.stdout or []:
            console.out.print(log.text, end="", markup=False, highlight=False)
        for log in execution.logs.stderr or []:
            console.err.print(log.text, end="", markup=False, highlight=False)
        return execution.exit_code or 0
    finally:
        with _contextlib.suppress(Exception):
            box.kill()


def _cmd_sandbox(args: argparse.Namespace) -> int:
    if args.sandbox_cmd == "stop":
        if osb.stop_server():
            console.note("sandbox server stopped")
        else:
            console.note("no managed sandbox server is running")
        return 0
    status = osb.server_status()
    console.out.print(f"  docker: {status['docker']}")
    console.out.print(
        f"  config: {status['config']}" + ("" if status["configured"] else " (not yet generated)")
    )
    if "domain" in status:
        health = "healthy" if status.get("healthy") else "not running"
        console.out.print(f"  server: {status['domain']} ({health})")
        if status.get("sandboxes") is not None:
            console.out.print(f"  sandboxes: {status['sandboxes']}")
    return 0


# ── parser ─────────────────────────────────────────────────────────────────────


_RUNTIME_HELP = (
    "Sandbox backend. 'opensandbox' (default): the Docker-based managed server with "
    "DNS-filtered egress isolation. 'libkrun': a podman microVM (no Docker, lighter) "
    "that exposes the host GPU to the sandbox via virtio-gpu, so a local model "
    "(provider 'local') runs GPU-accelerated in-process. Use libkrun when you want fast, "
    "private, $0 local inference and have a krunkit machine; opensandbox otherwise. "
    "Falls back to $AVP_RUNTIME."
)


def _add_run_args(p: argparse.ArgumentParser, *, needs_path: bool) -> None:
    if needs_path:
        p.add_argument("path", help="Path to an eval config (.eval.json)")
    p.add_argument(
        "--agent",
        default=None,
        help=(
            f"Agent(s) to run, comma-separated. Known: {', '.join(known_agents())}, "
            "or a path to any agent's avp-conformance.json. One board per agent. "
            'Overrides the config\'s "agents"; falls back to that, then to '
            f"{DEFAULT_AGENT}."
        ),
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override the model every commission runs (e.g. claude-sonnet-4-6)",
    )
    p.add_argument("--runtime", choices=runtime.RUNTIMES, default=None, help=_RUNTIME_HELP)
    p.add_argument(
        "--name",
        default=None,
        help="Name this voyage (its id for `eval view`/`list`). Prompts if a TTY; else autogenerates.",
    )
    p.add_argument("--out", default=None, help="Directory for NDJSON trajectories")
    p.add_argument("--json", dest="json_path", default=None, help="Write a machine-readable board")
    p.add_argument(
        "--threshold", type=float, default=None, help="Override the scorer pass threshold"
    )
    p.add_argument(
        "--max-items", type=int, default=None, help="Cap items per commission (cost control)"
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Max seconds per run before it's recorded as an error (default: 300)",
    )
    p.add_argument(
        "--resume",
        metavar="RUN_ID",
        default=None,
        help="Resume a run by id: reuse cells whose trajectory finished, re-run the rest",
    )
    p.add_argument(
        "--env",
        default=None,
        help="Run agents inside a declarative environment (a path to an env JSON, or a name "
        "in ~/.avp/environments). Defines the sandbox image, workspace, and egress.",
    )
    p.add_argument("--quiet", action="store_true", help="Suppress per-run progress on stderr")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="avp", description="The local AVP CLI.")
    groups = parser.add_subparsers(dest="group")  # not required: no args -> WELCOME

    p_init = groups.add_parser("init", help="Scaffold an eval config from the catalog")
    p_init.add_argument(
        "key", nargs="?", default=None, help="Catalog key (omit to pick interactively)"
    )
    p_init.add_argument("--dir", default=".", help="Directory to write the config into")
    p_init.add_argument(
        "--agent",
        default=None,
        help=(
            f"Agent(s) to pin in the config, comma-separated. Known: {', '.join(known_agents())}. "
            "Omit to pick interactively."
        ),
    )

    eval_p = groups.add_parser("eval", help="Run and compare Commission setups")
    esub = eval_p.add_subparsers(dest="eval_cmd", required=True)
    _add_run_args(
        esub.add_parser("run", help="Run an eval config and print the board"), needs_path=True
    )
    esub.add_parser("list", help="List recent eval runs (newest first)")
    p_del = esub.add_parser("delete", help="Delete one recorded run by id (or --all for every run)")
    p_del.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="ID",
        help="Voyage id of the run to delete (from `avp eval list`)",
    )
    p_del.add_argument(
        "--all",
        action="store_true",
        help="Delete every recorded run + its outputs (~/.avp/runs)",
    )

    p_view = esub.add_parser(
        "view", help="Open a finished eval on agentvoyagerproject.com (encodes it into the URL)"
    )
    p_view.add_argument(
        "path",
        nargs="?",
        default=None,
        metavar="ID",
        help="A voyage id from `avp eval list` (or a trajectories.json / out dir). "
        "Default: the most recent run.",
    )
    p_view.add_argument(
        "--agent",
        default=None,
        help="Open only this agent's trajectories (default: all in the run)",
    )
    p_view.add_argument("--site", default=viz.SITE, help="Viewer base URL (override for dev)")
    p_view.add_argument(
        "--no-open", action="store_true", help="Print the URL(s), don't open a browser"
    )

    com_p = groups.add_parser("cm", help="Build and inspect commissions in your library")
    csub = com_p.add_subparsers(dest="commission_cmd", required=True)
    p_create = csub.add_parser(
        "create",
        help="Generate a complete commission into your library (then edit the JSON)",
    )
    p_create.add_argument("id", help="Commission id (becomes <id>.json in your library)")
    p_create.add_argument(
        "--agent",
        default=None,
        help=f"Generate against this agent ({', '.join(known_agents())}, or a manifest path): "
        "enumerates its full tool/skill/subagent/MCP surface into the per-agent "
        "enabled_builtin_* maps and pins agent_versions. Edit the file to restrict.",
    )
    p_create.add_argument(
        "--model",
        default=None,
        help="Model slug, e.g. anthropic/claude-opus-4-8 (default: the agent's, "
        "else a cheap runnable sample)",
    )
    p_create.add_argument(
        "--from",
        dest="from_id",
        default=None,
        metavar="ID",
        help="Clone an existing library commission as the base instead of generating "
        "(carries its output_schema, mcp_servers, skills).",
    )
    p_create.add_argument(
        "--provider-id",
        dest="provider_id",
        default=None,
        metavar="ID",
        help="Provider/storefront id (e.g. anthropic, openrouter); sets the provider block",
    )
    p_create.add_argument(
        "--provider-base-url",
        dest="provider_base_url",
        default=None,
        metavar="URL",
        help="Provider endpoint override (requires --provider-id)",
    )
    p_create.add_argument(
        "--credential",
        dest="credential",
        default=None,
        metavar="HANDLE",
        help="Vault handle for the provider key (a SecretRef; see `avp env secret create`)",
    )
    p_create.add_argument(
        "--force", action="store_true", help="Overwrite an existing commission with this id"
    )
    csub.add_parser("list", help="List the commissions in your library (~/.avp/commissions)")
    p_describe = csub.add_parser(
        "describe",
        help="Describe a library commission (the raw wire Commission) by id, or a Commission file",
    )
    p_describe.add_argument(
        "id", help="A commission id from your library (or a Commission .json file)"
    )
    p_check = csub.add_parser("check", help="Check a library commission by id or path")
    p_check.add_argument(
        "target", help="A commission id from your library, or a path to a Commission .json file"
    )
    p_cdel = csub.add_parser("delete", help="Delete a commission from your library by id")
    p_cdel.add_argument("id", help="A commission id from your library")

    agent_p = groups.add_parser("agent", help="Install and inspect the agents you can run against")
    asub = agent_p.add_subparsers(dest="agent_cmd", required=True)
    asub.add_parser("list", help="List known agents, whether each is installed and ready")
    p_adesc = asub.add_parser(
        "describe", help="Print an agent's AgentDescriptor (its tools, models, skills, MCP)"
    )
    p_adesc.add_argument(
        "name", help=f"Agent name ({', '.join(known_agents())}) or a path to a manifest"
    )
    p_adesc.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Print the raw AgentDescriptor JSON (full tool input schemas)",
    )

    p_ainstall = asub.add_parser(
        "install", help="Install a prebuilt agent (from a GitHub release, or local artifacts)"
    )
    p_ainstall.add_argument("name", help=f"Agent to install ({', '.join(known_agents())})")
    p_ainstall.add_argument(
        "--version", default=None, help="Release version to install (e.g. 0.0.1). Default: latest."
    )
    p_ainstall.add_argument(
        "--binary",
        default=None,
        metavar="PATH",
        help="Install a binary agent from this local executable, skipping the release "
        "(the local-package dev loop).",
    )
    p_ainstall.add_argument(
        "--wheel",
        action="append",
        metavar="WHL",
        help="Install a Python agent from local wheel(s), skipping the release (repeatable).",
    )
    p_ainstall.add_argument(
        "--force", action="store_true", help="Reinstall over an existing install"
    )

    p_auninstall = asub.add_parser("uninstall", help="Remove an installed agent")
    p_auninstall.add_argument("name", help="Installed agent name")

    run_p = groups.add_parser(
        "run", help="Commission an agent to do a task, optionally inside an environment"
    )
    run_p.add_argument("prompt", help="The task for the agent")
    run_p.add_argument(
        "--agent",
        required=True,
        help=f"Agent to run ({', '.join(known_agents())}, or a manifest path)",
    )
    run_p.add_argument(
        "--env", default=None, help="Environment to run inside (a name or a path to an env JSON)"
    )
    run_p.add_argument("--model", default=None, help="Model override (else the agent's default)")
    run_p.add_argument("--runtime", choices=runtime.RUNTIMES, default=None, help=_RUNTIME_HELP)
    run_p.add_argument(
        "--timeout", type=float, default=600.0, help="Max seconds for the run (default: 600)"
    )

    env_p = groups.add_parser(
        "env", help="Define + run agent environments (a container image + workspace + egress)"
    )
    ensub = env_p.add_subparsers(dest="env_cmd", required=True)
    ensub.add_parser("list", help="List named environments (~/.avp/environments)")
    p_ecreate = ensub.add_parser("create", help="Create an environment in your library")
    p_ecreate.add_argument("name", help="Environment name (becomes <name>.json)")
    p_ecreate.add_argument(
        "--image",
        default=None,
        metavar="IMAGE",
        help="Base container image (default: python:3.12-slim)",
    )
    p_ecreate.add_argument("--apt", action="append", metavar="PKG", help="apt package (repeatable)")
    p_ecreate.add_argument("--pip", action="append", metavar="PKG", help="pip package (repeatable)")
    p_ecreate.add_argument(
        "--path",
        action="append",
        metavar="SRC",
        help="Copy a local file or directory into the env workspace (repeatable). "
        "Re-copied each run, so edits to SRC are picked up.",
    )
    p_ecreate.add_argument(
        "--file",
        action="append",
        metavar="PATH=SRC",
        help="Seed a file: PATH=inline-content, or PATH=@localfile (repeatable)",
    )
    p_ecreate.add_argument(
        "--setup",
        action="append",
        metavar="CMD",
        help="Command run in the sandbox workspace before the agent (repeatable)",
    )
    p_ecreate.add_argument(
        "--net", action="append", metavar="DOMAIN", help="Allowed egress domain (repeatable)"
    )
    p_ecreate.add_argument("--cpu", default=None, metavar="N", help='CPU cap (e.g. "2")')
    p_ecreate.add_argument("--memory", default=None, metavar="SIZE", help='Memory cap (e.g. "4Gi")')
    p_ecreate.add_argument("--force", action="store_true", help="Overwrite an existing environment")
    p_eshow = ensub.add_parser("show", help="Show an environment (a name or a path to an env JSON)")
    p_eshow.add_argument("env", help="Environment name (in ~/.avp/environments) or a path")
    p_erun = ensub.add_parser("run", help="Run a command inside an environment's sandbox")
    p_erun.add_argument("env", help="Environment name or path to an env JSON")
    p_erun.add_argument(
        "command", nargs=argparse.REMAINDER, help="Command to run inside the env, after `--`"
    )
    p_edel = ensub.add_parser("delete", help="Delete an environment from your library")
    p_edel.add_argument("name", help="Environment name")

    # Secrets a Commission references by handle ({"vault": "<handle>"}). Stored
    # in ~/.avp/secrets.toml (0600); the credential broker injects the value at
    # run time so it never enters the sandbox.
    p_secret = ensub.add_parser(
        "secret", help="Store credentials a Commission references by vault handle"
    )
    secsub = p_secret.add_subparsers(dest="secret_cmd", required=True)
    p_secset = secsub.add_parser("create", help="Store a secret by handle")
    p_secset.add_argument("handle", help='Vault handle (a Commission\'s {"vault": <handle>})')
    p_secset.add_argument(
        "value",
        nargs="?",
        default=None,
        help="The secret value. Omit to be prompted (keeps it out of shell history).",
    )
    p_secset.add_argument("--force", action="store_true", help="Overwrite an existing secret")
    secsub.add_parser("list", help="List stored handles (never the values)")
    p_secrm = secsub.add_parser("delete", help="Delete a stored secret by handle")
    p_secrm.add_argument("handle", help="Vault handle to delete")

    sandbox_p = groups.add_parser("sandbox", help="The managed sandbox server (OpenSandbox)")
    ssub = sandbox_p.add_subparsers(dest="sandbox_cmd", required=True)
    ssub.add_parser("status", help="Docker + server health, config path, live sandbox count")
    ssub.add_parser("stop", help="Stop the managed sandbox server")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.group is None:
        console.out.print(brand.logo())
        console.out.print()
        console.out.print(welcome())
        return 0
    if args.group == "init":
        return _cmd_init(args)
    if args.group == "eval":
        return _cmd_eval(args)
    if args.group == "cm":
        return _cmd_commission(args)
    if args.group == "agent":
        return _cmd_agent(args)
    if args.group == "env":
        return _cmd_env(args)
    if args.group == "run":
        return _cmd_run(args)
    if args.group == "sandbox":
        return _cmd_sandbox(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
