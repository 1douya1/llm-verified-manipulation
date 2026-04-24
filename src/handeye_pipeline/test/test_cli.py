import pytest

from handeye_pipeline.cli import solve_main


def test_cli_help_sanity():
    with pytest.raises(SystemExit) as exc:
        solve_main(["--help"])
    assert exc.value.code == 0
