"""Viewer-link payload shaping: single-agent stays flat, multi-agent folds into one."""

from __future__ import annotations

from avp_cli import viz


def _payload(agent: str) -> dict:
    return {
        "eval_version": "v1",
        "snapshot_at": "2026-05-28T00:00:00Z",
        "agent": agent,
        "by_commission": {"baseline": []},
        "commissions": {"baseline": {}},
    }


def test_combine_single_agent_stays_flat() -> None:
    p = _payload("goose")
    assert viz.combine_payloads([p]) is p  # no wrapper for the common case


def test_combine_multi_agent_wraps_into_agents() -> None:
    combined = viz.combine_payloads([_payload("goose"), _payload("claude-code")])
    assert set(combined) == {"eval_version", "snapshot_at", "agents"}
    assert [a["agent"] for a in combined["agents"]] == ["goose", "claude-code"]
    # each agent keeps its own by_commission slice
    assert all("by_commission" in a for a in combined["agents"])


def test_combined_link_roundtrips_through_the_site_decode() -> None:
    import base64
    import gzip
    import json

    combined = viz.combine_payloads([_payload("goose"), _payload("claude-code")])
    url = viz.view_url(combined, site="http://localhost:3000")
    z = url.split("#z=", 1)[1]
    # mirror payload.ts: base64url -> base64 -> gunzip -> json
    decoded = json.loads(gzip.decompress(base64.b64decode(z.replace("-", "+").replace("_", "/"))))
    assert decoded == combined
