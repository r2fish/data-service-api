"""R-66 WP-1 (design D-4, work order docs/work-orders/
WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_TIMEOUT_V1.md §2 完了条件 7):
static (no real PostgreSQL) checks pinning
`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`'s own migration
invocation list, order, and `max_connections` precondition literals.

(i) and (ii) both work from the SAME extraction -- `_extract_invocation_
migration_numbers` below finds only lines that are actual `psql`
invocations (`-f "..."` or `\\i ...`) naming a real
`<4 digits>_..._....sql` migration file, skipping every comment line
first (design D-4's own "コメント行を除いたもの") -- Step 3's own header
comment names `0004`/`0009`/`0013` in prose, never in this shape, so a
naive whole-file grep for those numbers would find false matches the
comment block alone accounts for (design D-4 (i)'s own rationale)."""
from __future__ import annotations

import re
from pathlib import Path

from r2db_api.platform_upgrades import PLATFORM_UPGRADE_NUMBERS

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "deploy" / "scripts" / "part1_provision_host_and_db.sh"
PART1A_PATH = Path(__file__).resolve().parents[1] / "deploy" / "scripts" / "part1a_check_max_connections.sh"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

#: The `\i` form appears in the script's SOURCE as TWO literal backslash
#: characters (`\\i`) -- it lives inside a bash double-quoted string
#: (`"\\i ..."`), and bash's own double-quote escaping collapses `\\` to
#: one backslash before psql ever sees it (`od -c` on the source line
#: confirms two literal `\` bytes before `i`). This regex matches the
#: SOURCE form, not the runtime value.
_INVOCATION_RE = re.compile(r'(?:-f\s+"|\\\\i\s+)\$\{[A-Z0-9_]+\}/(\d{4})_[A-Za-z0-9_]+\.sql')

#: design D-4 (i): the migrations `part1_provision_host_and_db.sh` never
#: applies via a `psql -f`/`\i` invocation of its own -- `0004` (operator-
#: run teardown, never onboarding) plus every per-application upgrade
#: script (`platform_upgrades.PLATFORM_UPGRADE_NUMBERS`, applied instead by
#: `ops upgrade-applications`, this script's own Step 5).
EXPECTED_EXCLUDED_MIGRATION_NUMBERS: frozenset[int] = PLATFORM_UPGRADE_NUMBERS | {4}

#: design D-4 (ii): the literal migration sequence spelled out in the
#: prose immediately following runbook §5's own "Order of operations"
#: fenced code block (that block itself only shows steps 1-3, `0001`/
#: `0002`/`0003`) -- the positional order `part1_provision_host_and_db.sh`'s
#: own `-f`/`\i` invocations must appear in.
EXPECTED_INVOCATION_ORDER = ("0001", "0002", "0005", "0006", "0007", "0013", "0014", "0008", "0012", "0003")


def _strip_comment_lines(text: str) -> str:
    """Drops every line whose first non-whitespace character is `#`
    (design D-4's own "コメント行を除いたもの") -- a trailing inline
    comment on an otherwise-live line is not stripped, matching how this
    script never puts a real `-f`/`\\i` invocation after a `#` on the same
    line anyway."""
    kept = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _extract_invocation_migration_numbers(script_text: str) -> list[str]:
    live_text = _strip_comment_lines(script_text)
    numbers = []
    for line in live_text.splitlines():
        if "-f " not in line and "\\i " not in line:
            continue
        match = _INVOCATION_RE.search(line)
        if match is not None:
            numbers.append(match.group(1))
    return numbers


def test_excluded_migration_set_matches_platform_upgrade_numbers_plus_deprovision() -> None:
    """Design D-4 (i)'s own drift guard: the excluded set this test file
    hardcodes above must equal `platform_upgrades.PLATFORM_UPGRADE_NUMBERS
    | {4}` -- a future per-application upgrade script (a new
    `0015_..._upgrade.sql`) changes `PLATFORM_UPGRADE_NUMBERS`, and this
    assertion is what keeps `EXPECTED_EXCLUDED_MIGRATION_NUMBERS` from
    silently drifting out of sync with it, so the completeness check below
    stays meaningful instead of accidentally excluding a real platform
    migration."""
    assert EXPECTED_EXCLUDED_MIGRATION_NUMBERS == PLATFORM_UPGRADE_NUMBERS | {4}


def test_every_platform_migration_appears_in_the_scripts_invocation_list() -> None:
    """Design D-4 (i): every real migration file under `migrations/`,
    except the explicit exclusion set above, must be one of this script's
    own `-f`/`\\i` invocations. Non-vacuous: `real_migration_numbers` below
    is asserted non-empty first, so a a broken glob (e.g. an emptied
    MIGRATIONS_DIR) cannot make the main assertion pass by finding nothing
    to check at all. If a future platform migration (`0015_...`, not a
    per-application upgrade script) is added to `migrations/` but never
    wired into this script, THIS is the test that goes red -- see the
    module-level `EXPECTED_EXCLUDED_MIGRATION_NUMBERS` docstring for why a
    genuine per-application upgrade script does not (per-application
    upgrade is applied by `ops upgrade-applications`, never added to this
    script's own `psql -f` invocations)."""
    name_re = re.compile(r"^(\d{4})_")
    real_migration_numbers = {int(m.group(1)) for path in MIGRATIONS_DIR.glob("*.sql") if (m := name_re.match(path.name))}
    assert real_migration_numbers, "no migration files found under r2db-api/migrations/ -- MIGRATIONS_DIR is likely wrong"

    invoked_numbers = {int(n) for n in _extract_invocation_migration_numbers(SCRIPT_PATH.read_text())}
    expected_numbers = real_migration_numbers - EXPECTED_EXCLUDED_MIGRATION_NUMBERS
    missing = expected_numbers - invoked_numbers
    assert not missing, (
        f"migration(s) {sorted(missing)} exist under r2db-api/migrations/ but part1_provision_host_and_db.sh "
        "never applies them via a psql -f/\\i invocation, and they are not in the excluded set (0004, plus every "
        "per-application upgrade in platform_upgrades.PLATFORM_UPGRADE_NUMBERS -- per-application upgrade is "
        "applied by `ops upgrade-applications` [the script's own Step 5], not added to this script's own psql -f "
        "invocations)."
    )


def test_invocation_order_matches_runbook_section_5() -> None:
    """Design D-4 (ii): the positional order of every `-f`/`\\i` invocation
    in `part1_provision_host_and_db.sh` matches the literal migration
    sequence spelled out in the PROSE paragraph immediately following
    runbook §5's own "Order of operations" fenced code block -- code
    review 1 低2/低3: that fenced block itself (`POSTGRES_PROVISIONING_
    RUNBOOK.md` §5, steps 1-3) only shows `0001`/`0002`/`0003`; the full
    platform-migration sequence this WP reorders (0013 right after 0007,
    before 0014; R-66 WP-1's own fix -- previously 0013 was never invoked
    at all) lives in the paragraph right after that block, not in the code
    block itself."""
    invoked_order = tuple(_extract_invocation_migration_numbers(SCRIPT_PATH.read_text()))
    assert invoked_order == EXPECTED_INVOCATION_ORDER


def _connection_limit_after(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    assert match is not None, f"pattern not found: {pattern}"
    return int(match.group(1))


def test_part1a_literals_98_and_72_recompute_from_migration_connection_limits() -> None:
    """Design D-4 (iii): `part1a_check_max_connections.sh`'s own literal
    `98`/`72` (the platform-baseline / per-application connection
    constants D-2 defines) are recomputed here directly from the
    `CONNECTION LIMIT` literals `0013_role_connection_limits.sql` (api 68,
    controlplane 20, runtime/developer 36 each), `0001_bootstrap_control_
    plane.sql` (control 5), and `0007_application_audit.sql` (auditreader
    5) actually carry -- 98 = 68 + 20 + 5 + 5, 72 = 36 + 36."""
    sql_0013 = (MIGRATIONS_DIR / "0013_role_connection_limits.sql").read_text()
    sql_0001 = (MIGRATIONS_DIR / "0001_bootstrap_control_plane.sql").read_text()
    sql_0007 = (MIGRATIONS_DIR / "0007_application_audit.sql").read_text()

    api_limit = _connection_limit_after(r"ALTER ROLE r2dbsvc_api CONNECTION LIMIT (\d+);", sql_0013)
    controlplane_limit = _connection_limit_after(r"ALTER ROLE r2dbsvc_controlplane CONNECTION LIMIT (\d+);", sql_0013)
    runtime_limit = _connection_limit_after(r"CONNECTION LIMIT (\d+)', app\.runtime_role\)", sql_0013)
    developer_limit = _connection_limit_after(r"CONNECTION LIMIT (\d+)', app\.developer_role\)", sql_0013)
    control_limit = _connection_limit_after(r"CREATE ROLE r2dbsvc_control .*CONNECTION LIMIT (\d+)'", sql_0001)
    auditreader_limit = _connection_limit_after(r"CREATE ROLE r2dbsvc_auditreader .*CONNECTION LIMIT (\d+)'", sql_0007)

    recomputed_platform_baseline = api_limit + controlplane_limit + control_limit + auditreader_limit
    recomputed_per_application = runtime_limit + developer_limit

    part1a_text = PART1A_PATH.read_text()
    literal_platform_baseline = _connection_limit_after(r"PLATFORM_BASELINE_CONNECTIONS=(\d+)", part1a_text)
    literal_per_application = _connection_limit_after(r"PER_APPLICATION_CONNECTIONS=(\d+)", part1a_text)

    assert literal_platform_baseline == recomputed_platform_baseline == 98
    assert literal_per_application == recomputed_per_application == 72


def test_part1a_is_called_right_after_0002_and_before_0005() -> None:
    """Design D-4 (iv): the line calling `part1a_check_max_connections.sh`
    appears AFTER the `0002_provisioning_functions.sql` invocation line AND
    before the `0005_credential_store.sql` invocation line (design D-2's
    own "位置": right after `0002`, before `0005`). Code review 1 中4: the
    previous version of this test only asserted the "before 0005" half --
    a mutation moving the call to before `0001` (too early, never right
    after `0002`) would have satisfied that half alone without satisfying
    design D-2's own stated position; this version pins BOTH bounds."""
    lines = SCRIPT_PATH.read_text().splitlines()
    call_index = next(i for i, line in enumerate(lines) if "part1a_check_max_connections.sh" in line and line.strip().startswith('"$'))
    invocation_0002_index = next(i for i, line in enumerate(lines) if "0002_provisioning_functions.sql" in line and ("-f " in line or "\\i " in line))
    invocation_0005_index = next(i for i, line in enumerate(lines) if "0005_credential_store.sql" in line and ("-f " in line or "\\i " in line))
    assert invocation_0002_index < call_index < invocation_0005_index, (invocation_0002_index, call_index, invocation_0005_index)


def test_upgrade_applications_call_passes_lock_timeout() -> None:
    """WP-2 完了条件6 (コードレビュー1低8): `part1_provision_host_and_db.sh`
    の `ops upgrade-applications` 呼び出し**全件**が `--lock-timeout` を渡す
    (design D-7: 既定値の無い必須引数なので、これを欠くと script はその場で
    exit 2 になる)。最初の一致行だけでなく、コメント行を除いた本文の全
    invocation 行を見る -- 将来 2 本目の呼び出しが増えても、1 本目にだけ
    `--lock-timeout` があれば緑のままになる穴を塞ぐ。空振り禁止: 観測件数
    1 以上を assert する。"""
    live_lines = _strip_comment_lines(SCRIPT_PATH.read_text()).splitlines()
    call_lines = [line for line in live_lines if "upgrade-applications" in line and line.strip().startswith('"${OPS[@]}"')]
    assert call_lines, "no `\"${OPS[@]}\" upgrade-applications` invocation line found"
    for line in call_lines:
        assert "--lock-timeout" in line, line
