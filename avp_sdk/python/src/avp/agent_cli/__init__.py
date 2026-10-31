"""The command line every in-tree AVP agent answers.

**Not part of the AVP spec**, which leaves transport to the deployment. A
provisional file transport for development, demos, and avp-cli, until the spec
defines one.

    <agent> ping [--out <path>]
    <agent> describe [--out <path>]
    <agent> run --commission <path | JSON> --out <path | ->

    raise SystemExit(main(run=run, describe=describe))
"""

from avp.agent_cli.cli import main
from avp.agent_cli.run import DescribeFn, RunFn
from avp.agent_cli.sink import EventSink, ndjson_sink

__all__ = ["DescribeFn", "EventSink", "RunFn", "main", "ndjson_sink"]
