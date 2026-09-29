"""Static reads of the r2db-api deployment artifacts for the multi-process
data plane (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-1 and
D-3 (2')): the two systemd units and the two `EnvironmentFile` examples
under `r2db-api/deploy/`.

What these tests pin, one property per test:

- the application-plane unit passes `--workers` from `${R2DB_WORKERS}`
  and nowhere writes a literal worker count;
- it runs `python -m r2db_api.main --preflight` as an `ExecStartPre=`
  from the same virtualenv, under the same `EnvironmentFile=`, and a
  failing preflight stops the unit (no `-` prefix);
- it has systemd create the slot directory (`RuntimeDirectory=` with
  mode `0700`);
- `api.env.example` names `R2DB_WORKERS` and an `R2DB_SLOT_DIR` equal to
  the path that `RuntimeDirectory=` creates;
- the control-plane unit passes `--workers` from
  `${R2DB_CONTROL_WORKERS}` and runs `python -m r2db_api.control_main
  --preflight` the same way;
- `control.env.example` sets `R2DB_CONTROL_WORKERS=1`.

A systemd unit is read as `[Section]` headers plus `Key=value` lines;
comment lines (`#` / `;`) never count, so a directive that survives only
inside a comment is absent here. Every test first asserts that the lines
it inspects exist, so no test passes on an empty read.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
API_UNIT = DEPLOY_DIR / "systemd" / "r2dbsvc-api.service"
CONTROL_UNIT = DEPLOY_DIR / "systemd" / "r2dbsvc-control.service"
API_ENV_EXAMPLE = DEPLOY_DIR / "env" / "api.env.example"
CONTROL_ENV_EXAMPLE = DEPLOY_DIR / "env" / "control.env.example"

# `--workers` followed by anything other than a `${...}` reference: a
# literal count (`--workers 4`, `--workers=4`, `--workers "4"`).
_LITERAL_WORKERS_RE = re.compile(r"--workers(?:=|\s+)(?!\$\{)\S")


def _service_directives(unit: Path) -> list[tuple[str, str]]:
    """`(key, value)` for every non-comment `Key=value` line inside the
    unit's `[Service]` section, in file order."""
    directives: list[tuple[str, str]] = []
    section = None
    for raw in unit.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Service" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        directives.append((key.strip(), value.strip()))
    return directives


def _values(unit: Path, key: str) -> list[str]:
    return [value for k, value in _service_directives(unit) if k == key]


def _env_assignments(example: Path) -> dict[str, str]:
    """Uncommented `NAME=value` lines of an `EnvironmentFile` example."""
    assignments: dict[str, str] = {}
    for raw in example.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        assignments[name.strip()] = value.strip()
    return assignments


def _single(values: list[str], what: str) -> str:
    assert len(values) == 1, f"expected exactly one {what}, found {values!r}"
    return values[0]


def _assert_workers_from_env(unit: Path, variable: str) -> None:
    exec_start = _single(_values(unit, "ExecStart"), f"ExecStart= in {unit.name}")
    argv = shlex.split(exec_start)
    assert "--workers" in argv, exec_start
    assert argv.count("--workers") == 1, exec_start
    assert argv[argv.index("--workers") + 1] == "${" + variable + "}", exec_start
    assert not _LITERAL_WORKERS_RE.search(exec_start), exec_start
    for key, value in _service_directives(unit):
        assert not _LITERAL_WORKERS_RE.search(value), f"{key}={value}"


def _assert_preflight(unit: Path, module: str) -> None:
    exec_start = _single(_values(unit, "ExecStart"), f"ExecStart= in {unit.name}")
    pre = _values(unit, "ExecStartPre")
    assert pre, f"{unit.name} has no ExecStartPre="
    expected_tail = ["-m", module, "--preflight"]
    matching = [value for value in pre if shlex.split(value)[1:] == expected_tail]
    assert len(matching) == 1, pre
    preflight = matching[0]
    # A leading `-` would make systemd ignore the preflight's own exit
    # status and start uvicorn anyway.
    assert not preflight.startswith(("-", "+", "!", "@", ":")), preflight
    interpreter = Path(shlex.split(preflight)[0])
    server = Path(shlex.split(exec_start)[0])
    assert interpreter.name.startswith("python"), preflight
    assert interpreter.parent == server.parent, (preflight, exec_start)
    # One EnvironmentFile= per unit: the preflight and uvicorn read the
    # same environment.
    _single(_values(unit, "EnvironmentFile"), f"EnvironmentFile= in {unit.name}")


def test_systemd_api_unit_passes_workers_from_env_without_a_literal_count():
    _assert_workers_from_env(API_UNIT, "R2DB_WORKERS")


def test_systemd_api_unit_runs_the_data_plane_preflight_before_uvicorn():
    _assert_preflight(API_UNIT, "r2db_api.main")


def test_systemd_api_unit_creates_the_slot_runtime_directory_mode_0700():
    runtime_directory = _single(_values(API_UNIT, "RuntimeDirectory"), "RuntimeDirectory=")
    assert runtime_directory == "r2dbsvc-api/slots"
    mode = _single(_values(API_UNIT, "RuntimeDirectoryMode"), "RuntimeDirectoryMode=")
    assert mode == "0700"


def test_env_example_api_names_workers_and_the_runtime_directory_slot_path():
    assignments = _env_assignments(API_ENV_EXAMPLE)
    assert assignments, API_ENV_EXAMPLE
    workers = assignments.get("R2DB_WORKERS")
    assert workers is not None and workers.isdigit() and int(workers) >= 1, workers
    runtime_directory = _single(_values(API_UNIT, "RuntimeDirectory"), "RuntimeDirectory=")
    assert assignments.get("R2DB_SLOT_DIR") == f"/run/{runtime_directory}"


def test_systemd_control_unit_passes_control_workers_from_env_without_a_literal_count():
    _assert_workers_from_env(CONTROL_UNIT, "R2DB_CONTROL_WORKERS")


def test_systemd_control_unit_runs_the_control_plane_preflight_before_uvicorn():
    _assert_preflight(CONTROL_UNIT, "r2db_api.control_main")


def test_env_example_control_pins_control_workers_to_one():
    assignments = _env_assignments(CONTROL_ENV_EXAMPLE)
    assert assignments, CONTROL_ENV_EXAMPLE
    assert assignments.get("R2DB_CONTROL_WORKERS") == "1"
