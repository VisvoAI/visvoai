"""Large-read protection — read_file pagination + list/shell output caps.

These bound a single tool result so it can't flood the model's context. Pure
function tests (no UI) against the package tools.
"""
import os

from visvoai.cli.tools import (
    read_file, list_files, run_shell, list_tree, cap_lines,
    READ_LINE_CAP, MAX_LINE_LEN, SHELL_LINE_CAP, TREE_PER_DIR_CAP, TREE_TOTAL_CAP,
)


def _big_file(tmp_path, n):
    p = tmp_path / "big.txt"
    p.write_text("\n".join(f"line {i}" for i in range(n)))
    return str(p)


def test_read_caps_at_default_with_paging_note(tmp_path):
    out = read_file.invoke({"path": _big_file(tmp_path, 5000)})
    lines = out.splitlines()
    assert len(lines) == READ_LINE_CAP + 1            # 2000 content + 1 note
    assert lines[0] == "1\tline 0"
    assert "of 5000" in lines[-1] and "offset=2001" in lines[-1]


def test_read_offset_pages_window(tmp_path):
    out = read_file.invoke({"path": _big_file(tmp_path, 5000), "offset": 2001, "limit": 100})
    lines = out.splitlines()
    assert lines[0] == "2001\tline 2000"              # 1-based offset
    assert len(lines) == 101                          # 100 content + note
    assert "lines 2001–2100 of 5000" in lines[-1]


def test_read_small_file_has_no_note(tmp_path):
    p = tmp_path / "s.txt"; p.write_text("a\nb\nc")
    out = read_file.invoke({"path": str(p)})
    assert out == "1\ta\n2\tb\n3\tc"                  # no paging note when it all fits


def test_read_offset_past_end_errors(tmp_path):
    out = read_file.invoke({"path": _big_file(tmp_path, 10), "offset": 99})
    assert out.startswith("ERROR: offset 99 is past end")


def test_read_clips_long_lines(tmp_path):
    p = tmp_path / "wide.txt"; p.write_text("x" * (MAX_LINE_LEN + 500))
    out = read_file.invoke({"path": str(p)})
    assert "[line truncated]" in out
    assert len(out.splitlines()[0]) < MAX_LINE_LEN + 100


def test_cap_lines_marks_truncation():
    capped = cap_lines("\n".join(str(i) for i in range(50)), 10)
    assert capped.splitlines()[:10] == [str(i) for i in range(10)]
    assert "showing 10 of 50 lines" in capped.splitlines()[-1]
    # under the cap → untouched
    assert cap_lines("a\nb", 10) == "a\nb"


def test_shell_caps_output_but_keeps_exit_marker(tmp_path):
    out = run_shell.invoke({"command": f"seq {SHELL_LINE_CAP + 500}"})
    assert out.splitlines()[-1] == "[exit: 0]"        # marker survives truncation
    assert "output truncated" in out


# ── list_tree: bounded on depth, fan-out, and total ──────────────────────────
def test_list_tree_prunes_noise_dirs(tmp_path):
    os.makedirs(tmp_path / "node_modules" / "pkg")
    (tmp_path / "node_modules" / "pkg" / "x.js").write_text("")
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("")
    out = list_tree.invoke({"path": str(tmp_path), "depth": 3})
    assert "node_modules" not in out      # pruned (non-git → fallback noise set)
    assert "src/" in out and "a.py" in out


def test_list_tree_per_dir_fanout_cap(tmp_path):
    big = tmp_path / "data"; big.mkdir()
    for i in range(TREE_PER_DIR_CAP + 150):
        (big / f"f{i}.csv").write_text("")
    out = list_tree.invoke({"path": str(tmp_path), "depth": 2})
    assert out.count(".csv") == TREE_PER_DIR_CAP    # clipped at the per-dir cap
    assert "more entries" in out


def test_list_tree_depth_limits_descent(tmp_path):
    deep = tmp_path / "a" / "b" / "c"; deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("")
    (tmp_path / "a" / "top.txt").write_text("")
    out = list_tree.invoke({"path": str(tmp_path), "depth": 1})
    assert "a/" in out
    assert "top.txt" not in out and "deep.txt" not in out   # depth 1 → no descent


def test_list_tree_errors_on_non_dir(tmp_path):
    f = tmp_path / "x.txt"; f.write_text("hi")
    assert list_tree.invoke({"path": str(f)}).startswith("ERROR: not a directory")
