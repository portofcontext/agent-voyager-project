# Maintainers

This file lists the current maintainers of the Agent Voyager Project. Maintainers are responsible for reviewing and merging changes, shepherding [AVP-RFCs](proposals/README.md) through their lifecycle, and signing off on release tags.

## Current maintainers

| Name | Organization | Areas of responsibility |
|---|---|---|
| Patrick Kelly | [@portofcontext](https://github.com/portofcontext) | Agentic-systems lead: Commission / Agent Descriptor / Trajectory shape, reference agent loop, supervisor patterns, overall governance |
| Elias Posen | [@portofcontext](https://github.com/portofcontext) | Protocol lead: Resolver API (JSON-RPC), MCP integration, CloudEvents / OTel GenAI attribute conformance, wire-format details |
| Patrick Carney | [@portofcontext](https://github.com/portofcontext) | Infrastructure lead: conformance harness and cases, CI/CD, release engineering, cross-language bindings (Rust / TS) and drift detection, `make smoke` matrix, deployment / cloud topology for the resolver service, performance and operational concerns across reference implementations |


## How to become a maintainer

The project is small. Become a maintainer the same way it works in most early-stage open-source projects: contribute substantial work (a proposal landed and implemented, a reference-agent rebuild, a meaningful conformance-suite expansion), demonstrate good judgment in reviews, and ask. Existing maintainers extend the invitation.

As the project grows, we will likely adopt the Kubernetes-style **OWNERS** model (per-directory reviewers/approvers) and SIG structure. Until there are enough contributors to warrant that overhead, this single MAINTAINERS.md is the source of truth.


## Contact

- File issues and PRs against [github.com/portofcontext/agent-voyager-project](https://github.com/portofcontext/agent-voyager-project).
