import sys

from jolteon.dashboard.config import parse_args


def test_parse_args_defaults_db_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = parse_args()

    assert args.root == "/tmp/jolteon"
    assert args.log_db == ""


def test_parse_args_reads_custom_db_path(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--root",
            "/custom/root",
            "--log-db",
            "/custom/log.sqlite",
        ],
    )

    args = parse_args()

    assert args.root == "/custom/root"
    assert args.log_db == "/custom/log.sqlite"
