"""Vendor the `avp` wire types into the standalone avp-cli wheel.

`avp-cli` is the only distribution we publish to PyPI (see release-pypi.yml). It
carries the `avp` wire types inside its own wheel so `uv tool install avp-cli` is
the entire install, with no separate `agent-voyager-project` dist to publish. The
CLI does not depend on the conformance harness (it owns its own agent-manifest
model in `avp_cli.agent_manifest`), so the harness and its case files stay out of
the wheel.

Crucially this runs for `standard` wheel builds ONLY: for `editable` installs it
is a no-op, so a workspace `uv sync` keeps resolving `import avp` to the live
editable source under avp/ instead of a stale copy shadowing it in site-packages.
"""

from __future__ import annotations

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Sibling source tree, relative to this package root (avp-cli/), mapped to its
# import-package name at the top of the wheel.
_VENDOR = {
    "../avp/bindings/python/src/avp": "avp",
}


class VendorSiblingsHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        build_data["force_include"].update(_VENDOR)
