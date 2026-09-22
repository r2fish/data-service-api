"""Q4 phase WP-0 (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-3
(d)/(f), §8.1, §10; work order docs/work-orders/
WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md §4 WP-0 変更対象 B): the static
rule scanner that fixes the per-application platform-upgrade script
discipline (design D-3 (c)) as an executable check, revised from the
disposable prototype (`{scratchpad}/proto_ledger_scan.py` --
`ON CONFLICT` was not checked at all, and only a `VALUES(...)` sub-clause
was inspected for the own-number literal) to match design D-3 (d)
regulation (b) verbatim:

    各 script が `INSERT INTO public._{r2db,mdb}_platform_upgrades` を
    含む 1 つの文の中に、自番号の整数リテラル (ゼロ埋めを外したもの) と
    `ON CONFLICT` の両方を含むこと。

This peer's own test scans ONLY `r2db-api/migrations/` (design D-3 (d):
"各 peer のテストは自 peer の `migrations/` だけを走査する").

Non-vacuity (常設規律 1, work order §4 WP-0 非 vacuity 要件): the
synthetic `tmp_path` fixtures below observe 適合/違反/ゼロ埋め不適合/
命名不一致/三者不一致 -- at least one of each -- because the real
`migrations/` directory, as of this WP, has no per-application upgrade
script yet (r2db's first one, `0009`, ships in WP-3) and so cannot
exercise 適合 by itself (design §10: "本フェーズ出荷後" is the ONLY
point at which 適合 >= 1 is expected against the real directory).

xfail bookkeeping, REMOVED in this same WP-3 commit (supervisor ruling
2026-09-05, work order §4 WP-0 完了条件 7/8, WP-3 完了条件 12/13): the
two assertions against the REAL `migrations/` directory that could not
yet be true as of WP-0 (適合 >= 1, and the three-way match against the
not-yet-existing `r2db_api.platform_upgrades` package constant) were
registered `xfail(strict=True)` there and are removed HERE, in the same
commit that ships `r2db-api/migrations/0009_platform_upgrades_ledger_
upgrade.sql` and `r2db_api/platform_upgrades.py` -- both now assert
plainly (`test_real_migrations_dir_has_at_least_one_conforming_script`/
`test_real_migrations_three_way_match` below), and both are green.

Rework round (supervisor ruling 2026-09-05, work order §4 WP-0 差し戻し
指示 1 / 裁定 A / 裁定 C): code review round 1 (Opus, mutation-tested)
found the first pass of this scanner wrong on two counts, both fixed
below --

  1. It did not strip `--` line comments or `/* */` block comments
     before scanning, so a ledger `INSERT` appearing ONLY inside a
     comment (never actually executed) was misjudged 適合, and the
     naive non-greedy `.*?;` statement search stopped at the FIRST `;`
     found anywhere in the file -- including one inside a trailing
     inline comment or a single-quoted string literal -- which could
     truncate a real, conforming statement before its own `ON CONFLICT`
     clause and misjudge it 違反. Fixed by `_strip_sql_comments` (removes
     comments first, never treating `--`/`/*` INSIDE a string literal as
     a comment start) plus `_iter_ledger_statements`'s own quote-aware
     walk to the terminating `;` (a `;` inside an open single-quoted
     string is not a statement terminator).
  2. The table name was hardcoded as the alternation
     `_(?:r2db|mdb)_platform_upgrades`, so THIS peer's own scanner could
     misjudge a script that ledger-INSERTs into the SIBLING peer's table
     (`_mdb_platform_upgrades`) as 適合 (audit 設計疑義 乙, resolved in
     favor of 乙 by supervisor ruling 2026-09-05 / 裁定 C). Fixed by
     making `ledger_table_name` a parameter the caller supplies (this
     peer's own test always passes `LEDGER_TABLE_NAME` below, never the
     sibling's) -- the pinned function body itself now carries no
     peer-specific literal at all.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

# design D-3 (d): "許可リストは番号の集合であり、各 peer のテストが自 peer
# 分だけを持つ (MitateDB = {6}、r2db = 空)。"
ALLOW_LIST_NUMBERS: frozenset[int] = frozenset()

# 裁定 C (監査 設計疑義 乙): this peer's OWN ledger table name -- never the
# sibling's (`_mdb_platform_upgrades`) -- passed explicitly to every
# `_classify_migrations_dir` / `scan_platform_upgrade_ledger_script` /
# `template_seed_numbers` call below.
LEDGER_TABLE_NAME = "_r2db_platform_upgrades"

NAME_RE = re.compile(r"^(\d{4})_.*_upgrade\.sql$")


def _strip_sql_comments(sql: str) -> str:
    """Removes `--` line comments (up to, but not including, the next
    newline) and `/* */` block comments from `sql`, WITHOUT ever treating
    a `--` or `/*` that appears INSIDE a single-quoted string literal as
    the start of a comment (SQL string literals can legitimately contain
    those two-character substrings verbatim, e.g. a script's own
    descriptive text). An unterminated block comment consumes the rest of
    the text (matching how a real SQL parser would also fail to find a
    body-ending token, rather than reinterpreting the remainder as code).
    `''` (a doubled single quote, SQL's own escaped-quote form) is
    recognized so a string like `'it''s fine'` does not end the string
    one quote early."""
    out: list[str] = []
    i, n = 0, len(sql)
    in_string = False
    while i < n:
        ch = sql[i]
        if in_string:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append(sql[i + 1])
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            newline_at = sql.find("\n", i)
            if newline_at == -1:
                break
            out.append("\n")
            i = newline_at + 1
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end_at = sql.find("*/", i + 2)
            if end_at == -1:
                break
            i = end_at + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_string_literals(sql: str) -> str:
    """Removes every single-quoted string literal's CONTENT from `sql`
    (the surrounding quotes too), honoring the `''` escaped-quote form --
    used by `template_seed_numbers` below so a zero-padded string literal
    like `'0009'` can never leave behind digits for a bare-integer scan to
    pick up as if they were a real integer literal."""
    out: list[str] = []
    i, n = 0, len(sql)
    in_string = False
    while i < n:
        ch = sql[i]
        if in_string:
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _iter_ledger_statements(text: str, ledger_table_name: str) -> list[str]:
    """Yields each `INSERT INTO public.<ledger_table_name> ... ;`
    statement found in `text`, with comments stripped FIRST (so a ledger
    `INSERT` appearing only inside a `--`/`/* */` comment is never
    yielded at all -- it is not a real statement), and the terminating
    `;` located OUTSIDE any single-quoted string literal (so a `;` inside
    a string value, e.g. a `script_name` containing punctuation, never
    truncates the statement early). A statement whose `;` is never found
    before the text ends (malformed SQL) is not yielded."""
    stripped = _strip_sql_comments(text)
    start_re = re.compile(
        r"INSERT\s+INTO\s+public\." + re.escape(ledger_table_name) + r"\b",
        re.IGNORECASE,
    )
    statements: list[str] = []
    n = len(stripped)
    for start_match in start_re.finditer(stripped):
        i = start_match.start()
        in_string = False
        while i < n:
            ch = stripped[i]
            if in_string:
                if ch == "'":
                    if i + 1 < n and stripped[i + 1] == "'":
                        i += 2
                        continue
                    in_string = False
                i += 1
                continue
            if ch == "'":
                in_string = True
                i += 1
                continue
            if ch == ";":
                statements.append(stripped[start_match.start() : i + 1])
                break
            i += 1
    return statements


def scan_platform_upgrade_ledger_script(text: str, own_number: int, ledger_table_name: str) -> tuple[str, str]:
    """Design D-3 (d) regulation (b): classifies ONE per-application
    upgrade script's already-read SQL text as 適合 ("conforms") or 違反
    ("violates"), given the integer this script's own filename already
    identifies it by (`own_number`, the de-zero-padded `NNNN` -- the
    caller extracts this from the filename via `NAME_RE` before calling,
    since allow-listing and naming are the caller's own concerns, not
    this function's) and this peer's OWN ledger table name
    (`ledger_table_name` -- 裁定 C: the caller passes its own peer's
    table, e.g. `_r2db_platform_upgrades`, never the sibling peer's, so a
    script that ledger-INSERTs into the wrong peer's table is correctly
    違反, not 適合). 適合 requires a SINGLE
    `INSERT INTO public.<ledger_table_name> ... ;` statement that
    contains BOTH the literal (case-insensitive) keywords `ON CONFLICT`
    and a bare integer literal equal to `own_number` -- bounded on both
    sides against digits/`.` so a zero-padded STRING literal (e.g.
    `'0009'`) never counts as the bare integer `9` (the digit `0`
    immediately preceding the `9` blocks the left-hand boundary),
    matching design D-3 (d)'s own "ゼロ埋めを外したもの" text.

    Only statements that themselves target the ledger table are
    considered, via `_iter_ledger_statements` -- which strips `--`/`/* */`
    comments BEFORE searching (a commented-out ledger `INSERT` is not a
    real statement and must not count as 適合), and locates each
    statement's terminating `;` OUTSIDE any single-quoted string literal
    (a `;` inside a string value must not truncate a real statement
    early and misjudge it 違反).

    裁定 3 (audit-wp0-delta.log 設計疑義 1, supervisor ruling 2026-09-05,
    adopted 乙): the own-number search runs against the statement with
    every string literal's CONTENT stripped first (`_strip_string_
    literals`, symmetric with the sibling `template_seed_numbers` below,
    which already stripped string literals before ITS OWN digit scan) --
    design D-3 (d) regulation (b) says "自番号の整数リテラル" (an integer
    LITERAL), and a digit sequence appearing only inside a string value
    (e.g. a descriptive `script_name` or comment column that happens to
    mention a number) is not an integer literal at all. Before this fix,
    `VALUES ('x', 'note 9 here') ON CONFLICT ...` was misjudged 適合 for
    `own_number=9` -- the bare-integer search saw the whole statement
    text, quotes included."""
    own_literal_re = re.compile(r"(?<![\d.])" + re.escape(str(own_number)) + r"(?![\d.])")
    for statement in _iter_ledger_statements(text, ledger_table_name):
        has_on_conflict = re.search(r"\bON\s+CONFLICT\b", statement, re.IGNORECASE) is not None
        has_own_literal = own_literal_re.search(_strip_string_literals(statement)) is not None
        if has_on_conflict and has_own_literal:
            return (
                "適合",
                f"one INSERT ... {ledger_table_name} statement contains both ON CONFLICT and literal {own_number}",
            )
    return (
        "違反",
        f"no INSERT INTO public.{ledger_table_name} statement contains BOTH ON CONFLICT "
        f"and the literal integer {own_number} within the same statement",
    )


def template_seed_numbers(template_text: str, ledger_table_name: str) -> frozenset[int]:
    """Design D-3 (d) regulation (d) ("三者一致"): extracts the set of
    integer literals appearing INSIDE the `VALUES (...)` tuple(s) of
    template `0003`'s own ledger-seed `INSERT INTO public.
    <ledger_table_name> ... ON CONFLICT ...` statement(s) targeting THIS
    peer's own ledger table (`ledger_table_name` -- 裁定 C, never the
    sibling's, matching `scan_platform_upgrade_ledger_script` above) --
    this is the three-way match's "middle set". Only literals inside a
    `VALUES` tuple are counted: text after `ON CONFLICT` is cut off first
    (so, e.g., a numeric literal appearing only in an `ON CONFLICT DO
    UPDATE SET x = 2` clause is never miscounted as a seeded upgrade
    number), and every single-quoted string literal is stripped before
    the digit scan (so a zero-padded string like `'0009'` can never leave
    behind digits `0009` for the scan to misread as the bare integer
    `9`). Reuses `_iter_ledger_statements` so a ledger `INSERT` written
    inside a comment, or whose `;` sits inside a string literal, is
    handled the identical way `scan_platform_upgrade_ledger_script`
    handles it for a per-application script.

    Extracted (裁定 A, supervisor ruling 2026-09-05) so the synthetic
    three-way-match test below exercises this REAL extraction logic
    instead of three hand-written literal sets."""
    numbers: set[int] = set()
    for statement in _iter_ledger_statements(template_text, ledger_table_name):
        values_match = re.search(r"\bVALUES\b(.*)", statement, re.IGNORECASE | re.DOTALL)
        if values_match is None:
            continue
        values_text = re.split(r"\bON\s+CONFLICT\b", values_match.group(1), flags=re.IGNORECASE)[0]
        values_text = _strip_string_literals(values_text)
        for tuple_text in re.findall(r"\(([^()]*)\)", values_text):
            numbers.update(int(n) for n in re.findall(r"\b\d+\b", tuple_text))
    return frozenset(numbers)


class _ScanResult:
    def __init__(self) -> None:
        self.tally: dict[str, int] = {"適合": 0, "違反": 0, "免除": 0, "対象外": 0}
        self.details: list[tuple[str, str, str]] = []  # (filename, verdict, reason)

    @property
    def exempted_numbers(self) -> frozenset[int]:
        return frozenset(int(NAME_RE.match(name).group(1)) for name, verdict, _ in self.details if verdict == "免除")

    @property
    def applicable_numbers(self) -> frozenset[int]:
        """Every number this test scanned as a per-application upgrade
        script (適合/違反/免除 -- i.e. everything NAME_RE matched),
        regardless of verdict -- this is the "left-hand set" of design
        D-3 (d) regulation (d)'s three-way match."""
        return frozenset(int(NAME_RE.match(name).group(1)) for name, verdict, _ in self.details if verdict != "対象外")


def _classify_migrations_dir(migrations_dir: Path, allow_list: frozenset[int], ledger_table_name: str) -> _ScanResult:
    result = _ScanResult()
    for path in sorted(migrations_dir.glob("*.sql")):
        name = path.name
        match = NAME_RE.match(name)
        if not match:
            result.tally["対象外"] += 1
            result.details.append((name, "対象外", f"filename does not match {NAME_RE.pattern}"))
            continue
        own_number = int(match.group(1))
        if own_number in allow_list:
            result.tally["免除"] += 1
            result.details.append((name, "免除", f"{own_number} is on the allow-list; ledger-INSERT check skipped"))
            continue
        verdict, reason = scan_platform_upgrade_ledger_script(path.read_text(encoding="utf-8"), own_number, ledger_table_name)
        result.tally[verdict] += 1
        result.details.append((name, verdict, reason))
    return result


# ===========================================================================
# Synthetic fixtures (tmp_path) -- non-vacuity (常設規律 1): 適合/違反/
# ゼロ埋め不適合/命名不一致/三者不一致 each observed at least once,
# independent of whatever the real migrations/ directory currently
# contains.
# ===========================================================================


def test_synthetic_conforming_script_is_適合(tmp_path):
    script = tmp_path / "0009_add_widgets_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (9, '0009_add_widgets_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 1, "違反": 0, "免除": 0, "対象外": 0}


def test_synthetic_script_missing_on_conflict_is_違反(tmp_path):
    script = tmp_path / "0010_add_gadgets_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (10, '0010_add_gadgets_upgrade.sql');\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_zero_padded_string_literal_is_違反_not_適合(tmp_path):
    """Design D-3 (d): "ゼロ埋め文字列は不適合" -- a script whose only
    occurrence of its own number is the zero-padded STRING literal
    `'0011'` (never the bare integer `11`) must be 違反, even though
    `ON CONFLICT` is present."""
    script = tmp_path / "0011_add_sprockets_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES ('0011', '0011_add_sprockets_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_non_matching_filename_is_対象外(tmp_path):
    (tmp_path / "0012_provision_something.sql").write_text("-- not a per-application upgrade script\n")
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 0, "免除": 0, "対象外": 1}


def test_synthetic_allow_listed_number_is_免除_even_without_a_ledger_insert(tmp_path):
    (tmp_path / "0006_legacy_upgrade.sql").write_text("-- ships without a ledger INSERT; grandfathered\n")
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset({6}), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 0, "免除": 1, "対象外": 0}


def test_name_re_requires_the_upgrade_suffix():
    """完了条件 5 (命名規範): `NNNN_<name>_upgrade.sql` に一致しないファ
    イルは対象外である -- `_upgrade` を落とした同じ番号のファイル名は
    一致しない。"""
    assert NAME_RE.match("0009_add_widgets_upgrade.sql")
    assert not NAME_RE.match("0009_add_widgets.sql")
    assert not NAME_RE.match("0009_provision_application.sql")


# ---------------------------------------------------------------------------
# Rework round fixtures (work order §4 WP-0 差し戻し指示 1(a)-(e); code
# review round 1, Opus, mutation-tested): pins that the comment/string
# handling `_strip_sql_comments` / `_iter_ledger_statements` add is
# actually exercised, one behavior per fixture.
# ---------------------------------------------------------------------------


def test_synthetic_ledger_insert_inside_a_line_comment_is_違反(tmp_path):
    """差し戻し指示 1(a): a script whose ONLY appearance of a ledger
    `INSERT` is inside a `--` line comment must be 違反 -- a commented-out
    statement was never actually executed, so it must not count as 適合
    (the first-pass scanner, which did not strip comments before
    scanning, misjudged this case 適合 -- see review-wp0.log's own probe
    output, case A)."""
    script = tmp_path / "0013_add_thingies_upgrade.sql"
    script.write_text(
        "-- INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "-- VALUES (13, '0013_add_thingies_upgrade.sql') ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_ledger_insert_inside_a_block_comment_is_違反(tmp_path):
    """差し戻し指示 1(b): the `/* ... */` form of the same case above."""
    script = tmp_path / "0014_add_gizmos_upgrade.sql"
    script.write_text(
        "/*\n"
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (14, '0014_add_gizmos_upgrade.sql') ON CONFLICT (upgrade_number) DO NOTHING;\n"
        "*/\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_inline_comment_containing_a_semicolon_is_still_適合(tmp_path):
    """差し戻し指示 1(c): a REAL, conforming statement whose OWN inline
    `--` comment (BEFORE the statement's own terminating `;`) itself
    contains a semicolon must still be 適合 -- the first-pass scanner's
    non-greedy `.*?;` statement search stopped at the `;` inside the
    comment, truncating the match before `ON CONFLICT` and misjudging
    this case 違反 (review-wp0.log's own probe output, case B)."""
    script = tmp_path / "0015_add_widgets_two_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "-- note: the legacy value was 12; that upgrade has since been retired\n"
        "VALUES (15, '0015_add_widgets_two_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 1, "違反": 0, "免除": 0, "対象外": 0}


def test_synthetic_string_literal_containing_a_semicolon_is_still_適合(tmp_path):
    """差し戻し指示 1(d): a REAL, conforming statement whose own string
    literal (a `script_name` value, here) contains a semicolon must still
    be 適合 -- the same non-greedy `.*?;` bug as case (c) above, but
    triggered by a string literal instead of a comment (review-wp0.log's
    own probe output, case B2)."""
    script = tmp_path / "0016_add_gadgets_two_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (16, '0016_add_gadgets_two_upgrade.sql; see the deployment runbook')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 1, "違反": 0, "免除": 0, "対象外": 0}


def test_synthetic_lowercase_statement_keywords_are_still_適合(tmp_path):
    """差し戻し指示 1(e) / レビュー指摘 7 (`re.IGNORECASE` was unpinned): a
    script written entirely in lowercase SQL keywords (`insert into`,
    `values`, `on conflict`, `do nothing`) must still be 適合 -- pins that
    the case-insensitive matching this scanner has always relied on
    stays in place, rather than being silently dropped in a future
    edit."""
    script = tmp_path / "0017_add_sprockets_two_upgrade.sql"
    script.write_text(
        "insert into public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "values (17, '0017_add_sprockets_two_upgrade.sql')\n"
        "on conflict (upgrade_number) do nothing;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 1, "違反": 0, "免除": 0, "対象外": 0}


def test_synthetic_insert_into_the_sibling_peers_ledger_table_is_違反(tmp_path):
    """裁定 C (監査 設計疑義 乙): a script that ledger-INSERTs into the
    SIBLING peer's table name (`_mdb_platform_upgrades`, never this
    peer's own `LEDGER_TABLE_NAME`) must be 違反 under THIS peer's own
    scan -- the scanner is parameterized by ledger table name precisely
    so a copy-pasted script naming the wrong peer's table is caught, not
    silently accepted as if the table name were peer-agnostic."""
    script = tmp_path / "0018_add_widgets_three_upgrade.sql"
    script.write_text(
        "INSERT INTO public._mdb_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (18, '0018_add_widgets_three_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


# ---------------------------------------------------------------------------
# WP-0 最終追補 fixtures (supervisor ruling 2026-09-05, 裁定 2/3,
# audit-wp0-delta.log §6 (1)/(2)): the independent acceptance-audit
# mutation found `_strip_sql_comments`'s own string-literal tracking
# unpinned (no fixture exercised a `--` INSIDE a string literal at all),
# and `scan_platform_upgrade_ledger_script`'s own-number search unstripped
# of string-literal content (design 疑義 1, adopted 乙 above).
# ---------------------------------------------------------------------------


def test_synthetic_string_literal_containing_a_double_dash_is_still_適合(tmp_path):
    """裁定 2 (audit-wp0-delta.log §6 (1)): `_strip_sql_comments` must
    never treat a `--` INSIDE a single-quoted string literal as the start
    of a `--` line comment -- a conforming statement whose `script_name`
    string value happens to contain the two-character substring `--` (a
    plausible descriptive dash, not a comment marker) must still be 適合.
    The audit found this behavior UNPINNED: disabling the tracking
    (`if ch == "'":` -> `if ch == "'" and False:`) left every existing
    test in this file green (58 passed, 4 xfailed) because no fixture
    exercised a string literal containing `--` at all -- this fixture
    closes that gap. Written on a single line (no comment-stripping-safe
    newline between the `--` and `ON CONFLICT`) so the mutation's naive
    strip-to-end-of-line would swallow `ON CONFLICT` itself, misjudging
    this case 違反 instead of leaving it merely truncated but still
    passing."""
    script = tmp_path / "0019_add_widgets_four_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name) "
        "VALUES (19, 'a -- b') ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 1, "違反": 0, "免除": 0, "対象外": 0}


def test_synthetic_own_number_only_inside_a_string_literal_is_違反(tmp_path):
    """裁定 3 (design 疑義 1, adopted 乙; audit-wp0-delta.log §6 (2)):
    `scan_platform_upgrade_ledger_script` strips string-literal CONTENT
    before matching the own-number bare-integer literal -- symmetric with
    the sibling `template_seed_numbers`, which already calls
    `_strip_string_literals` before its own digit scan (design D-3 (d)
    regulation (b) says "自番号の整数リテラル", and a digit sequence
    appearing only inside a string value is not an integer literal at
    all). Before this fix, `VALUES ('x', 'note 9 here') ON CONFLICT ...`
    was misjudged 適合 for `own_number=9` -- the search covered the whole
    statement text, quotes included."""
    script = tmp_path / "0009_note_literal_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES ('x', 'note 9 here')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_bare_digit_collision_is_違反(tmp_path):
    """Supervisor addendum (WP-0 final, 2026-09-05): the digit-boundary
    lookarounds in `own_literal_re` are load-bearing on their own -- a
    script numbered `0001` whose only bare integer literal is `19` (which
    CONTAINS the digit `1`) must be 違反. Without the boundaries the
    substring match would call it 適合. The string-literal strip cannot
    protect this case because `19` is a bare integer, not a quoted value."""
    script = tmp_path / "0001_bare_digit_collision_upgrade.sql"
    script.write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (19, 'collision')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    result = _classify_migrations_dir(tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 0, "違反": 1, "免除": 0, "対象外": 0}


def test_synthetic_three_way_match_concordant_and_discordant_sets(tmp_path):
    """完了条件 7 (三者一致), 裁定 A: exercises the REAL extraction logic
    (`_classify_migrations_dir`'s own `applicable_numbers`, and
    `template_seed_numbers`) against a synthetic `migrations/` directory
    standing in for the real one (whose own per-application upgrade
    script and `platform_upgrades` package constant do not exist until
    WP-3), rather than three hand-written literal sets (the first pass of
    this test asserted `{9} == {9} == {9}` as bare literals and executed
    NONE of the scanner's own code -- audit finding, §2 (i))."""
    (tmp_path / "0009_add_widgets_upgrade.sql").write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (9, '0009_add_widgets_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    (tmp_path / "0010_add_gadgets_upgrade.sql").write_text(
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (10, '0010_add_gadgets_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    script_numbers = _classify_migrations_dir(
        tmp_path, allow_list=frozenset(), ledger_table_name=LEDGER_TABLE_NAME
    ).applicable_numbers

    concordant_template_text = (
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (9, '0009_add_widgets_upgrade.sql'), (10, '0010_add_gadgets_upgrade.sql')\n"
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    concordant_seed_numbers = template_seed_numbers(concordant_template_text, LEDGER_TABLE_NAME)
    concordant_package_constant_numbers = frozenset({9, 10})
    assert script_numbers == concordant_seed_numbers == concordant_package_constant_numbers == frozenset({9, 10})

    discordant_template_text = (
        "INSERT INTO public._r2db_platform_upgrades (upgrade_number, script_name)\n"
        "VALUES (9, '0009_add_widgets_upgrade.sql')\n"  # forgot to also seed 10
        "ON CONFLICT (upgrade_number) DO NOTHING;\n"
    )
    discordant_seed_numbers = template_seed_numbers(discordant_template_text, LEDGER_TABLE_NAME)
    assert not (script_numbers == discordant_seed_numbers == concordant_package_constant_numbers)


# ===========================================================================
# Real migrations/ (r2db-api/migrations, this peer only) -- design D-3
# (d): "各 peer のテストは自 peer の migrations/ だけを走査する。"
# ===========================================================================


def test_real_migrations_dir_has_zero_violations_and_the_expected_exemptions():
    """完了条件 6: 実 `migrations/` に対して 違反 0 かつ 免除 = r2db 空
    (`ALLOW_LIST_NUMBERS` が空集合であるとおり -- r2db に `0006` 相当の
    出荷済み免除対象は無い)。

    陳腐化 docstring 訂正 (監査 2026-09-05 証拠不足の指摘): この docstring
    はかつて「現時点で per-application upgrade script は 1 つも無いので、
    走査対象はすべて対象外になる」と書いていたが、WP-3 で `0009_platform_
    upgrades_ledger_upgrade.sql` が出荷された今、実測は
    `{'適合': 1, '違反': 0, '免除': 0, '対象外': 8}` (`0001`-`0008` の
    8 本の platform 単発 migration が対象外、`0009` だけが適合) であり、
    「対象がすべて対象外」はもう成立しない。本テスト自身が検査するのは
    違反 0 と免除の集合だけであり、適合 >= 1 の実測は `test_real_
    migrations_dir_has_at_least_one_conforming_script` が別途行う (完了
    条件 8) -- この docstring は実測値を逐語で記録するにとどめる。

    Phase 9 WP-2a で `0010_field_constraints_upgrade.sql` が加わり、実測は
    `{'適合': 2, '違反': 0, '免除': 0, '対象外': 8}` に更新された (`0009`/
    `0010` の 2 本が適合)。

    Phase 9 WP-2c で `0011_idempotency_records_upgrade.sql` が加わり、実測
    は `{'適合': 3, '違反': 0, '免除': 0, '対象外': 8}` に更新された
    (`0009`/`0010`/`0011` の 3 本が適合)。

    Phase 10 WP-6a で `0012_process_ceilings.sql` が加わり (platform 単発
    -- `_upgrade.sql` で終わらない命名、design D-5(ii))、実測は
    `{'適合': 3, '違反': 0, '免除': 0, '対象外': 9}` に更新された (対象外が
    8 -> 9; 適合の 3 本は不変)。

    Phase 10 WP-4f で `0013_role_connection_limits.sql` が加わり (platform
    単発 -- `_upgrade.sql` で終わらない命名、supervisor ruling
    2026-09-09)、実測は `{'適合': 3, '違反': 0, '免除': 0, '対象外': 10}`
    に更新された (対象外が 9 -> 10; 適合の 3 本は不変)。

    R-56 WP-1 で `0014_auditreader_statement_timeout.sql` が加わり
    (platform 単発 -- `_upgrade.sql` で終わらない命名)、実測は
    `{'適合': 3, '違反': 0, '免除': 0, '対象外': 11}` に更新された (対象外
    が 10 -> 11; 適合の 3 本は不変)。"""
    result = _classify_migrations_dir(MIGRATIONS_DIR, ALLOW_LIST_NUMBERS, LEDGER_TABLE_NAME)
    assert result.tally == {"適合": 3, "違反": 0, "免除": 0, "対象外": 11}
    assert result.exempted_numbers == ALLOW_LIST_NUMBERS == frozenset()


def test_naming_convention_excludes_every_current_platform_single_shot_migration():
    """完了条件 5 (WP-3 で改訂 -- `0009_platform_upgrades_ledger_upgrade.
    sql` が実 per-application upgrade script として加わったため、「`NAME_
    RE` に一致するファイルが 1 つも無い」という WP-0 時点の主張はもう成立
    しない): platform 単発 migration (`0001`-`0008`、Phase 10 WP-6a で加
    わった `0012`) はどれもこの命名を使っていないこと -- `NAME_RE` に一致
    するのは正当な per-application upgrade script (`0009`、Phase 9 WP-2a
    で加わった `0010`、WP-2c で加わった `0011`) だけであること。"""
    matching = {p.name for p in MIGRATIONS_DIR.glob("*.sql") if NAME_RE.match(p.name)}
    assert matching == {"0009_platform_upgrades_ledger_upgrade.sql", "0010_field_constraints_upgrade.sql", "0011_idempotency_records_upgrade.sql"}
    platform_single_shot_migrations = (
        "0001_bootstrap_control_plane.sql",
        "0002_provisioning_functions.sql",
        "0003_provision_application.sql",
        "0004_deprovision_application.sql",
        "0005_credential_store.sql",
        "0006_control_plane_http.sql",
        "0007_application_audit.sql",
        "0008_platform_declarations_and_writer_timeouts.sql",
        "0012_process_ceilings.sql",
        "0013_role_connection_limits.sql",
        "0014_auditreader_statement_timeout.sql",
    )
    for name in platform_single_shot_migrations:
        assert name not in matching, f"{name} incorrectly matches the per-application upgrade naming convention"


def test_real_migrations_dir_has_at_least_one_conforming_script():
    """完了条件 8/13 (WP-0 の `xfail(strict=True)` を本 WP-3 と同一コミッ
    トで撤去 -- design §10 / work order §4 WP-0 完了条件 8): `0009_
    platform_upgrades_ledger_upgrade.sql` が実 `migrations/` に加わり、
    適合 >= 1 が実際に成立する。"""
    result = _classify_migrations_dir(MIGRATIONS_DIR, ALLOW_LIST_NUMBERS, LEDGER_TABLE_NAME)
    assert result.tally["適合"] >= 1


def test_real_migrations_three_way_match():
    """完了条件 7/12 (WP-0 の `xfail(strict=True)` を本 WP-3 と同一コミッ
    トで撤去 -- design §10 / work order §4 WP-0 完了条件 7): {`*_upgrade.
    sql` の番号集合} == {テンプレート `0003` の seed 集合} == {`r2db_api.
    platform_upgrades.PLATFORM_UPGRADE_NUMBERS`} が実際に成立する。"""
    import importlib

    script_numbers = _classify_migrations_dir(MIGRATIONS_DIR, ALLOW_LIST_NUMBERS, LEDGER_TABLE_NAME).applicable_numbers

    template_text = (MIGRATIONS_DIR / "0003_provision_application.sql").read_text(encoding="utf-8")
    seed_numbers = template_seed_numbers(template_text, LEDGER_TABLE_NAME)

    platform_upgrades = importlib.import_module("r2db_api.platform_upgrades")
    package_numbers = frozenset(platform_upgrades.PLATFORM_UPGRADE_NUMBERS)

    assert script_numbers == seed_numbers == package_numbers


# ===========================================================================
# L-3 (supervisor ruling 2026-09-05, review): a PG-INDEPENDENT pin of the
# F-12 message text (design §3.8), mirroring MitateDB-api's own `test_
# platform_upgrades.py::test_f12_message_matches_design_section_3_8_
# verbatim` -- r2db previously pinned F-12 only against a REAL PostgreSQL
# server (`tests/test_postgres.py::test_verify_platform_upgrades_applied_
# raises_service_unavailable_when_a_number_is_missing`) or via the cross-
# peer isomorphism table (which pins the FUNCTION BODY of `_f12_message`,
# never the text `require_application_upgrades_applied` actually raises
# for THIS peer's own `PLATFORM_UPGRADE_NUMBERS`). This test needs no
# database at all -- a minimal fake `psycopg.Connection` stand-in whose
# own ledger table does not exist is enough to exercise `require_
# application_upgrades_applied`'s pure control flow end to end.
# ===========================================================================


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        import psycopg

        raise psycopg.errors.UndefinedTable("relation does not exist")


class _FakeConnMissingLedger:
    """A minimal stand-in for a `psycopg.Connection` whose own ledger
    table does not exist -- used only to exercise `require_application_
    upgrades_applied`'s pure control flow (no real PostgreSQL round trip
    needed for THIS particular case, which is also covered against a
    real server in `tests/test_postgres.py`)."""

    def cursor(self):
        return _FakeCursor()

    def rollback(self):
        pass


def test_f12_message_matches_design_section_3_8_verbatim():
    """設計 §3.8 F-12 の骨子を逐語で assert する (常設規律 4) -- PG 非
    依存 (L-3, supervisor ruling 2026-09-05, review)。番号列挙・`ops
    upgrade-applications`・`--dry-run` の案内をすべて含み、DSN・資格情報
    ・内部ホスト名・宣言値を含まない (SI-10)。"""
    import importlib

    platform_upgrades = importlib.import_module("r2db_api.platform_upgrades")

    try:
        platform_upgrades.require_application_upgrades_applied(
            _FakeConnMissingLedger(),
            ledger_table_name=platform_upgrades.LEDGER_TABLE_NAME,
            expected=platform_upgrades.PLATFORM_UPGRADE_NUMBERS,
            application_id="acme",
            ops_module=platform_upgrades.PEER_MODULE,
        )
    except platform_upgrades.PlatformUpgradeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected PlatformUpgradeError")
    assert message == (
        "This application's storage is missing platform upgrade(s) 9, 10, 11: the deployment must apply them "
        "before this application can serve requests. Run 'python -m r2db_api.ops upgrade-applications "
        "--lock-timeout <value>' (its '--dry-run' shows applied and pending per application and requires "
        "the same '--lock-timeout'), then retry."
    )
    for forbidden in ("dsn", "DSN=", "password", "://", "host="):
        assert forbidden not in message
