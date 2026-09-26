import json

from jolteon.cli.replay import main


def test_cli_validation_and_failure(replay_dataset, tmp_path, capsys):
    _, document = replay_dataset
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    assert main(["validate", "--manifest", str(path)]) == 0
    assert "input_hash" in capsys.readouterr().out
    assert main(["compare", str(tmp_path)]) == 1
    assert main(["compare", str(tmp_path), str(tmp_path / "absent")]) == 1
    assert (
        main(
            [
                "run",
                "--manifest",
                str(path),
                "--speed",
                "unbounded",
                "--output",
                str(tmp_path / "one"),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run",
                "--manifest",
                str(path),
                "--speed",
                "unbounded",
                "--output",
                str(tmp_path / "two"),
            ]
        )
        == 0
    )
    assert main(["compare", str(tmp_path / "one"), str(tmp_path / "two")]) == 2
    meta = tmp_path / "two/result.json"
    data = json.loads(meta.read_text())
    data["status"] = "failed"
    meta.write_text(json.dumps(data))
    assert main(["compare", str(tmp_path / "one"), str(tmp_path / "two")]) == 1


def test_cli_strict_equivalence(native_replay_dataset, tmp_path):
    _, document = native_replay_dataset
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    for name in ("a", "b"):
        assert (
            main(
                [
                    "run",
                    "--manifest",
                    str(path),
                    "--output",
                    str(tmp_path / name),
                ]
            )
            == 0
        )
    assert main(["compare", str(tmp_path / "a"), str(tmp_path / "b")]) == 0


def test_fresh_processes_match_at_all_speeds(native_replay_dataset, tmp_path):
    import subprocess
    import sys

    _, document = native_replay_dataset
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    outputs = []
    for speed in ("1x", "10x", "24x", "unbounded"):
        output = tmp_path / speed
        subprocess.run(
            [
                sys.executable,
                "-m",
                "jolteon.cli.replay",
                "run",
                "--manifest",
                str(path),
                "--speed",
                speed,
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        outputs.append(str(output))
    assert main(["compare", *outputs]) == 0
