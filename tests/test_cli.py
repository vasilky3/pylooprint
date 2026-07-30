"""End-to-end runs through the console interface."""

from __future__ import annotations

import zipfile

from pylooprint.cli import main


def test_refuses_an_already_looped_file(result_3mf, capsys, tmp_path):
    exit_code = main([str(result_3mf), "-n", "2", "-o", str(tmp_path / "out.gcode.3mf")])
    assert exit_code == 1
    assert "already been looped" in capsys.readouterr().err


def test_writes_a_valid_3mf(golden_project, tmp_path, capsys):
    destination = tmp_path / "looped.gcode.3mf"
    assert main([str(golden_project), "-n", "2", "-o", str(destination)]) == 0

    out = capsys.readouterr().out
    assert "printer     : A1 Mini" in out
    assert destination.exists()

    with zipfile.ZipFile(destination) as archive:
        gcode = archive.read("Metadata/plate_1.gcode").decode("utf-8")
        assert "Metadata/slice_info.config" in archive.namelist()
    assert gcode.count("; >>> LOOP 2 / 2 <<<") == 1


def test_dry_run_writes_nothing(golden_project, tmp_path, capsys):
    destination = tmp_path / "nope.gcode.3mf"
    assert main([str(golden_project), "-n", "2", "--dry-run", "-o", str(destination)]) == 0
    assert not destination.exists()
    assert "would write" in capsys.readouterr().out


def test_rejects_out_of_range_settings(result_3mf, capsys):
    assert main([str(result_3mf), "-n", "0"]) == 1
    assert "--loops must be between" in capsys.readouterr().err
    assert main([str(result_3mf), "-t", "200"]) == 1
    assert "--temp must be between" in capsys.readouterr().err


def test_reports_a_risky_cooldown_temperature(golden_project, tmp_path, capsys):
    main([str(golden_project), "-n", "1", "-t", "40", "--dry-run", "-o", str(tmp_path / "x.3mf")])
    assert "may not release the part" in capsys.readouterr().err


def test_printer_can_be_overridden(golden_project, tmp_path, capsys):
    main([str(golden_project), "-n", "1", "-p", "a1", "--dry-run", "-o", str(tmp_path / "x.3mf")])
    assert "printer     : A1" in capsys.readouterr().out


def test_the_default_cooldown_is_23_degrees(golden_project, tmp_path, capsys):
    main([str(golden_project), "-n", "1", "--dry-run", "-o", str(tmp_path / "x.3mf")])
    # The A1 Mini's bed sensor reads 4 degrees high, so 23 is commanded as 19.
    assert "cool-down   : 23 C -> commanded 19 C" in capsys.readouterr().out
