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


def test_reports_the_parts_on_the_plate(suitable_project, tmp_path, capsys):
    main([str(suitable_project), "--dry-run", "-o", str(tmp_path / "x.3mf")])

    out = capsys.readouterr().out
    assert "parts       : 1" in out
    assert "  part 1    : X 20.1..179.7  Y 0.2..159.8  top Z 180.00" in out


def test_reports_the_planned_push_lines(cone_multi_project, tmp_path, capsys):
    """Four cones, two of them touching: three parts swept off in two passes."""
    main([str(cone_multi_project), "--dry-run", "-o", str(tmp_path / "x.3mf")])

    out = capsys.readouterr().out
    assert "parts       : 3" in out
    assert "push plan   : 2 line(s), left to right (blade 55 mm, reach 27.5 mm)" in out
    assert "  line 1    : X 71.62  Z 38.08  (parts 1, 2)" in out
    assert "  line 2    : X 145.99  Z 23.38  (part 3)" in out


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


def test_the_default_cooldown_is_26_degrees(golden_project, tmp_path, capsys):
    main([str(golden_project), "-n", "1", "--dry-run", "-o", str(tmp_path / "x.3mf")])
    # The A1 Mini's bed sensor reads 4 degrees high, so 26 is commanded as 19.
    assert "cool-down   : 26 C -> commanded 19 C" in capsys.readouterr().out
