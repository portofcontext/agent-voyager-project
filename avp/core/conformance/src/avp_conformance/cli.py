"""`avp-conformance` CLI entry point.

Gated behind the `conformance` extra. The Typer app lives in `_app.py` so
this shim stays importable even when typer isn't installed: the bare `avp`
package can advertise the entry point without failing on import, and the
user sees a clear "install the extra" message instead of an ImportError
traceback.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from avp_conformance._app import app
    except ImportError as e:
        if e.name == "typer":
            print(
                "error: avp-conformance requires the `conformance` extra.\n"
                "install with: pip install 'avp[conformance]'",
                file=sys.stderr,
            )
            sys.exit(2)
        raise
    app()
