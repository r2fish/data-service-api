"""tools/tests/test_ledger.py -- tests for tools/dev/ledger.py.

The design is docs/design/LEDGER_FIXED_FIELDS_V1.md (D-1 to D-3, D-7, D-8);
the work order is docs/work-orders/WORK_ORDER_R117_LEDGER_FIXED_FIELDS_V1.md
WP-1. Not under `conformance-tests/` and not in pyproject.toml's `testpaths`
(same convention as tools/tests/test_change_class.py).

Every fixture is synthetic and written under `tmp_path`: a small ledger with
the two tables, an archive file, and (for --verify-move) a throwaway git
repository. Each red test breaks exactly one condition and asserts that the
findings carry that one tag and no other, so a fixture that trips a second
check by accident fails the test, and a check that goes missing turns the
test red instead of leaving it green on an unrelated finding. The last group
runs the tool on the repository's real ledger.

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_ledger.py -q
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DEV = Path(__file__).resolve().parents[1] / "dev"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"dev_{name}", _DEV / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


ledger = _load("ledger")

HEADER_81 = "| ID | 状態 | 規模 | 印 | 着手条件 | 件名 | 内容 | 行き先 |\n|---|---|---|---|---|---|---|---|"
HEADER_82 = "| ID | 状態 | 閉止日 | 件名 |\n|---|---|---|---|"
ARCHIVE_HEAD = (
    "<!-- 出所: synthetic ledger fixture -->\n"
    "<!-- 抜き出した時点: synthetic -->\n"
    "<!-- 逐語。書き換えない -->\n"
)


def r81(n, state="未着手", size="M", mark="なし", cond="-", title="件名", rest="内容 | 行き先 |"):
    return f"| **R-{n}** | {state} | {size} | {mark} | {cond} | {title} | {rest}"


def r82(n, state="閉止", date="2026-09-08", title="索引の件名"):
    return f"| **R-{n}** | {state} | {date} | {title} |"


def old_row(n):
    return f"| **R-{n}** | 内容{n} | 行き先{n} |"


def section(n, extra=(), row=None):
    body = ["", f"## R-{n}", "", row if row is not None else old_row(n), ""]
    for line in extra:
        body += [line, ""]
    return "\n".join(body)


def ledger_text(rows81, rows82):
    return (
        "# Synthetic ledger\n\n## 8. 台帳\n\n- 記録: archive\n\n"
        "### 8.1 未閉止と常設の行\n\n" + HEADER_81 + "\n" + "\n".join(rows81) + "\n\n"
        "### 8.2 閉止・却下の索引\n\n" + HEADER_82 + "\n" + "\n".join(rows82) + "\n\n"
        "### R-23 着手前調査資料（非正本）\n\ntext\n\n---\n\n## 9. 次\n"
    )


def base_rows81():
    return [r81(1, "常設", "-", "なし"), r81(2, "進行中", "S", "あり", "着手の条件"), r81(3)]


def base_rows82():
    return [r82(4), r82(5, "却下", "2026-09-09")]


def archive_text(ids, head=ARCHIVE_HEAD, extras=None):
    extras = extras or {}
    return head + "".join(section(n, extras.get(n, ())) for n in ids)


def build(tmp_path, rows81=None, rows82=None, archive=None):
    rows81 = base_rows81() if rows81 is None else rows81
    rows82 = base_rows82() if rows82 is None else rows82
    lp = tmp_path / "ledger.md"
    ap = tmp_path / "archive.md"
    lp.write_text(ledger_text(rows81, rows82), encoding="utf-8")
    ap.write_text(archive if archive is not None else archive_text([4, 5], extras={4: ["【追記 2026-09-30】追記の本文"]}), encoding="utf-8")
    return lp, ap


def run(capsys, *argv):
    code = ledger.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def check(capsys, lp, ap):
    return run(capsys, str(lp), "--archive", str(ap), "--check")


def tags(out):
    return set(re.findall(r"^RED \[([\w-]+)\]", out, re.M))


def assert_red(capsys, tmp_path, tag, **kw):
    lp, ap = build(tmp_path, **kw)
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {tag}, out


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------

def test_baseline_fixture_is_green(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, _ = check(capsys, lp, ap)
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "ledger --check: GREEN rows(8.1)=3 rows(8.2)=2 archive_sections=2"


def test_script_runs_as_a_program(tmp_path):
    lp, ap = build(tmp_path)
    proc = subprocess.run(
        ["python3", str(_DEV / "ledger.py"), str(lp), "--archive", str(ap), "--check"],
        capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout.decode("utf-8")
    assert "GREEN" in proc.stdout.decode("utf-8")


# ---------------------------------------------------------------------------
# --check: one red per condition (work order 2.3 conditions 1-13)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("which,rows", [
    ("81", [r81(1, "常設", "-", "なし"), "| **R-2** | 進行中 | S | あり | - |", r81(3)]),
    ("81", [r81(1, "常設", "-", "なし"), r81(2, rest="内容 |"), r81(3)]),
    ("82", [r82(4), "| **R-5** | 却下 | 2026-09-09 |"]),
    ("82", [r82(4), "| **R-5** | 却下 | 2026-09-09 | 件名 | 余分 |"]),
])
def test_c1_missing_or_extra_columns(tmp_path, capsys, which, rows):
    if which == "81":
        assert_red(capsys, tmp_path, "fields", rows81=rows)
    else:
        assert_red(capsys, tmp_path, "fields", rows82=rows)


@pytest.mark.parametrize("rows81", [
    [r81(1, "常設", "-", "なし"), r81(2, state="保留"), r81(3)],
    [r81(1, "常設", "-", "なし"), r81(2, size="XL"), r81(3)],
    [r81(1, "常設", "-", "なし"), r81(2, mark="多分"), r81(3)],
])
def test_c2_value_outside_the_vocabulary(tmp_path, capsys, rows81):
    assert_red(capsys, tmp_path, "vocab", rows81=rows81)


def test_c2_state_outside_the_vocabulary_in_the_index(tmp_path, capsys):
    assert_red(capsys, tmp_path, "vocab", rows82=[r82(4), r82(5, state="完了")])


def test_c2b_dash_size_only_for_a_standing_row(tmp_path, capsys):
    assert_red(capsys, tmp_path, "dash", rows81=[r81(1, "常設", "-", "なし"), r81(2, size="-"), r81(3)])


@pytest.mark.parametrize("date", ["2026-02-30", "2026-9-8", "20260908", "2026-13-01"])
def test_c3_closing_date_must_be_a_calendar_date(tmp_path, capsys, date):
    assert_red(capsys, tmp_path, "date", rows82=[r82(4, date=date), r82(5, "却下", "2026-09-09")])


@pytest.mark.parametrize("which,rows", [
    ("81", [r81(1, "常設", "-", "なし"), r81(2, title="あ" * 41), r81(3)]),
    ("81", [r81(1, "常設", "-", "なし"), r81(2, cond="い" * 61), r81(3)]),
    ("82", [r82(4, title="う" * 41), r82(5, "却下", "2026-09-09")]),
])
def test_c4_length_overrun(tmp_path, capsys, which, rows):
    if which == "81":
        assert_red(capsys, tmp_path, "length", rows81=rows)
    else:
        assert_red(capsys, tmp_path, "length", rows82=rows)


def test_c4_the_limits_themselves_are_green(tmp_path, capsys):
    rows81 = [r81(1, "常設", "-", "なし"), r81(2, title="あ" * 40, cond="い" * 60), r81(3)]
    lp, ap = build(tmp_path, rows81=rows81, rows82=[r82(4, title="う" * 40), r82(5, "却下", "2026-09-09")])
    code, out, _ = check(capsys, lp, ap)
    assert code == 0, out


@pytest.mark.parametrize("which,rows", [
    ("81", [r81(1, "常設", "-", "なし"), r81(2, title="a|b"), r81(3)]),
    ("81", [r81(1, "常設", "-", "なし"), r81(2, cond="a|b"), r81(3)]),
    ("82", [r82(4, title="a|b"), r82(5, "却下", "2026-09-09")]),
])
def test_c5_pipe_in_a_fixed_field(tmp_path, capsys, which, rows):
    if which == "81":
        assert_red(capsys, tmp_path, "pipe", rows81=rows)
    else:
        assert_red(capsys, tmp_path, "pipe", rows82=rows)


def test_c6_duplicate_id_in_one_table(tmp_path, capsys):
    assert_red(capsys, tmp_path, "dup", rows81=[r81(1, "常設", "-", "なし"), r81(2), r81(2), r81(3)])


def test_c6_duplicate_id_across_the_two_tables(tmp_path, capsys):
    assert_red(capsys, tmp_path, "dup", rows81=[r81(1, "常設", "-", "なし"), r81(2), r81(3), r81(5)])


def test_c7_missing_id(tmp_path, capsys):
    assert_red(capsys, tmp_path, "gap", rows81=[r81(1, "常設", "-", "なし"), r81(2)], rows82=[r82(4), r82(5, "却下", "2026-09-09")])


def test_c8_ids_not_ascending_in_table_one(tmp_path, capsys):
    assert_red(capsys, tmp_path, "order", rows81=[r81(1, "常設", "-", "なし"), r81(3), r81(2)])


def test_c8_ids_not_ascending_in_the_index(tmp_path, capsys):
    assert_red(capsys, tmp_path, "order", rows82=[r82(5, "却下", "2026-09-09"), r82(4)])


@pytest.mark.parametrize("which,rows", [
    ("81", [r81(1, "常設", "-", "なし"), r81(2, state="閉止"), r81(3)]),
    ("81", [r81(1, "常設", "-", "なし"), r81(2), r81(3, state="却下")]),
    ("82", [r82(4, state="未着手"), r82(5, "却下", "2026-09-09")]),
    ("82", [r82(4), r82(5, state="常設", date="2026-09-09")]),
])
def test_c9_state_does_not_belong_in_the_table(tmp_path, capsys, which, rows):
    if which == "81":
        assert_red(capsys, tmp_path, "table", rows81=rows)
    else:
        assert_red(capsys, tmp_path, "table", rows82=rows)


def test_c10_index_id_without_an_archive_section(tmp_path, capsys):
    assert_red(capsys, tmp_path, "index", archive=archive_text([4]))


def test_c10_archive_section_without_an_index_row(tmp_path, capsys):
    assert_red(capsys, tmp_path, "index", archive=archive_text([4, 5, 9]))


def test_c10_two_archive_sections_for_one_id(tmp_path, capsys):
    assert_red(capsys, tmp_path, "index", archive=archive_text([4, 4, 5]))


def test_c11_section_with_no_row(tmp_path, capsys):
    text = ARCHIVE_HEAD + "\n## R-4\n\n" + section(5)
    assert_red(capsys, tmp_path, "section", archive=text)


def test_c11_section_with_two_rows(tmp_path, capsys):
    text = ARCHIVE_HEAD + section(4, extra=[old_row(4)]) + section(5)
    assert_red(capsys, tmp_path, "section", archive=text)


def test_c11_heading_and_row_id_disagree(tmp_path, capsys):
    text = ARCHIVE_HEAD + section(4, row=old_row(6)) + section(5)
    assert_red(capsys, tmp_path, "section", archive=text)


def test_c11_a_later_note_line_is_not_a_row(tmp_path, capsys):
    lp, ap = build(tmp_path, archive=archive_text([4, 5], extras={5: ["【追記 2026-10-01】note", "【追記 2026-10-02】note"]}))
    code, out, _ = check(capsys, lp, ap)
    assert code == 0, out


@pytest.mark.parametrize("head", [
    "",
    "<!-- 出所: one -->\n<!-- two -->\n",
    "<!-- 出所: one -->\n<!-- two -->\nplain third line\n",
])
def test_c12_archive_header_missing(tmp_path, capsys, head):
    assert_red(capsys, tmp_path, "header", archive=archive_text([4, 5], head=head))


def test_c13_no_rows_at_all_is_red(tmp_path, capsys):
    lp, ap = build(tmp_path, rows81=[], rows82=[], archive=ARCHIVE_HEAD)
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"empty"}, out


# ---------------------------------------------------------------------------
# --check: what the tables are read from (return 1, points 1-2 and 4)
# ---------------------------------------------------------------------------

SEP_81 = "|---|---|---|---|---|---|---|---|"
SEP_82 = "|---|---|---|---|"


def build_edited(tmp_path, old, new, archive=None):
    """The baseline fixture with one piece of the ledger text replaced."""
    lp, ap = build(tmp_path, archive=archive)
    text = lp.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    lp.write_text(text.replace(old, new), encoding="utf-8")
    return lp, ap


def assert_red_edited(capsys, tmp_path, old, new, expected, archive=None):
    lp, ap = build_edited(tmp_path, old, new, archive=archive)
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == expected, out
    return out


@pytest.mark.parametrize("heading,header,sep", [
    ("### 8.1 追加", HEADER_81.split("\n")[0], SEP_81),
    ("### 8.2 追加", HEADER_82.split("\n")[0], SEP_82),
])
def test_r1a_a_second_table_heading_is_red(tmp_path, capsys, heading, header, sep):
    assert_red_edited(
        capsys, tmp_path, "### R-23 着手前調査資料",
        f"{heading}\n\n{header}\n{sep}\n\n### R-23 着手前調査資料", {"heading"},
    )


def test_r1a_a_second_table_heading_with_a_row_is_red_twice(tmp_path, capsys):
    header = HEADER_81.split("\n")[0]
    assert_red_edited(
        capsys, tmp_path, "### R-23 着手前調査資料",
        f"### 8.1 追加\n\n{header}\n{SEP_81}\n{r81(6)}\n\n### R-23 着手前調査資料", {"heading", "stray"},
    )


def test_r1b_a_row_after_a_blank_line_in_table_one_is_red(tmp_path, capsys):
    assert_red_edited(capsys, tmp_path, "\n\n### 8.2 ", f"\n\n{r81(6)}\n\n### 8.2 ", {"stray"})


def test_r1b_a_closed_row_left_under_the_later_subsection_is_red(tmp_path, capsys):
    assert_red_edited(capsys, tmp_path, "\n\ntext\n", f"\n\n{old_row(2)}\n\ntext\n", {"stray"})


def test_r1b_a_row_shaped_line_after_section_8_is_not_stray(tmp_path, capsys):
    lp, ap = build_edited(tmp_path, "## 9. 次\n", f"## 9. 次\n\n{old_row(2)}\n")
    code, out, _ = check(capsys, lp, ap)
    assert code == 0, out


@pytest.mark.parametrize("old,new", [
    (HEADER_81.split("\n")[0], "| ID | 内容 | 行き先 |"),
    (HEADER_82.split("\n")[0], "| ID | 閉止日 | 状態 | 件名 |"),
])
def test_r1c_a_header_line_that_is_not_the_designed_columns_is_red(tmp_path, capsys, old, new):
    assert_red_edited(capsys, tmp_path, old, new, {"columns"})


def test_r2_an_archive_row_cut_short_is_red(tmp_path, capsys):
    text = ARCHIVE_HEAD + section(4) + section(5, row="| **R-5** | 内容5 | 行")
    lp, ap = build(tmp_path, archive=text)
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"row-end"}, out


def test_r2_an_archive_without_a_final_newline_is_red(tmp_path, capsys):
    lp, ap = build(tmp_path, archive=archive_text([4, 5]).rstrip("\n"))
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"eof"}, out


def test_r2_an_archive_cut_in_the_middle_of_its_last_row_is_red_twice(tmp_path, capsys):
    text = archive_text([4, 5]).rstrip("\n")
    lp, ap = build(tmp_path, archive=text[:-6])
    code, out, _ = check(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"row-end", "eof"}, out


@pytest.mark.parametrize("header", [HEADER_81, HEADER_82])
def test_r4_a_table_without_its_separator_line_is_red(tmp_path, capsys, header):
    out = assert_red_edited(capsys, tmp_path, header, header.split("\n")[0], {"fields"})
    assert "no header and separator" in out


@pytest.mark.parametrize("anchor", [r81(3), r82(5, "却下", "2026-09-09")])
def test_r4_a_table_line_without_an_id_cell_is_red(tmp_path, capsys, anchor):
    assert_red_edited(capsys, tmp_path, anchor, anchor + "\n| 余分な行 | x |", {"fields"})


def test_r4_open_refuses_a_ledger_with_an_unreadable_row(tmp_path, capsys):
    lp, ap = build(tmp_path, rows81=[r81(1, "常設", "-", "なし"), "| **R-2** | 進行中 | S | あり | - |", r81(3)])
    code, out, err = run(capsys, str(lp), "--archive", str(ap), "--open")
    assert code == 1
    assert out == ""
    assert "RED [fields]" in err and "run --check" in err


# ---------------------------------------------------------------------------
# --open / --all / --show (conditions 14-19)
# ---------------------------------------------------------------------------

def _open_fixture(tmp_path):
    rows81 = [
        r81(1, "未着手", "M", "あり", "設計の裁定", "一番目"),
        r81(2, "進行中", "S", "なし", "-", "二番目"),
        r81(3, "未着手", "L", "なし", "依頼者の判断", "三番目"),
        r81(4, "常設", "-", "あり", "-", "四番目 (常設)"),
    ]
    return build(tmp_path, rows81=rows81, rows82=[r82(5)], archive=archive_text([5]))


def _md_ids(out):
    return re.findall(r"^\| (R-\d+) \|", out, re.M)


def test_c14_open_leaves_out_standing_rows(tmp_path, capsys):
    lp, ap = _open_fixture(tmp_path)
    code, out, _ = run(capsys, str(lp), "--open")
    assert code == 0
    ids = _md_ids(out)
    assert ids and "R-4" not in ids and "R-5" not in ids


def test_c15_open_lists_unmarked_first_then_by_id(tmp_path, capsys):
    lp, ap = _open_fixture(tmp_path)
    code, out, _ = run(capsys, str(lp), "--open")
    assert code == 0
    assert _md_ids(out) == ["R-2", "R-3", "R-1"]


def test_c16_open_summary_line(tmp_path, capsys):
    lp, ap = _open_fixture(tmp_path)
    code, out, _ = run(capsys, str(lp), "--open")
    assert code == 0
    assert out.rstrip("\n").splitlines()[-1] == "open=3 (印なし=2 印あり=1; 未着手=2 進行中=1)"


def test_c16_open_columns_are_id_title_size_mark_condition_state(tmp_path, capsys):
    lp, ap = _open_fixture(tmp_path)
    _, out, _ = run(capsys, str(lp), "--open")
    lines = out.splitlines()
    assert lines[0] == "| ID | 件名 | 規模 | 印 | 着手条件 | 状態 |"
    assert lines[2] == "| R-2 | 二番目 | S | なし | - | 進行中 |"


def test_c17_tsv_is_tab_separated_and_has_no_markdown(tmp_path, capsys):
    lp, ap = _open_fixture(tmp_path)
    code, out, _ = run(capsys, str(lp), "--open", "--format", "tsv")
    assert code == 0
    lines = out.splitlines()
    assert not any(l.startswith("|") for l in lines)
    assert lines[0].split("\t") == ["ID", "件名", "規模", "印", "着手条件", "状態"]
    assert [l.split("\t")[0] for l in lines[1:4]] == ["R-2", "R-3", "R-1"]
    assert lines[1].split("\t") == ["R-2", "二番目", "S", "なし", "-", "進行中"]
    assert lines[-1] == "open=3 (印なし=2 印あり=1; 未着手=2 進行中=1)"


def test_c18_all_lists_standing_closed_and_rejected_rows_with_counts(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, _ = run(capsys, str(lp), "--all")
    assert code == 0
    assert _md_ids(out) == ["R-1", "R-2", "R-3", "R-4", "R-5"]
    assert out.rstrip("\n").splitlines()[-1] == "all=5 (未着手=1 進行中=1 常設=1 閉止=1 却下=1)"


def test_c19_show_prints_a_table_one_row_verbatim(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, _ = run(capsys, str(lp), "--archive", str(ap), "--show", "R-2")
    assert code == 0
    assert out == r81(2, "進行中", "S", "あり", "着手の条件") + "\n"


def test_c19_show_prints_an_archived_row_and_its_later_notes(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, _ = run(capsys, str(lp), "--archive", str(ap), "--show", "R-4")
    assert code == 0
    assert out.splitlines() == [old_row(4), "【追記 2026-09-30】追記の本文"]


def test_c19_show_of_an_unknown_id_is_red(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, err = run(capsys, str(lp), "--archive", str(ap), "--show", "R-77")
    assert code == 1
    assert out == "" and "R-77" in err


# ---------------------------------------------------------------------------
# --verify-move (conditions 20-22)
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_git(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True,
    )


def _move_fixture(tmp_path, base_ids=(1, 2, 3, 4, 5), rows81=None, archive_rows=None):
    """A repo whose HEAD holds the old one-table ledger; the work tree holds
    the two-table form and the archive (the archive lives outside the repo)."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    base = "# L\n\n## 8. 台帳\n\n| ID | 内容 | 行き先 |\n|---|---|---|\n" + "\n".join(old_row(n) for n in base_ids) + "\n\n## 9. 次\n"
    lp = repo / "docs" / "ledger.md"
    lp.write_text(base, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "docs/ledger.md")
    _git(repo, "commit", "-q", "-m", "base")
    if rows81 is None:
        rows81 = [
            r81(1, "常設", "-", "なし", rest="内容1 | 行き先1 |"),
            r81(2, rest="内容2 | 行き先2 |"),
            r81(3, rest="内容3 | 行き先3 |"),
        ]
    lp.write_text(ledger_text(rows81, [r82(4), r82(5, "却下", "2026-09-09")]), encoding="utf-8")
    ap = tmp_path / "archive.md"
    rows = archive_rows or {4: old_row(4), 5: old_row(5)}
    ap.write_text(ARCHIVE_HEAD + "".join(section(n, row=row) for n, row in rows.items()), encoding="utf-8")
    return lp, ap


def _verify(capsys, lp, ap, rev="HEAD"):
    return run(capsys, str(lp), "--archive", str(ap), "--verify-move", rev)


def test_move_fixture_is_green(tmp_path, capsys, isolated_git):
    lp, ap = _move_fixture(tmp_path)
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 0, out
    assert out.strip() == "ledger --verify-move HEAD: GREEN base_ids=5 archive_rows=2 new_ids=0"


def test_c20_archive_row_longer_than_the_base_row_is_red(tmp_path, capsys, isolated_git):
    lp, ap = _move_fixture(tmp_path, archive_rows={4: old_row(4) + " |", 5: old_row(5)})
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"moved-row"}, out


def test_c20_archive_row_with_one_changed_character_is_red(tmp_path, capsys, isolated_git):
    lp, ap = _move_fixture(tmp_path, archive_rows={4: old_row(4).replace("内容4", "内容X"), 5: old_row(5)})
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"moved-row"}, out


def test_c21_table_one_remainder_with_a_trailing_space_is_red(tmp_path, capsys, isolated_git):
    rows81 = [
        r81(1, "常設", "-", "なし", rest="内容1 | 行き先1 |"),
        r81(2, rest="内容2 | 行き先2 | "),
        r81(3, rest="内容3 | 行き先3 |"),
    ]
    lp, ap = _move_fixture(tmp_path, rows81=rows81)
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"kept-rest"}, out


def test_c21_table_one_remainder_with_a_changed_character_is_red(tmp_path, capsys, isolated_git):
    rows81 = [
        r81(1, "常設", "-", "なし", rest="内容1 | 行き先1 |"),
        r81(2, rest="内容2 | 行き先X |"),
        r81(3, rest="内容3 | 行き先3 |"),
    ]
    lp, ap = _move_fixture(tmp_path, rows81=rows81)
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"kept-rest"}, out


def test_r3_verify_move_is_red_while_check_has_findings(tmp_path, capsys, isolated_git):
    rows81 = [
        r81(1, "常設", "-", "なし", rest="内容1 | 行き先1 |"),
        "| **R-2** | 未着手 | M | なし | - |",
        r81(3, rest="内容3 | 行き先3 |"),
    ]
    lp, ap = _move_fixture(tmp_path, rows81=rows81)
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"fields"}, out
    assert out.strip().splitlines()[-1] == "ledger --verify-move HEAD: RED findings=1 new_ids=0"


def test_c22_a_base_id_in_neither_archive_nor_table_one_is_red(tmp_path, capsys, isolated_git):
    lp, ap = _move_fixture(tmp_path, base_ids=(1, 2, 3, 4, 5, 6))
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 1, out
    assert tags(out) == {"lost-id"}, out
    assert "R-6" in out


def test_c22_an_id_not_in_the_base_is_counted_not_red(tmp_path, capsys, isolated_git):
    rows81 = [
        r81(1, "常設", "-", "なし", rest="内容1 | 行き先1 |"),
        r81(2, rest="内容2 | 行き先2 |"),
        r81(3, rest="内容3 | 行き先3 |"),
        r81(6, rest="新しい内容 | 新しい行き先 |"),
    ]
    lp, ap = _move_fixture(tmp_path, rows81=rows81)
    code, out, _ = _verify(capsys, lp, ap)
    assert code == 0, out
    assert out.strip() == "ledger --verify-move HEAD: GREEN base_ids=5 archive_rows=2 new_ids=1"


# ---------------------------------------------------------------------------
# precondition errors (condition 23)
# ---------------------------------------------------------------------------

def test_c23_unreadable_ledger_is_78(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, out, err = run(capsys, str(tmp_path / "absent.md"), "--archive", str(ap), "--check")
    assert code == 78
    assert "precondition" in err


def test_c23_no_section_8_tables_is_78(tmp_path, capsys):
    lp, ap = build(tmp_path)
    lp.write_text("# Ledger without section 8\n\ntext\n", encoding="utf-8")
    code, _, err = check(capsys, lp, ap)
    assert code == 78
    assert "8.1" in err


def test_c23_unreadable_archive_is_78(tmp_path, capsys):
    lp, ap = build(tmp_path)
    code, _, err = run(capsys, str(lp), "--archive", str(tmp_path / "absent.md"), "--check")
    assert code == 78
    assert "precondition" in err


def test_c23_verify_move_outside_a_git_repository_is_78(tmp_path, capsys, isolated_git):
    lp, ap = build(tmp_path)
    code, _, err = _verify(capsys, lp, ap)
    assert code == 78
    assert "git" in err


def test_c23_verify_move_with_an_unknown_revision_is_78(tmp_path, capsys, isolated_git):
    lp, ap = _move_fixture(tmp_path)
    code, _, err = _verify(capsys, lp, ap, rev="no-such-revision")
    assert code == 78
    assert "git" in err


def test_c23_verify_move_without_a_git_binary_is_78(tmp_path, capsys, monkeypatch):
    lp, ap = build(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    code, _, err = _verify(capsys, lp, ap)
    assert code == 78
    assert "git" in err


# ---------------------------------------------------------------------------
# the repository's own ledger (condition 24)
# ---------------------------------------------------------------------------

def test_c24_real_ledger_check_is_green(capsys):
    code, out, err = run(capsys, "--check")
    assert code == 0, out + err
    m = re.search(r"GREEN rows\(8\.1\)=(\d+) rows\(8\.2\)=(\d+) archive_sections=(\d+)", out)
    assert m, out
    n81, n82, sections = (int(g) for g in m.groups())
    assert n81 > 0 and n82 > 0 and sections == n82


def test_c24_real_ledger_open_lists_rows(capsys):
    code, out, err = run(capsys, "--open")
    assert code == 0, err
    n = int(re.search(r"^open=(\d+) ", out, re.M).group(1))
    assert n > 0 and len(_md_ids(out)) == n
