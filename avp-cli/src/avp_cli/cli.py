"""`avp` - the local AVP CLI for building, running, and iterating on Commissions.

    avp                              getting-started + agent routing (no args)
    avp init [KEY] [--dir D]         scaffold an eval (in place) + its commissions (to ~/.avp)
    avp eval run CONFIG              run an eval config, print a ranked board
    avp eval list                    list recent eval runs (with their ids)
    avp eval view [ID]               open an eval on agentvoyagerproject.com (default: most recent)
    avp eval delete ID [--all]       delete one recorded run by id (or --all for every run)
    avp commission list              list your portable commission library
    avp commission describe ID       render a library commission by id
    avp commission check ID|FILE     check a library commission, or a Commission JSON file
    avp commission delete ID         remove a commission from your library

An eval is a JSON config file authored in place (no code); commissions are
portable artifacts in ~/.avp/commissions referenced by id. The CLI is the engine.
The agent supplies its own credentials from the environment. When no agent's
toolchain is present a run exits 2 (a preflight skip).
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

import questionary

from avp_cli import brand, catalog, config, console, library, live, paths, run_manifest, state, viz
from avp_cli import commission as commission_mod
from avp_cli.agents import DEFAULT_AGENT, known_agents, preflight, resolve_agent
from avp_cli.eval.engine import Eval, RunObserver, RunResult, run_matrix, setups_for
from avp_cli.eval.report import board_table, comparison_table, dump_json, failures
from avp_cli.observability import tool_tally
from avp_cli.onboarding import welcome

_SKIP = 2  # no agent toolchain present; skip cleanly rather than error

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
    config_path: str | None = None,
) -> int:
    runnable = []
    for spec in agent_specs:
        agent = resolve_agent(spec)
        reason = preflight(agent.name)
        if reason is not None:
            console.warn(f"skipping agent '{agent.name}': {reason}")
        else:
            runnable.append(agent)
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
                out_dir=out,
                max_items=max_items,
                model=model,
                observer=vl.observer(),
                compare=compare,
            )
    else:
        observer = None if quiet else _note_observer(total, compare=compare)
        boards = run_matrix(
            ev,
            runnable,
            out_dir=out,
            max_items=max_items,
            model=model,
            observer=observer,
            compare=compare,
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
        f"view it: [bold]uv run avp eval view {run_id}[/bold]"
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
    body.append(f"\nnext:\n  uv run avp eval run {target.name}")
    console.panel(entry.title, "\n".join(body), style="green")
    return 0


# ── commission ────────────────────────────────────────────────────────────────


def _cmd_commission(args: argparse.Namespace) -> int:
    if args.commission_cmd == "list":
        return _cmd_commission_list()
    if args.commission_cmd == "check":
        return _cmd_commission_validate(args.target)
    if args.commission_cmd == "delete":
        if not library.delete(args.id):
            console.error_panel(
                f"no commission {args.id!r}",
                f"not in your library ({_tilde(paths.commissions_dir())}) — see `avp commission list`.",
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
            f"not a library id (see `avp commission list`) nor a readable Commission file: {exc}",
        )
        return 1
    console.print_json(commission_mod.full_dict(c))
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
            "not a library id (see `avp commission list`) nor a path to a Commission .json file.",
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
    console.note("avp commission describe <id>  ·  see the full Commission")
    return 0


# ── agent ───────────────────────────────────────────────────────────────────────


def _cmd_agent(args: argparse.Namespace) -> int:
    if args.agent_cmd == "list":
        return _cmd_agent_list()
    return _cmd_agent_describe(args.name, json_out=args.json_out)


def _cmd_agent_list() -> int:
    """List known agents and whether their local toolchain is ready."""
    from rich.table import Table

    table = Table(title="agents", header_style="bold")
    table.add_column("name", style=f"bold {brand.SAIL}", no_wrap=True)
    table.add_column("status")
    table.add_column("command", overflow="fold", style="dim")
    for name in known_agents():
        agent = resolve_agent(name)
        reason = preflight(name)
        status = "[green]ready[/]" if reason is None else f"[yellow]{reason}[/yellow]"
        table.add_row(name, status, " ".join(agent.manifest.command))
    console.out.print(table)
    console.note("avp agent describe <name>  ·  see its tools, models, skills")
    return 0


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
    console.note("view one:  uv run avp eval view <id>   (no arg opens the most recent)")
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
    run_id = _resolve_run_id(args)
    out = Path(args.out) if args.out else _default_out_dir() / run_id
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
        config_path=args.path,
    )


# ── parser ─────────────────────────────────────────────────────────────────────


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

    com_p = groups.add_parser("commission", help="Build and inspect commissions in your library")
    csub = com_p.add_subparsers(dest="commission_cmd", required=True)
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

    agent_p = groups.add_parser("agent", help="Inspect the agents you can run against")
    asub = agent_p.add_subparsers(dest="agent_cmd", required=True)
    asub.add_parser("list", help="List known agents and whether their toolchain is ready")
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
    if args.group == "commission":
        return _cmd_commission(args)
    if args.group == "agent":
        return _cmd_agent(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
