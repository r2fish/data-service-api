"""Static reads of `MitateDB-api/docker/Dockerfile` for the multi-process
data plane (design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-1 and
D-3 (2')). No container runtime is involved: the file's own text is
what these tests observe.

What these tests pin, one property per test:

- the image creates the slot directory owned by the `USER` the
  container runs as, mode 0700, before switching to that user, and
  `MITATEDB_SLOT_DIR` names that directory;
- the `data` branch of `CMD` passes `--workers "${MITATEDB_WORKERS}"`
  and nowhere writes a literal worker count or a default for the
  variable (`ENV` / `ARG` in any stage, `${MITATEDB_WORKERS:-n}`);
- the `data` branch reaches `exec uvicorn` only through `&&` after the
  preflight (or under `set -e`), never through `;`;
- the `data` branch runs `python -m mitatedb_api.main --preflight`
  before `exec uvicorn`;
- the `control` branch passes `--workers "${MITATEDB_CONTROL_WORKERS}"`
  and nowhere writes a literal worker count or a default for the
  variable;
- the `control` branch runs `python -m mitatedb_api.control_main
  --preflight` before `exec uvicorn`, and only through `&&` (or under
  `set -e`).

The Dockerfile is read as logical instructions: comment lines are
dropped and backslash continuations are joined. `CMD` is the exec form
`["sh", "-c", <script>]`; the script is split into its `control` and
`data` branches at the one `if [ "$SERVICE" = "control" ]; then ...;
else ...; fi`. Every test first asserts that the instruction or branch
it inspects exists, so no test passes on an empty read.
"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "docker" / "Dockerfile"

_BRANCHES_RE = re.compile(
    r'^\s*(?P<prefix>(?:set -e\s*;\s*)?)if \[ "\$SERVICE" = "control" \]; then (?P<control>.+); '
    r"else (?P<data>.+); fi\s*$"
)
# `--workers` followed by anything other than a `${...}` reference
# (quoted or not): a literal count.
_LITERAL_WORKERS_RE = re.compile(r'--workers(?:=|\s+)(?!"?\$\{)\S')


def _instructions() -> list[tuple[str, str]]:
    """`(INSTRUCTION, arguments)` for every logical instruction, in order."""
    logical: list[str] = []
    pending = ""
    for raw in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            pending += stripped[:-1].strip() + " "
            continue
        logical.append(pending + stripped)
        pending = ""
    assert not pending, pending
    result = []
    for line in logical:
        keyword, _, arguments = line.partition(" ")
        result.append((keyword.upper(), arguments.strip()))
    return result


def _runtime_stage() -> list[tuple[str, str]]:
    """Instructions of the last stage (the one the image runs)."""
    instructions = _instructions()
    starts = [i for i, (keyword, _) in enumerate(instructions) if keyword == "FROM"]
    assert starts, "no FROM"
    return instructions[starts[-1]:]


def _env(stage: list[tuple[str, str]], name: str) -> str | None:
    value = None
    for keyword, arguments in stage:
        if keyword != "ENV":
            continue
        for token in shlex.split(arguments):
            if "=" in token:
                key, _, val = token.partition("=")
                if key == name:
                    value = val
    return value


def _cmd_script() -> str:
    cmds = [arguments for keyword, arguments in _instructions() if keyword == "CMD"]
    assert len(cmds) == 1, cmds
    argv = json.loads(cmds[0])
    assert argv[:2] == ["sh", "-c"] and len(argv) == 3, argv
    return argv[2]


def _branches() -> tuple[str, str, str]:
    """`(prefix, control, data)` of the `CMD` script."""
    script = _cmd_script()
    match = _BRANCHES_RE.match(script)
    assert match, script
    return match.group("prefix"), match.group("control"), match.group("data")


def _assert_workers_from_env(branch: str, variable: str) -> None:
    assert "exec uvicorn " in branch, branch
    expected = '--workers "${' + variable + '}"'
    assert branch.count("--workers") == 1, branch
    assert expected in branch, branch
    assert not _LITERAL_WORKERS_RE.search(branch), branch


def _assert_no_worker_default(variable: str) -> None:
    """The worker count has no default anywhere in the image: no `ENV` or
    `ARG` of `variable` in any stage and no `${variable:-n}` /
    `${variable-n}` fallback in `CMD`, so a deploy that does not set the
    variable fails the preflight instead of starting a baked-in count."""
    instructions = _instructions()
    assert instructions, DOCKERFILE
    for keyword, arguments in instructions:
        if keyword not in ("ENV", "ARG"):
            continue
        tokens = shlex.split(arguments)
        names = {token.partition("=")[0] for token in tokens if "=" in token}
        if tokens and "=" not in tokens[0]:
            names.add(tokens[0])  # `ENV NAME value` / `ARG NAME`
        assert variable not in names, f"{keyword} {arguments}"
    script = _cmd_script()
    for fallback in ("${" + variable + ":", "${" + variable + "-"):
        assert fallback not in script, script


def _preflight_join(branch: str, module: str) -> str:
    """The separator between `python -m <module> --preflight` and
    `exec uvicorn <module>:app` in `branch` (`&&` or `;`)."""
    match = re.search(
        r"python -m " + re.escape(module) + r" --preflight\s*(?P<sep>&&|;)\s*exec uvicorn "
        + re.escape(module) + r":app ",
        branch,
    )
    assert match, branch
    return match.group("sep")


def test_docker_image_creates_the_slot_directory_owned_by_user_mode_0700():
    stage = _runtime_stage()
    users = [(i, arguments) for i, (keyword, arguments) in enumerate(stage) if keyword == "USER"]
    assert len(users) == 1, users
    user_index, user = users[0]
    slot_dir = _env(stage, "MITATEDB_SLOT_DIR")
    assert slot_dir and slot_dir.startswith("/"), slot_dir
    runs = [
        (i, arguments) for i, (keyword, arguments) in enumerate(stage)
        if keyword == "RUN" and slot_dir in arguments
    ]
    assert runs, f"no RUN creates {slot_dir}"
    steps = [shlex.split(step) for index, run in runs for step in run.split("&&")]
    assert ["mkdir", "-p", slot_dir] in steps, steps
    assert ["chown", f"{user}:{user}", slot_dir] in steps, steps
    assert ["chmod", "0700", slot_dir] in steps, steps
    assert all(index < user_index for index, _ in runs), (runs, user_index)
    for step in steps:
        if step and step[0] == "chmod" and slot_dir in step:
            assert step == ["chmod", "0700", slot_dir], step


def test_docker_cmd_data_branch_passes_workers_from_env_without_a_literal_count():
    _prefix, _control, data = _branches()
    _assert_workers_from_env(data, "MITATEDB_WORKERS")
    _assert_no_worker_default("MITATEDB_WORKERS")


def test_docker_cmd_data_branch_never_reaches_uvicorn_after_a_failed_preflight():
    prefix, _control, data = _branches()
    separator = _preflight_join(data, "mitatedb_api.main")
    assert separator == "&&" or prefix.startswith("set -e"), (prefix, data)


def test_docker_cmd_data_branch_runs_the_data_plane_preflight_before_uvicorn():
    _prefix, _control, data = _branches()
    preflight = data.find("python -m mitatedb_api.main --preflight")
    server = data.find("exec uvicorn mitatedb_api.main:app ")
    assert preflight != -1, data
    assert server != -1, data
    assert preflight < server, data


def test_docker_cmd_control_branch_passes_control_workers_from_env_without_a_literal_count():
    _prefix, control, _data = _branches()
    _assert_workers_from_env(control, "MITATEDB_CONTROL_WORKERS")
    _assert_no_worker_default("MITATEDB_CONTROL_WORKERS")


def test_docker_cmd_control_branch_runs_the_control_plane_preflight_before_uvicorn():
    prefix, control, _data = _branches()
    separator = _preflight_join(control, "mitatedb_api.control_main")
    assert separator == "&&" or prefix.startswith("set -e"), (prefix, control)
