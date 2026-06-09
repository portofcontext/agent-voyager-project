"""An MCP server that teaches an agent AVP.

The `mcp` onboarding strategy: instead of dumping AVP docs into the system
prompt, give the agent tools to look them up on demand. The server bundles the
AVP docs (so it runs offline, no repo access needed) and exposes three tools:

  - list_avp_docs()        -> the doc sections available
  - read_avp_doc(name)     -> the full text of one section
  - search_avp(query)      -> the sections whose text matches, with snippets

Run it over stdio:  `avp-knowledge-mcp`  (or `uvx avp-knowledge-mcp` once published).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from avp_knowledge_mcp.docs import DOCS

mcp = FastMCP("avp-knowledge")


@mcp.tool()
def list_avp_docs() -> list[str]:
    """List the AVP documentation sections available to read."""
    return list(DOCS.keys())


@mcp.tool()
def read_avp_doc(name: str) -> str:
    """Read one AVP documentation section in full. `name` is one of list_avp_docs()."""
    if name not in DOCS:
        return f"unknown doc {name!r}; available: {', '.join(DOCS)}"
    return DOCS[name]


@mcp.tool()
def search_avp(query: str) -> str:
    """Search the AVP docs. Returns matching sections with a short snippet each."""
    q = query.lower().strip()
    hits: list[str] = []
    for name, text in DOCS.items():
        low = text.lower()
        idx = low.find(q)
        if idx != -1:
            start = max(0, idx - 80)
            snippet = text[start : idx + 160].replace("\n", " ")
            hits.append(f"[{name}] …{snippet}…")
    if not hits:
        return f"no AVP doc matched {query!r}; try list_avp_docs() and read_avp_doc(name)"
    return "\n".join(hits)


def main() -> None:
    mcp.run()
