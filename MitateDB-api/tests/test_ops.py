"""`python -m mitatedb_api.ops` (design v1.2 R-6, WP-5 flip) -- direct,
real-subprocess tests.

No other test file exercises this module as a subprocess (the HTTP
conformance adapter, `conformance_adapter_mitatedb_http.py`, is the only
OTHER caller, and it treats the CLI as an opaque black box for its own
condition-test purposes). This file's own job is the CLI's *external
contract* directly: exit codes, stdout/stderr shape, the declare-and-echo
gate's own two-step protocol, and that state changes really land in
PostgreSQL (including the accompanying `control_audit` row, same
transaction).

Uses `control_plane_harness.py`'s shared throwaway-platform fixture (same
convention `test_control_ceremony.py`/`test_control_plane_postgres.py`
already use for their own PostgreSQL-backed tests).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from .control_plane_harness import control_platform  # noqa: F401 (fixture)
from mitatedb_api.control_credential_store_postgres import PostgresControlCredentialStore
from mitatedb_api.control_plane import (ControlPlaneLimits, ControlPlaneService, PostgresApplicationRegistry,
                                        PostgresControlBackend, PostgresCredentialRegistry,
                                        bootstrap_control_credential)

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_APP_PEPPER = "ops-cli-test-app-pepper-0000000000"
_CONTROL_PEPPER = "ops-cli-test-control-pepper-0000000"


def _run_ops(control_platform, *args: str, control_pepper: str = _CONTROL_PEPPER,
             app_pepper: "str | None" = _APP_PEPPER, actor_credential_id: "str | None" = None,
             actor_secret: "str | None" = None, provision_dsn: "str | None" = None,
             migrations_dir: "Path | None" = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env["MITATEDB_CONTROLPLANE_DSN"] = control_platform.controlplane_dsn
    env["MITATEDB_PLATFORM_SCHEMA"] = control_platform.registry_schema
    # Q4 phase (design D-2, work order §4 WP-2 変更対象 D): `MITATEDB_
    # DATA_BASE_URL`/`MITATEDB_CONTROL_BASE_URL` are REMOVED env vars
    # (F-2, rejected whenever defined) -- `surfaces` now comes from
    # `<registry>.platform_declarations`, already seeded (both `data`/
    # `control`) by `control_plane_harness.bootstrap_control_platform`.
    # Explicitly unset here in case the PARENT `os.environ` this dict is
    # copied from happens to carry either (a real deployment's own shell,
    # say) -- this subprocess must observe the SAME F-2 rejection any
    # other caller does, not a silently-inherited leftover.
    env.pop("MITATEDB_DATA_BASE_URL", None)
    env.pop("MITATEDB_CONTROL_BASE_URL", None)
    env.pop("MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS", None)
    env.pop("MITATEDB_AUDIT_IDLE_TIMEOUT_MS", None)
    if control_pepper is not None:
        env["MITATEDB_CONTROL_CREDENTIAL_PEPPER"] = control_pepper
    else:
        env.pop("MITATEDB_CONTROL_CREDENTIAL_PEPPER", None)
    if app_pepper is not None:
        env["MITATEDB_CREDENTIAL_PEPPER"] = app_pepper
    else:
        env.pop("MITATEDB_CREDENTIAL_PEPPER", None)
    # WP-6 break-glass command family's own environment (ops.py::_actor_
    # credential/_provision_dsn/_migrations_dir) -- absent by default so the
    # pre-existing bootstrap/reset tests above are unaffected.
    if actor_credential_id is not None:
        env["MITATEDB_CONTROL_CREDENTIAL_ID"] = actor_credential_id
    else:
        env.pop("MITATEDB_CONTROL_CREDENTIAL_ID", None)
    if actor_secret is not None:
        # Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04,
        # 裁定 1): `ops.py::_actor_credential` requires `MITATEDB_CONTROL_
        # CREDENTIAL_SECRET` to hold the COMPOSED bearer (the exact
        # `secret:` value a real operator would have saved) -- this
        # module's own test callers (`_bootstrapped_actor`) already pass
        # that composed bearer directly, so it is set here VERBATIM, no
        # re-composition (this file never held the raw, unsplit secret
        # part separately from its own composed form).
        env["MITATEDB_CONTROL_CREDENTIAL_SECRET"] = actor_secret
    else:
        env.pop("MITATEDB_CONTROL_CREDENTIAL_SECRET", None)
    if provision_dsn is not None:
        env["MITATEDB_PROVISION_DSN"] = provision_dsn
    else:
        env.pop("MITATEDB_PROVISION_DSN", None)
    if migrations_dir is not None:
        env["MITATEDB_MIGRATIONS_DIR"] = str(migrations_dir)
    else:
        env.pop("MITATEDB_MIGRATIONS_DIR", None)
    return subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", *args], capture_output=True, text=True, env=env)


def _parse_issued(stdout: str) -> tuple[str, str]:
    credential_id = secret = None
    for line in stdout.splitlines():
        if line.startswith("credential_id: "):
            credential_id = line[len("credential_id: "):].strip()
        elif line.startswith("secret: "):
            secret = line[len("secret: "):].strip()
    assert credential_id and secret, f"could not parse stdout: {stdout!r}"
    return credential_id, secret


def _control_credentials_rows(control_platform) -> list[tuple]:
    statement = sql.SQL("SELECT credential_id, enabled, revoked, must_rotate FROM {table} ORDER BY issued_at").format(
        table=sql.Identifier(control_platform.registry_schema, "control_credentials"))
    with psycopg.connect(control_platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement)
            return cur.fetchall()


def _control_audit_rows(control_platform) -> list[tuple]:
    statement = sql.SQL("SELECT operation, outcome, actor_type FROM {table} ORDER BY audit_seq").format(
        table=sql.Identifier(control_platform.registry_schema, "control_audit"))
    with psycopg.connect(control_platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement)
            return cur.fetchall()


@pytest.fixture(autouse=True)
def _clean_control_credentials(control_platform):
    """Each test in this file gets a clean `applications`/`credentials`/
    `control_credentials`/`control_audit` slate -- module-scoped
    `control_platform` is shared with every OTHER test function here, and
    `bootstrap`'s own CONFLICT refusal (correctly) depends on prior state.
    WP-6: `applications`/`credentials` joined this cleanup alongside the
    pre-existing two tables once the break-glass command family's own
    tests below started registering applications/issuing credentials
    (`credentials` is deleted before `applications` -- the same FK-safe
    order `test_control_plane_postgres.py::backend`'s own teardown uses)."""
    with psycopg.connect(control_platform.provision_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {control_platform.registry_schema}.credentials")
            cur.execute(f"DELETE FROM {control_platform.registry_schema}.control_credentials")
            cur.execute(f"DELETE FROM {control_platform.registry_schema}.applications")
            cur.execute(f"DELETE FROM {control_platform.registry_schema}.control_audit")
    yield


@pytest.fixture(scope="module")
def deprovision_script_dir(tmp_path_factory, control_platform) -> Path:
    """A copy of `0004_deprovision_application.sql` rewritten with this
    module's own throwaway prefix (R-4's prefix-replacement convention,
    identical to what `control_plane_harness.bootstrap_control_platform`
    already does for `0001`/`0002`) -- the CLI's own `deprovision`
    subcommand needs this because the UNMODIFIED script hardcodes the
    literal `mitatedb_registry` schema, which does not exist on this
    throwaway platform (only `{prefix}_registry` does). Pointed to via
    `MITATEDB_MIGRATIONS_DIR` (`ops.py::_migrations_dir`'s own documented
    override)."""
    out_dir = tmp_path_factory.mktemp("mitatedb_ops_deprovision_" + control_platform.prefix)
    text = (MIGRATIONS_DIR / "0004_deprovision_application.sql").read_text().replace(
        "mitatedb", control_platform.prefix)
    (out_dir / "0004_deprovision_application.sql").write_text(text)
    return out_dir


def _bootstrapped_actor(control_platform):
    """Bootstraps + self-rotates a real control credential directly against
    PostgreSQL (bypassing the CLI, mirroring `test_control_plane_postgres.
    py::_bootstrapped`) and returns `(service, credential_id, secret)` --
    this file's own break-glass subcommand tests use the resulting id/
    secret as `MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET` (exactly what a
    real operator's own already-rotated control credential provides), and
    use `service` directly (not the CLI) for setup calls this WP's break-
    glass scope deliberately excludes (`register_application`/`issue_
    credential` stay HTTP/in-band-only operations, design v1.2 §3 WP-6
    row's own six-command list)."""
    applications = PostgresApplicationRegistry(control_platform.controlplane_dsn, schema=control_platform.registry_schema)
    credentials = PostgresCredentialRegistry(control_platform.controlplane_dsn, pepper=_APP_PEPPER,
                                             schema=control_platform.registry_schema)
    control_credentials = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER,
                                                         schema=control_platform.registry_schema)
    backend = PostgresControlBackend(applications=applications, credentials=credentials,
                                     control_credentials=control_credentials,
                                     audit_schema=control_platform.registry_schema, dsn=control_platform.controlplane_dsn)
    with backend.unit_of_work() as work:
        credential_id, bearer = bootstrap_control_credential(control_credentials, backend.append_audit, work=work)
    service = ControlPlaneService(backend, limits=ControlPlaneLimits(
        applications=20, credentials_per_application=5, control_requests_per_minute=190))
    # Phase 6 WP-3 差し戻し 最終ラウンド (裁定 1): `PostgresControlCredentialStore.
    # authenticate` takes the FULL composed bearer -- passed straight
    # through, unsplit.
    secret = bearer
    rotated = service.rotate_credential(secret, credential_id)
    rotated_secret = rotated["secret"]
    return service, credential_id, rotated_secret


def test_bootstrap_issues_a_real_must_rotate_credential(control_platform) -> None:
    result = _run_ops(control_platform, "bootstrap")
    assert result.returncode == 0, result.stderr
    credential_id, secret = _parse_issued(result.stdout)
    assert "must_rotate: true" in result.stdout

    rows = _control_credentials_rows(control_platform)
    assert len(rows) == 1
    row_id, enabled, revoked, must_rotate = rows[0]
    assert row_id == credential_id
    assert enabled is True and revoked is False and must_rotate is True

    audit_rows = _control_audit_rows(control_platform)
    assert audit_rows == [("bootstrap_control_credential", "allow", "operator_cli")]


def test_bootstrap_refused_with_conflict_while_a_control_credential_exists(control_platform) -> None:
    first = _run_ops(control_platform, "bootstrap")
    assert first.returncode == 0, first.stderr

    second = _run_ops(control_platform, "bootstrap")
    assert second.returncode == 1
    body = json.loads(second.stderr.strip())
    assert body["code"] == "CONFLICT"

    # Refusing a second bootstrap must not touch state at all: still
    # exactly the one row/one audit event the first invocation created.
    assert len(_control_credentials_rows(control_platform)) == 1
    assert len(_control_audit_rows(control_platform)) == 1


def test_bootstrap_refused_with_conflict_even_when_the_only_row_is_revoked(control_platform) -> None:
    """Contract `control_plane.bootstrap`: "while a control credential
    exists" reads as row-existence, not "while an unrevoked one exists"
    (design v1.2 R-6, WP-4's own M-6 disposition)."""
    result = _run_ops(control_platform, "bootstrap")
    credential_id, _secret = _parse_issued(result.stdout)
    with psycopg.connect(control_platform.provision_dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {table} SET revoked = TRUE WHERE credential_id = {ph}").format(
                    table=sql.Identifier(control_platform.registry_schema, "control_credentials"),
                    ph=sql.Placeholder(),
                ),
                [credential_id],
            )

    second = _run_ops(control_platform, "bootstrap")
    assert second.returncode == 1
    assert json.loads(second.stderr.strip())["code"] == "CONFLICT"


def test_reset_without_confirm_declares_the_phrase_and_touches_nothing(control_platform) -> None:
    bootstrap_result = _run_ops(control_platform, "bootstrap")
    original_id, _secret = _parse_issued(bootstrap_result.stdout)

    denial = _run_ops(control_platform, "reset")
    assert denial.returncode == 2
    body = json.loads(denial.stderr.strip())
    assert body["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert body["details"]["required_confirmation"].startswith("RESET control_credentials @active=")
    assert body["details"]["consequence"]
    # An unconfirmed denial reads state (to compute the phrase) but must
    # write nothing: the original credential is still exactly as it was.
    rows = _control_credentials_rows(control_platform)
    assert len(rows) == 1 and rows[0][0] == original_id and rows[0][2] is False  # not revoked
    assert len(_control_audit_rows(control_platform)) == 1  # only the original bootstrap event


def test_reset_with_wrong_confirmation_is_also_refused_and_touches_nothing(control_platform) -> None:
    _run_ops(control_platform, "bootstrap")
    denial = _run_ops(control_platform, "reset", "--confirm", "not the right phrase at all")
    assert denial.returncode == 2
    assert json.loads(denial.stderr.strip())["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert len(_control_credentials_rows(control_platform)) == 1


def test_reset_with_the_echoed_phrase_revokes_everything_and_mints_one_new_credential(control_platform) -> None:
    bootstrap_result = _run_ops(control_platform, "bootstrap")
    original_id, _secret = _parse_issued(bootstrap_result.stdout)

    probe = _run_ops(control_platform, "reset")
    phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]

    confirmed = _run_ops(control_platform, "reset", "--confirm", phrase)
    assert confirmed.returncode == 0, confirmed.stderr
    new_id, new_secret = _parse_issued(confirmed.stdout)
    assert new_id != original_id
    assert "must_rotate: true" in confirmed.stdout

    rows = {row[0]: row for row in _control_credentials_rows(control_platform)}
    assert rows[original_id][2] is True  # revoked
    assert rows[new_id][1] is True and rows[new_id][2] is False and rows[new_id][3] is True  # enabled, not revoked, must_rotate

    audit_ops = [row[0] for row in _control_audit_rows(control_platform)]
    assert audit_ops == ["bootstrap_control_credential", "reset_control_credentials"]


def test_reset_bootstraps_from_empty_state_too(control_platform) -> None:
    """`reset` is also the recovery path when NO control credential has
    ever existed at all (not only the "revoke everything" case) -- the
    ceremony core's own `has_any()` check inside `reset_control_
    credentials` handles an empty table the same as a populated one."""
    probe = _run_ops(control_platform, "reset")
    assert probe.returncode == 2
    phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]
    # An empty active-id set still produces a real, deterministic phrase.
    assert phrase.startswith("RESET control_credentials @active=")

    confirmed = _run_ops(control_platform, "reset", "--confirm", phrase)
    assert confirmed.returncode == 0, confirmed.stderr
    assert len(_control_credentials_rows(control_platform)) == 1


def test_two_independent_bootstrap_runs_never_mint_the_same_secret(control_platform) -> None:
    first = _run_ops(control_platform, "bootstrap")
    _id1, secret1 = _parse_issued(first.stdout)
    probe = _run_ops(control_platform, "reset")
    phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]
    second = _run_ops(control_platform, "reset", "--confirm", phrase)
    _id2, secret2 = _parse_issued(second.stdout)
    assert secret1 != secret2


def test_missing_controlplane_dsn_dies_loudly(control_platform) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    env.pop("MITATEDB_CONTROLPLANE_DSN", None)
    env["MITATEDB_CONTROL_CREDENTIAL_PEPPER"] = _CONTROL_PEPPER
    result = subprocess.run(
        [sys.executable, "-m", "mitatedb_api.ops", "bootstrap"], capture_output=True, text=True, env=env)
    assert result.returncode == 2
    assert "MITATEDB_CONTROLPLANE_DSN is required" in result.stderr


def test_identical_peppers_are_refused_before_any_database_access(control_platform) -> None:
    same_pepper = "identical-pepper-value-used-for-both-0000"
    result = _run_ops(control_platform, "bootstrap", control_pepper=same_pepper, app_pepper=same_pepper)
    assert result.returncode == 2
    assert "pepper" in result.stderr.lower()
    # Refused before ever touching the platform database: still zero rows.
    assert _control_credentials_rows(control_platform) == []


# ===========================================================================
# WP-6 break-glass command family (design v1.2 §3 WP-6 row).
# ===========================================================================


def _run_bg(control_platform, actor_credential_id: str, actor_secret: str, *args: str,
            **kwargs) -> subprocess.CompletedProcess:
    return _run_ops(control_platform, *args, actor_credential_id=actor_credential_id,
                    actor_secret=actor_secret, **kwargs)


def test_list_applications_and_list_credentials_report_real_registry_state(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brklist1")
    issued = service.issue_credential(actor_secret, "brklist1", "runtime")

    apps = _run_bg(control_platform, actor_id, actor_secret, "list-applications")
    assert apps.returncode == 0, apps.stderr
    apps_body = json.loads(apps.stdout)
    assert {"application_id": "brklist1", "enabled": True} in apps_body["applications"]

    creds = _run_bg(control_platform, actor_id, actor_secret, "list-credentials")
    assert creds.returncode == 0, creds.stderr
    creds_body = json.loads(creds.stdout)
    by_id = {row["credential_id"]: row for row in creds_body["credentials"]}
    assert by_id[issued["credential_id"]]["application_id"] == "brklist1"
    assert by_id[issued["credential_id"]]["role"] == "runtime"
    assert by_id[issued["credential_id"]]["revoked"] is False
    # Contract's own mixed listing (R-6 m-6): the actor's own control
    # credential appears too, with no application_id key at all.
    assert by_id[actor_id]["role"] == "control"
    assert "application_id" not in by_id[actor_id]


def test_enable_and_disable_application_round_trip(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkapp1")

    disabled = _run_bg(control_platform, actor_id, actor_secret, "disable-application", "brkapp1")
    assert disabled.returncode == 0, disabled.stderr
    assert json.loads(disabled.stdout) == {"application_id": "brkapp1", "enabled": False}
    assert dict(service.list_applications(actor_secret)["applications"][0].items()) == {
        "application_id": "brkapp1", "enabled": False}

    enabled = _run_bg(control_platform, actor_id, actor_secret, "enable-application", "brkapp1")
    assert enabled.returncode == 0, enabled.stderr
    assert json.loads(enabled.stdout) == {"application_id": "brkapp1", "enabled": True}


def test_enable_and_disable_credential_round_trip(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkcred1")
    issued = service.issue_credential(actor_secret, "brkcred1", "runtime")
    target = issued["credential_id"]

    disabled = _run_bg(control_platform, actor_id, actor_secret, "disable-credential", target)
    assert disabled.returncode == 0, disabled.stderr
    assert json.loads(disabled.stdout) == {"credential_id": target, "enabled": False, "revoked": False}

    enabled = _run_bg(control_platform, actor_id, actor_secret, "enable-credential", target)
    assert enabled.returncode == 0, enabled.stderr
    assert json.loads(enabled.stdout) == {"credential_id": target, "enabled": True, "revoked": False}


def test_rotate_credential_replaces_the_secret_for_either_kind(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkrot1")
    issued = service.issue_credential(actor_secret, "brkrot1", "runtime")

    rotated = _run_bg(control_platform, actor_id, actor_secret, "rotate-credential", issued["credential_id"])
    assert rotated.returncode == 0, rotated.stderr
    new_id, new_secret = _parse_issued(rotated.stdout)
    assert new_id == issued["credential_id"]
    assert new_secret != issued["secret"]

    # Self-rotate (the actor's own control credential) also works -- the
    # exact mechanism that clears a freshly bootstrap/reset must_rotate
    # credential's own gate.
    self_rotated = _run_bg(control_platform, actor_id, actor_secret, "rotate-credential", actor_id)
    assert self_rotated.returncode == 0, self_rotated.stderr
    _rid, rotated_secret = _parse_issued(self_rotated.stdout)
    assert rotated_secret != actor_secret


def test_revoke_application_credential_needs_no_confirmation(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkrev1")
    issued = service.issue_credential(actor_secret, "brkrev1", "runtime")

    revoked = _run_bg(control_platform, actor_id, actor_secret, "revoke-credential", issued["credential_id"])
    assert revoked.returncode == 0, revoked.stderr
    assert json.loads(revoked.stdout)["revoked"] is True


def test_revoke_last_active_control_credential_requires_declare_and_echo(control_platform) -> None:
    """The core WP-6 gate this file's own completion condition #4 names:
    an unconfirmed/mismatched revoke of the operator's OWN (only active)
    control credential is refused and touches nothing; the echoed phrase
    from that refusal makes it succeed."""
    _service, actor_id, actor_secret = _bootstrapped_actor(control_platform)

    denial = _run_bg(control_platform, actor_id, actor_secret, "revoke-credential", actor_id)
    assert denial.returncode == 2
    body = json.loads(denial.stderr.strip())
    assert body["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert body["details"]["required_confirmation"].startswith(f"REVOKE control_credential {actor_id}")
    rows = {row[0]: row for row in _control_credentials_rows(control_platform)}
    assert rows[actor_id][2] is False  # not revoked -- the denial touched nothing

    wrong_result = _run_bg(control_platform, actor_id, actor_secret, "revoke-credential", actor_id, "--confirm",
                           "not the right phrase")
    assert wrong_result.returncode == 2
    assert json.loads(wrong_result.stderr.strip())["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    rows = {row[0]: row for row in _control_credentials_rows(control_platform)}
    assert rows[actor_id][2] is False

    phrase = body["details"]["required_confirmation"]
    confirmed = _run_bg(control_platform, actor_id, actor_secret, "revoke-credential", actor_id, "--confirm", phrase)
    assert confirmed.returncode == 0, confirmed.stderr
    assert json.loads(confirmed.stdout)["revoked"] is True
    rows = {row[0]: row for row in _control_credentials_rows(control_platform)}
    assert rows[actor_id][2] is True


def test_audit_report_prints_events_oldest_first_as_json_lines(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkaudit1")

    result = _run_ops(control_platform, "audit-report", provision_dsn=control_platform.provision_dsn)
    assert result.returncode == 0, result.stderr
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    operations = [line["operation"] for line in lines]
    # bootstrap, self-rotate, register_application -- in that order.
    assert operations == ["bootstrap_control_credential", "rotate_credential", "register_application"]
    assert all("event_id" in line and "occurred_at" in line for line in lines)


def test_audit_report_since_and_until_window_the_report(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkaudit2")

    far_future = _run_ops(control_platform, "audit-report", "--since", "2999-01-01T00:00:00Z",
                          provision_dsn=control_platform.provision_dsn)
    assert far_future.returncode == 0, far_future.stderr
    assert far_future.stdout.strip() == ""

    everything = _run_ops(control_platform, "audit-report", "--since", "2000-01-01T00:00:00Z",
                          provision_dsn=control_platform.provision_dsn)
    assert len(everything.stdout.splitlines()) == 3


def test_deprovision_without_confirm_declares_the_phrase_and_touches_nothing(
        control_platform, deprovision_script_dir) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkdep1")

    denial = _run_ops(control_platform, "deprovision", "brkdep1",
                      provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    assert denial.returncode == 2
    body = json.loads(denial.stderr.strip())
    assert body["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert body["details"]["required_confirmation"].startswith("DEPROVISION application brkdep1 @registered=")
    assert body["details"]["consequence"]
    # Untouched: the application is still registered.
    assert any(row["application_id"] == "brkdep1"
              for row in service.list_applications(actor_secret)["applications"])


def test_deprovision_with_wrong_confirmation_is_refused_and_touches_nothing(
        control_platform, deprovision_script_dir) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkdep2")

    denial = _run_ops(control_platform, "deprovision", "brkdep2", "--confirm", "not the right phrase",
                      provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    assert denial.returncode == 2
    assert json.loads(denial.stderr.strip())["code"] == "DESTRUCTIVE_CONFIRMATION_REQUIRED"
    assert any(row["application_id"] == "brkdep2"
              for row in service.list_applications(actor_secret)["applications"])


def test_deprovision_with_the_echoed_phrase_removes_the_registration(
        control_platform, deprovision_script_dir) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "brkdep3")
    issued = service.issue_credential(actor_secret, "brkdep3", "runtime")

    probe = _run_ops(control_platform, "deprovision", "brkdep3",
                     provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    phrase = json.loads(probe.stderr.strip())["details"]["required_confirmation"]

    confirmed = _run_ops(control_platform, "deprovision", "brkdep3", "--confirm", phrase,
                         provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    assert confirmed.returncode == 0, confirmed.stderr
    assert "brkdep3" in confirmed.stdout
    assert "deprovisioned" in confirmed.stdout

    remaining = service.list_applications(actor_secret)["applications"]
    assert all(row["application_id"] != "brkdep3" for row in remaining)
    # M-4 (WP-1): deprovision removes the application's credential rows in
    # the same step -- the just-issued credential must be gone too, not
    # merely the application row.
    remaining_creds = {row["credential_id"] for row in service.list_credentials(actor_secret)["credentials"]}
    assert issued["credential_id"] not in remaining_creds


def test_deprovision_of_an_unregistered_application_fails_loudly(control_platform, deprovision_script_dir) -> None:
    result = _run_ops(control_platform, "deprovision", "never_registered_brk_app",
                      provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    assert result.returncode == 1
    assert json.loads(result.stderr.strip())["code"] == "NOT_FOUND"


def test_deprovision_rejects_a_malformed_application_id_before_any_database_access(
        control_platform, deprovision_script_dir) -> None:
    result = _run_ops(control_platform, "deprovision", "Not-A-Valid-Id!",
                      provision_dsn=control_platform.provision_dsn, migrations_dir=deprovision_script_dir)
    assert result.returncode == 1
    assert json.loads(result.stderr.strip())["code"] == "VALIDATION_FAILED"


def test_break_glass_commands_require_the_control_credential_pepper_and_actor(control_platform) -> None:
    """Missing `MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET` dies loudly (exit
    2) before any operation is attempted, the same `_die`/`_require_env`
    contract every other required-environment variable in this module
    already gets."""
    result = _run_ops(control_platform, "list-applications")
    assert result.returncode == 2
    assert "MITATEDB_CONTROL_CREDENTIAL_ID is required" in result.stderr


def test_audit_report_requires_provision_dsn(control_platform) -> None:
    result = _run_ops(control_platform, "audit-report")
    assert result.returncode == 2
    # Review M-1: exit code 2 alone does not discriminate this `_die()`
    # path from the declare-and-echo gate's own reserved exit 2
    # (`_print_denial_and_exit`) -- the stderr message is what actually
    # proves this failed for the right reason (a missing required env var,
    # not a destructive-confirmation refusal).
    assert "MITATEDB_PROVISION_DSN is required" in result.stderr


# ===========================================================================
# Phase 3.5 WP-5 (design docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_
# V1.md §4/§1-D/§1-E): out-of-band `issue-audit-credential` ceremony CLI,
# `freeze-issuance`/`unfreeze-issuance` CLI subcommands. Both are out-of-
# band-only, driven with `MITATEDB_CONTROLPLANE_DSN` directly -- neither
# needs `MITATEDB_CONTROL_CREDENTIAL_ID`/`_SECRET` (mirrors `bootstrap`/
# `reset` above, not the WP-6 break-glass command family).
# ===========================================================================


def test_cli_issue_audit_credential_produces_a_ready_to_use_credential(control_platform) -> None:
    """Out-of-band audit-credential issuance -- no in-band path exists for
    `role="audit"` either. The printed secret already has `must_rotate:
    false` (the ceremony issues and rotates before ever printing, design §4
    M-1 -- there is no in-band self-rotate path for an audit principal to
    otherwise clear it with)."""
    result = _run_ops(control_platform, "issue-audit-credential")
    assert result.returncode == 0, result.stderr
    # Phase 6 WP-3 (design D-1(d)): `ops.py`'s own stdout now prints the
    # complete, composed bearer on the `secret:` line -- recover the raw
    # secret this test's own direct `store.authenticate()` call still
    # needs (mirrors that store's own `authenticate` method, the real
    # receiving boundary that splits the bearer -- Phase 6 WP-3 差し戻し
    # 最終ラウンド 裁定 1 retired the old `http.py::_split_bearer` helper
    # this comment used to name here).
    credential_id, bearer = _parse_issued(result.stdout)
    secret = bearer
    assert "must_rotate: false" in result.stdout
    assert credential_id.startswith("ctl_")

    store = PostgresControlCredentialStore(control_platform.controlplane_dsn, pepper=_CONTROL_PEPPER,
                                           schema=control_platform.registry_schema)
    principal = store.authenticate(secret)
    assert principal.credential_id == credential_id
    assert principal.must_rotate is False
    assert principal.role == "audit"


def test_cli_issue_audit_credential_is_not_a_once_only_ritual(control_platform) -> None:
    """Unlike `bootstrap`, any number of audit credentials may be issued --
    there is no "first row" invariant to protect here, and this does not
    refuse merely because a control credential already exists."""
    _run_ops(control_platform, "bootstrap")
    first = _run_ops(control_platform, "issue-audit-credential")
    second = _run_ops(control_platform, "issue-audit-credential")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_id, _ = _parse_issued(first.stdout)
    second_id, _ = _parse_issued(second.stdout)
    assert first_id != second_id


def test_cli_freeze_issuance_then_unfreeze_round_trips(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "fzcli1")

    frozen = _run_ops(control_platform, "freeze-issuance", "fzcli1")
    assert frozen.returncode == 0, frozen.stderr
    assert "frozen" in frozen.stdout

    from mitatedb_api.errors import AuthorizationError
    with pytest.raises(AuthorizationError):
        service.issue_credential(actor_secret, "fzcli1", "runtime")

    unfrozen = _run_ops(control_platform, "unfreeze-issuance", "fzcli1")
    assert unfrozen.returncode == 0, unfrozen.stderr
    assert "no longer frozen" in unfrozen.stdout

    issued = service.issue_credential(actor_secret, "fzcli1", "runtime")
    assert issued["application_id"] == "fzcli1"


def test_cli_freeze_issuance_unknown_application_fails_closed(control_platform) -> None:
    result = _run_ops(control_platform, "freeze-issuance", "definitely_not_registered_xyz")
    assert result.returncode != 0


def test_cli_freeze_issuance_writes_control_audit_row(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "fzcli2")
    result = _run_ops(control_platform, "freeze-issuance", "fzcli2")
    assert result.returncode == 0, result.stderr

    statement = sql.SQL(
        "SELECT operation, target_kind, application_id, target_id, outcome FROM {table} "
        "WHERE operation = 'freeze_issuance' AND application_id = %s"
    ).format(table=sql.Identifier(control_platform.registry_schema, "control_audit"))
    with psycopg.connect(control_platform.provision_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(statement, ["fzcli2"])
            rows = cur.fetchall()
    assert len(rows) == 1
    operation, target_kind, application_id, target_id, outcome = rows[0]
    assert target_kind == "application"
    assert application_id == "fzcli2"
    assert target_id == "fzcli2"
    assert outcome == "allow"


def test_cli_freeze_issuance_does_not_affect_already_issued_credentials(control_platform) -> None:
    service, actor_id, actor_secret = _bootstrapped_actor(control_platform)
    service.register_application(actor_secret, "fzcli3")
    issued = service.issue_credential(actor_secret, "fzcli3", "runtime")

    result = _run_ops(control_platform, "freeze-issuance", "fzcli3")
    assert result.returncode == 0, result.stderr

    state = service._backend.credential_state(issued["credential_id"])  # noqa: SLF001
    assert state is not None and state[0] is True and state[1] is False  # still enabled, not revoked
