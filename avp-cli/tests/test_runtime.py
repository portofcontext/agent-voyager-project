from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from avp_cli import runtime


@pytest.mark.parametrize("egress", [[], ["api.openai.com"]])
def test_libkrun_never_starts_with_unfiltered_network(monkeypatch, egress) -> None:
    run = Mock(return_value=CompletedProcess([], 0, stdout="", stderr=""))
    monkeypatch.setattr(runtime.subprocess, "run", run)
    kwargs = {
        "image": "test",
        "env": {},
        "mounts": [],
        "egress": egress,
        "resources": {},
        "timeout_s": 10,
    }
    backend = runtime.LibkrunRuntime()
    if egress:
        with pytest.raises(ValueError, match="use opensandbox"):
            backend.create(**kwargs)
        run.assert_not_called()
    else:
        backend.create(**kwargs)
        argv = run.call_args.args[0]
        assert argv[argv.index("--network") + 1] == "none"
