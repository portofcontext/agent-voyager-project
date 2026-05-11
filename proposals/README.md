# AVP-RFCs

AVP-RFCs are how the Agent Voyager Project evolves. An **AVP-RFC** (Agent Voyager RFC) is a written design document that proposes, communicates, and coordinates a new effort: a new event type, a new resolver method, a structural change to a sub-spec, a process change.

> Acronym note: **AVP** is the project (Agent Voyager Project). **AVP-RFC** is a proposal against it. Keep them separate.

The format is borrowed from [Kubernetes Enhancement Proposals (KEPs)](https://github.com/kubernetes/enhancements), [IETF RFCs](https://www.rfc-editor.org/rfc-index.html), [Python PEPs](https://peps.python.org/), and [Rust RFCs](https://rust-lang.github.io/rfcs/). It is deliberately light at the project's current scale; the structure exists so that growth doesn't break the process.

## When to file an AVP-RFC

File an AVP-RFC for:

- **Wire-format changes**: new event types, new Commission fields, new Agent Descriptor fields, new Resolver API methods, breaking changes to existing shapes.
- **Stability transitions**: moving a sub-spec from `alpha` to `beta` to `stable`, or marking one `deprecated`.
- **Process changes**: changes to the AVP-RFC process itself, governance, the conformance suite contract.
- **Architectural decisions**: adding/removing a sub-spec, splitting one in two, renaming.

You do **not** need an AVP-RFC for:

- Bug fixes, performance work, or refactors that don't change the wire.
- Reference-implementation changes that don't touch any spec doc under `spec/v0.1/`.
- Documentation cleanups.

When in doubt, file one. AVP-RFCs are cheap; downstream churn from un-discussed wire changes is expensive.

## Quick start

1. **Read the umbrella sub-spec index** at [`../spec/v0.1/README.md`](../spec/v0.1/README.md) so you know which sub-spec your change touches.
2. **Copy [`NNNN-template/`](./NNNN-template/)** to `proposals/<NNNN>-<short-title>/` where `<NNNN>` is the next free integer (zero-padded).
3. **Fill out the README.md** following the section headings. The `Summary` and `Motivation` sections are the minimum to merge as `provisional`.
4. **Fill out `metadata.yaml`** with at minimum `title`, `authors`, `status`, `created`.
5. **Open a PR** with the new directory. Discuss in the PR.
6. **Iterate.** Merge early as `provisional`; refine in subsequent PRs as the proposal solidifies.

## Statuses

An AVP-RFC carries one of these statuses in its `metadata.yaml`:

| Status | Meaning |
|---|---|
| `provisional` | The proposal exists and is being discussed. Wire change NOT yet planned. |
| `accepted` | Design is approved. Implementation work can start. |
| `implementable` | Implementation has started or is fully scoped. |
| `implemented` | The proposal is fully realized in the spec + reference implementations. |
| `rejected` | The proposal was considered and declined. The document stays as a record. |
| `withdrawn` | The author pulled the proposal back. |
| `superseded-by-NNNN` | Replaced by a later AVP-RFC. |

`rejected` and `withdrawn` proposals stay in the directory. The historical record matters for future readers asking "did anyone consider X?"

## Numbering

AVP-RFCs are numbered with zero-padded integers, written as `AVP-RFC-0001`, `AVP-RFC-0002`, `AVP-RFC-0042`. Directory names use the bare integer (`0001-<short-title>/`). Numbers are assigned in PR-merge order, NOT pre-allocated. Pick the next free integer when your PR is ready to merge.

`NNNN-template/` is reserved as the template; do not use `0000`.

## Layout of an AVP-RFC directory

```
proposals/
├── README.md                          # this file
├── NNNN-template/                     # the template (copy it, do not edit)
│   ├── README.md
│   └── metadata.yaml
└── 0001-avp-to-atif-conversion/       # example future proposal
    ├── README.md                      # the design doc
    └── metadata.yaml                  # title, authors, status, created, sub-specs touched
```

## Relationship to sub-spec versioning

The four sub-specs ([Trajectory](../spec/v0.1/trajectory.md) / [Commission](../spec/v0.1/commission.md) / [Agent Descriptor](../spec/v0.1/agent-descriptor.md) / [Resolver API](../spec/v0.1/resolver.md)) share the umbrella `v0.1` version. AVP-RFCs are the granular record of *how* each sub-spec evolved between releases; the version bump bundles a set of `implemented` AVP-RFCs.

When an AVP-RFC lands a wire-affecting change, its `metadata.yaml` records which sub-spec(s) it touches and the target umbrella version. Future tooling can render an "AVP-RFCs implemented since v0.1" view by querying that metadata.
