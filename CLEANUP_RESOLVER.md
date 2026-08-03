# Cleanup: remove the Resolver API from v0.1 surfaces

The Resolver API was removed from v0.1 in `3cedc6b` ("rm resolver in v0.1",
2026-05-20). That commit deleted `spec/v0.1/resolver.md`, the
`Commission.subagents` field, and the ref-based indirection on
`mcp_servers` / `skills`. It did not sweep the prose, the schema-generator
descriptions, or the package metadata.

**Current shape, for reference when rewriting.** `Commission.mcp_servers[]`
carries inline connection material (`McpServerHttp` with `url` / `headers` /
`auth`, or `McpServerStdio` with `command` / `args` / `env`).
`Commission.skills[]` carries inline content (`files`: relative path to file
content). There is no `subagents` field and no `ref` field anywhere.
Credentials are the only indirection left: `SecretRef` (`{"vault": "<handle>"}`)
on `provider.credential` and `McpServerHttp.auth`. v0.1 has no two-party wire
protocol at all.

Subagents are a related trap: `subagent_invoked` / `subagent_returned` still
exist, but v0.1 subagents are in-process frames on the parent's trajectory.
`avp.subagent.run_id` is reserved for a future revision and is absent for
in-process subagents ([trajectory.py:301](avp/bindings/python/src/avp/trajectory.py#L301)).
Any prose describing a child run "the supervisor commissions independently"
is wrong for the same reason.

Delete this file when the checklist is done.

## Done

- [x] `CLAUDE.md`: spec list, the "built on" bullets (JSON-RPC row dropped,
      MCP / Agent Skills reworded to inline), the `resolver.md` reference in
      "Things you should not do", "four normative specs" to three, the
      `avp/bindings/python/` entry that claimed a resolver client, and the
      `FOUNDATIONS.md` summary line.
- [x] `FOUNDATIONS.md`: opening thesis, stack diagram, the whole "JSON-RPC 2.0
      (the AVP Resolver API)" section, MCP + Agent Skills sections, "no mid-run
      reach-in", the `Commission` example (was entirely `{id, ref}` shaped and
      included the dropped `subagents` field), philosophy bullets, "what AVP
      does NOT define", the ATIF subagent row, and the versioning list. Also
      fixed the stale `spec/v0.1/...` link paths and the subagent claim.
- [x] The "no resolver round-trip" trim pass (see the decision below): five
      prose / docstring sites plus the two hand-written binding headers.
      `avp/bindings/{rust,typescript}/src/` is now free of the word entirely.

## Prose and metadata

- [x] `README.md` (done: diagram is two flows, JSON-RPC clause dropped and
      MCP / Agent Skills reworded to the inline material a Commission carries,
      Resolver row removed from the spec table, "Four specs" to "Three specs"
      with the two-party-wire-protocol sentence replaced by "All three are
      data-shape specs and compose independently"). `grep -in
      "resolver\|avp\.resolve\|subagent\|json-rpc"` over `README.md` is clean.
- [x] `SKILL.md` (done: Resolver bullet dropped, "four specs" to three in both
      the intro and the reading-order list, the "RPC payloads are JSON-RPC 2.0"
      clause replaced with the Agent Skills anchor that was missing from that
      sentence, and the `resolver.md` routing entry removed). No regeneration
      needed: `avp/scripts/build-skill.sh` copies `SKILL.md` into the bundle
      verbatim, it does not derive it. `grep -in
      "resolver\|json-rpc\|four spec"` over `SKILL.md` is clean.
- [x] `MAINTAINERS.md` (done: both areas-of-responsibility entries had the
      resolver item dropped and nothing put in its place. The remaining
      responsibilities on both rows still describe real surfaces, so no
      reassignment was invented. If the infrastructure row should name the
      sandbox / container stack the CLI manages, that is a call for the
      maintainers, not this sweep.)
- [x] `proposals/` (done: "a new resolver method" is now "a new Commission
      field" in the opening AVP-RFC definition, "new Resolver API methods"
      dropped from the wire-format bullet, and "The four specs" is three with
      the dead `resolver.md` link removed. Two extras the checklist missed,
      both found by grepping the whole directory rather than the one file:
      `proposals/NNNN-template/metadata.yaml` listed `resolver` as a valid
      `specs:` value in both the comment and the commented-out example, so
      every future AVP-RFC copied from the template would have carried it;
      and the "you do not need an AVP-RFC for" bullet said `spec/v0.1/`,
      a path that predates the move to `avp/core/spec/v0.1/`.)
- [x] `avp/bindings/python/CLAUDE.md` (done: the in-scope "Resolver client +
      worked sample" bullet and the out-of-scope "Multi-class resolver
      server/client abstractions" bullet both deleted.)
- [x] `avp/bindings/python/README.md` (done, and it was not just the word.
      The whole `src/avp/archive/` paragraph was stale: that directory was
      deleted in `bba4ee9` (2026-06-02), so the "do NOT import from it"
      warning pointed at nothing. Removed the paragraph and the `archive/`
      line from the package-layout block.)
- [x] [`avp/bindings/python/pyproject.toml`:13](avp/bindings/python/pyproject.toml#L13)
      (done: `description` is now "wire types (Pydantic source of truth) and
      event sinks", matching what the package actually ships.)

**Stale `Spec` URLs, fixed in passing.** The same pyproject carried
`Spec = ".../tree/main/spec/v0.1"`, a 404 since the move to
`avp/core/spec/v0.1/`. Not a resolver hit, but it was one line away from one.
The identical dead URL was in `avp-cli/pyproject.toml` and
`agents/avp-claude-agent-sdk/python/pyproject.toml`; all three now point at
`tree/main/avp/core/spec/v0.1`. `avp-cli` is the published dist, so that one
was reaching PyPI.

## Generated artifacts

These are the only hits that ship in machine-readable form. Fix the generator,
never the output.

- [ ] [`avp/scripts/generate-schemas.py`:79](avp/scripts/generate-schemas.py#L79)
      the `Commission` description: "supervisor-managed assets (mcp_servers,
      skills, subagents) as opaque `{id, ref}` pairs the agent dereferences via
      the AVP Resolver API at startup". Wrong on three counts (refs, the
      resolver, and the dropped `subagents` field).
- [ ] [`avp/scripts/generate-schemas.py`:150](avp/scripts/generate-schemas.py#L150)
      the umbrella bundle description lists "JSON-RPC 2.0 (Resolver API)" among
      what AVP is built on.
- [ ] [`avp/bindings/python/src/avp/descriptor.py`:25](avp/bindings/python/src/avp/descriptor.py#L25)
      module docstring: "Trajectory / Commission / Resolver API types."
- [ ] Re-run `make schemas` after the three edits above. Confirm
      [`commission.schema.json`:232](avp/core/spec/v0.1/commission.schema.json#L232)
      and [`avp.schema.json`:5](avp/core/spec/v0.1/avp.schema.json#L5) pick up
      the new text. Neither has changed yet: the trim pass regen only moved the
      `Commission` description embedded in `trajectory.schema.json`, which comes
      from the `commission.py` docstring, not from these two overrides.
- [ ] Re-run `avp/scripts/generate-bindings.sh` after that.

**Toolchain note.** `cargo-typify` was not installed on this machine and the
script hard-fails on the missing prerequisite. It is now installed
(`cargo install cargo-typify`). The trim-pass regeneration touched only
`trajectory.rs` and `trajectory.ts`, so the installed version matches whatever
generated the committed bindings; no version-churn cleanup needed.

## "No resolver round-trip" clauses (resolved: trim them)

**Decision:** trim. The resolver was never released, so a v0.1 reader has
never encountered it. Explaining its absence is verbose and confusing, not
helpful. State what the Commission does carry; say nothing about what it
doesn't. This applies to any new prose too: do not write "no resolver
round-trip" as a contrast anywhere.

- [x] [`avp/core/spec/v0.1/commission.md`:140](avp/core/spec/v0.1/commission.md#L140)
- [x] [`avp/core/spec/v0.1/trajectory.md`:196](avp/core/spec/v0.1/trajectory.md#L196)
- [x] [`avp/bindings/python/src/avp/commission.py`:155](avp/bindings/python/src/avp/commission.py#L155)
      (source of the generated Rust / TS comments; `make schemas` run)
- [x] [`PATTERNS.md`:44](PATTERNS.md#L44)
- [x] [`avp-cli/src/avp_cli/vault.py`:5](avp-cli/src/avp_cli/vault.py#L5)
      "This module is the supervisor's resolver" was the generic sense, not
      the AVP Resolver API, but the word collides. Now "the supervisor side
      of that lookup".
- [x] Hand-written binding headers, which the generator does not touch:
      [`rust/src/lib.rs`:25](avp/bindings/rust/src/lib.rs#L25) and
      [`typescript/src/index.ts`:27](avp/bindings/typescript/src/index.ts#L27).

## Leave alone

Historical records. Rewriting them would falsify the log.

- `agents/avp-claude-agent-sdk/python/src/avp_claude_agent_sdk/_commission.py`
  [:38](agents/avp-claude-agent-sdk/python/src/avp_claude_agent_sdk/_commission.py#L38)
  already states the removal correctly as history.
- `agents/avp-goose/rust/DESIGN.md` [:215-235](agents/avp-goose/rust/DESIGN.md#L215-L235)
  is a work log describing the removal as it happened.
- `avp/core/conformance/.../CONFORMANCE_PLAN.md` [:100](avp/core/conformance/src/avp_conformance/CONFORMANCE_PLAN.md#L100)
  is a completed checklist item recording that `scripted_resolver` /
  `omit_resolver` were dropped.
- `avp-cli/examples/onboarding/**` is fixture data for the onboarding example,
  not documentation of AVP.

Two in this area are NOT purely historical and do need a decision:

- [ ] [`COVERAGE.md`:95-107](avp/core/conformance/src/avp_conformance/COVERAGE.md#L95-L107)
      has a live "Blocked on infrastructure (no in-repo resolver)" section
      listing planned conformance cases for a layer that no longer exists,
      including an `error_occurred(resolver_not_configured)` case. Delete the
      section; keep the sub-bullet at [:107](avp/core/conformance/src/avp_conformance/COVERAGE.md#L107)
      about inline-skill coverage, which is still wanted.
- [ ] [`COVERAGE.md`:58](avp/core/conformance/src/avp_conformance/COVERAGE.md#L58)
      counts "the entire resolver layer" among what is uncovered.
- [ ] [`case.py`:13](avp/core/conformance/src/avp_conformance/case.py#L13) and
      [`CONFORMANCE_PLAN.md`:25](avp/core/conformance/src/avp_conformance/CONFORMANCE_PLAN.md#L25)
      state the no-stubbing policy as covering "model / tool / resolver
      outcomes". Drop the third item.

## Close out

- [ ] `grep -rin "resolver\|avp\.resolve\|spawn_subagent\|AVP_RESOLVER" .` and
      confirm every survivor is on the "leave alone" list above.
- [ ] `grep -rn "spec/v0\.1" *.md` and confirm no path predates the move to
      `avp/core/spec/v0.1/`. FOUNDATIONS.md had four of these.
- [ ] `make check`. Bindings drift detection is what catches a `make schemas`
      or `generate-bindings.sh` that was skipped. **Status so far:**
      `format-check`, `lint`, and `test` pass (all package suites green).
      `bindings-check` has not been run yet. `conformance` cannot pass on this
      machine, see below.
- [ ] No em dashes in any new prose (`CLAUDE.md` house rule).
- [ ] Paid checks are not required: this is a doc-and-metadata change with no
      observable wire impact. `make schemas` output is description text only,
      so no field shape moves.
- [ ] Delete this file.

**Blocked locally: `make conformance`.** It fails at the `goose-ping` step with
a 10s `TimeoutExpired` on `cargo run --bin avp-goose-conformance`. The real
cause is not the timeout: building the crate fails with "is `cmake` not
installed?" from a dependency's build script. `cmake` is missing on this
machine. This is a pre-existing environment gap with no connection to the
resolver cleanup (the sweep touches no Rust source except two doc comments),
but it does mean `make check` cannot go green here until `cmake` is installed
(`brew install cmake`). Verify on CI or after installing it before treating the
free floor as satisfied.
