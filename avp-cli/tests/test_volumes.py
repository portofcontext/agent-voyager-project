"""`--volume HOST:SANDBOX[:ro]`."""

from pathlib import Path

import pytest
from opensandbox.models.sandboxes import Host, Volume

from avp_cli.console import Failed
from avp_cli.runs import volumes


def test_read_write_and_read_only(tmp_path: Path) -> None:
    host = Host(path=str(tmp_path.resolve()))
    assert volumes.parse([f"{tmp_path}:/data", f"{tmp_path}:/ro:ro"]) == [
        Volume(name="volume-0", host=host, mount_path="/data"),
        Volume(name="volume-1", host=host, mount_path="/ro", read_only=True),
    ]


@pytest.mark.parametrize(
    ("volume", "message"),
    [
        ("{tmp}", "isn't HOST:SANDBOX"),
        ("{tmp}:/a:/b", "isn't HOST:SANDBOX"),
        ("{tmp}/missing:/data", "doesn't exist"),
        ("{tmp}:data", "must be an absolute path"),
        ("{tmp}:/io", "is the run directory"),
        ("{tmp}:/io/x", "is the run directory"),
    ],
)
def test_bad_volumes_fail(tmp_path: Path, volume: str, message: str) -> None:
    with pytest.raises(Failed, match=message):
        volumes.parse([volume.format(tmp=tmp_path)])
