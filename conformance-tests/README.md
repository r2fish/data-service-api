# Data Service API Conformance Tests

Implementation-independent tests for the common Data Service API contract and Security Invariants.

The same suite must be runnable against both:

- `r2db-api`
- `MitateDB-api`

## Security relationship

Security verification is derived from `security/SECURITY_INVARIANTS_V1.md`, not from whichever behavior the current implementation happens to have.

```text
Threat Model
  ↓
Security Invariant
  ↓
Conformance condition
  ↓
r2db-api / MitateDB-api evidence
```

A common invariant may be verified by API-level automated tests, controlled fault/security tests, or documented platform-control evidence when the property cannot be observed through the public API alone.

The conformance suite must not become a fixed feature allowlist. New capabilities may add new tests when needed while remaining free to use new implementation mechanisms.

## Initial extraction

Existing validated r2db-api tests are evidence candidates, not the source of truth. Their behavior should be mapped against the common invariants before reuse.

Likely reusable areas include authentication, CRUD, filtering/sorting/pagination, JSONB behavior, application isolation, SQL-injection resistance, request transaction rollback, and Runtime/Developer schema privilege separation.

Platform-specific deployment/provisioning mechanics do not belong in the common test suite, but evidence that a platform-specific control satisfies a common invariant belongs in `security/CONTROL_MAPPING.md`.

`CONDITIONS.md` is the implementation-independent condition register. The
initial executable `test_contract.py` verifies that the common contract is
machine-readable, has separate application/control authority, and records all
CCR dispositions. Peer adapters run the same condition IDs for runtime
behavior; the r2db foundation adapter is exercised under `r2db-api/tests/`.

## Adding a new peer

`conformance-tests/adapter.py` is a *port*: the abstract `ConformanceAdapter`
interface, its value types, and the condition tests that exercise it. It is
owned by this repository. Each peer owns its own *plug*: the concrete code
that connects the port to that peer's actual runtime. This split (design
`docs/design/CONFORMANCE_ADAPTER_V1.md` principle 1) keeps neither `r2db-api`
nor `MitateDB-api` the implicit owner of the common contract -- the
condition tests never live inside a peer, and a peer's internals never leak
into `conformance-tests/`.

To register a new peer:

1. Create `<peer>/conformance/conformance_adapter_<name>.py` exposing a
   `build_adapter()` function that returns a `ConformanceAdapter` instance.
2. Implement `ConformanceAdapter` (`conformance-tests/adapter.py`) against
   that peer's own client/service code, satisfying every abstract method,
   the `MUST_COVER_TAMPER_KINDS` tamper-vector coverage, and the
   `MUST_COVER_IDENTIFIER_POSITIONS` / `MUST_COVER_VALUE_POSITIONS` position
   coverage.
3. Add an entry to `conformance-tests/registry.json`:

   ```json
   {"name": "<peer>", "module": "conformance_adapter_<name>", "required": true}
   ```

   `conftest.py` adds `<peer>/conformance/` to `sys.path` and imports the
   module by name at collection time.

A `required: true` entry that fails to import or to build (`build_adapter()`
raising, or not returning a `ConformanceAdapter`) fails the whole suite at
collection -- it does not skip. Skipping would silently convert "this
peer's conformance is unverified" into "permitted," which the port
explicitly refuses to do (design principle 4). Only mark an entry
`required: false` for a peer that is deliberately not yet expected to pass.

The adapter must mirror its peer faithfully and must never compensate for a
peer's gaps (design section 10.5). If a peer is missing a check the port
expects -- for example, an operation that should reject a disabled
application but doesn't -- the fix belongs in the peer, not in adapter code
that quietly performs the missing check on the peer's behalf. An adapter
that does that is no longer testing the peer; it is testing itself.

### One peer, more than one adapter

A single peer may register more than one entry in `registry.json`, each
with its own `build_adapter()` module. `r2db-api` currently does this:
`conformance_adapter_r2db` drives `DataService` in-process, directly, over
an in-memory `ApplicationCell`; `conformance_adapter_r2db_http` drives the
same peer's real ASGI HTTP boundary (`r2db_api.http`) in front of a
`DataService` backed by `PostgresCell` against a real local PostgreSQL
server. Both are registered `required: true` and both appear as separate
adapter ids in every condition test's parametrization.

This is not duplication. The point of a second adapter for the same peer
is that the *identical* condition IDs -- the same tamper vectors, the same
identifier/value position corpus, the same C-01/C-03/C-08 assertions --
re-run unchanged against a materially different deployed shape: request
parsing, byte-bound enforcement, connection pooling, catalog-backed
identifier verification, and real transactional rollback are all only
reachable through the HTTP+PostgreSQL adapter, not the in-process one. A
peer that only ever registers its in-process adapter has conformance
evidence for its authority logic, but none for how that logic behaves once
it is actually sitting behind the wire protocol and the storage engine it
will run against in deployment. Register a second adapter for a peer
whenever it grows a second materially different way of being reached (for
example, a real database-backed storage engine, or a network transport)
that the existing adapter's plug does not exercise.

A real-stack adapter that depends on an external service the local
environment might not have (here, a running PostgreSQL server) still
follows the `required: true` rule above: it does not skip when that
dependency is unreachable. `conformance_adapter_r2db_http.py` checks
PostgreSQL connectivity explicitly during construction and, if it cannot
connect, fails loudly with the DSN it tried and remediation steps, which
`conftest.py` then turns into a hard collection error for the whole suite
-- never a silently shrunk parametrization list. The dependency is
configured through one environment variable (`R2DB_TEST_ADMIN_DSN`, shared
with `r2db-api/tests/test_postgres.py`) rather than hard-coded, so the
adapter can be pointed at a different reachable server, but there is no
path that turns "PostgreSQL is unreachable" into "this adapter's coverage
is silently absent."

## Running against real PostgreSQL

Both peers' HTTP+PostgreSQL adapters need a real PostgreSQL server reachable
through a superuser-equivalent DSN, one environment variable per peer:

- `R2DB_TEST_ADMIN_DSN` (shared with `r2db-api/tests/test_postgres.py`)
- `MITATEDB_TEST_ADMIN_DSN` (shared with `MitateDB-api/tests/test_postgres.py`)

Both default to a local unix-socket DSN (`host=/tmp port=5432 dbname=postgres`)
when unset. That default does not reach a server started in a container on a
published loopback port -- set both variables explicitly to a loopback TCP
DSN whenever PostgreSQL is not reachable over `/tmp`.

The server must be started with `max_connections=300`. The completion gate
runs the suite with `-n 5 --dist loadgroup` (see `conftest.py`'s
`pytest_collection_modifyitems`), which confines each adapter's own
session-scoped connection pool to one worker process but still runs five
adapters' worth of real PostgreSQL connections concurrently against the
same server; the default `max_connections=100` was measured (Phase 6) at
64 of 100 connections used, which `-n 5`'s concurrent adapters are
expected to exceed. An unreachable or under-provisioned PostgreSQL server
must fail the run, never skip it -- the same fail-loud rule as the adapter
construction check above.

Both peers' HTTP+PostgreSQL adapters also shell out to a real `psql`
client on `PATH` to apply migrations (`conformance_adapter_r2db_http.py:230`,
`conformance_adapter_mitatedb_http.py:167`); install a PostgreSQL client
package before running the gate. Install the peers themselves with
`pip install -c constraints.txt -e './r2db-api[test]' -e './MitateDB-api[test]'`
(each extras argument is quoted so zsh does not treat `[test]` as a glob).

The completion gate command is `python -m pytest -q -n 5 --dist loadgroup`,
run solo (no other pytest process concurrently against the same server).
CI (`.github/workflows/ci.yml`) runs this identical command against a
`postgres:16` container started with `-c max_connections=300` and DSNs
overridden to that container's loopback address; CI's Python 3.11 job's
pass/fail/skipped/xfailed tally is the authoritative record of the gate,
and the Python 3.12 job is required to reproduce the identical tally.

## `COLLECTION_FLOOR` (R-9, evidence-loss detection)

`conformance-tests/COLLECTION_FLOOR` holds a single decimal integer: a
floor on the number of tests the *root* pytest session (run from the
repository root, not just this directory) collects. `tools/check_collection_floor.py`
(standard library only) re-runs `python -m pytest --collect-only -q` from
the repository root, reads pytest's own trailing `<N> tests collected`
line, and compares it against that floor. CI (`.github/workflows/ci.yml`,
`conformance` job) runs this check in both the 3.11 and 3.12 matrix jobs,
after PostgreSQL is up and dependencies are installed but before the
conformance gate itself -- `--collect-only` builds all four adapters at
collection time (`conftest.py`'s `_discover_and_build`) and performs
connection verification against PostgreSQL, so this step needs the same
PostgreSQL server and DSN environment variables as the gate proper. It
does not provision disposable databases (measured: 0 diff in
`pg_database` / `pg_roles` before and after a `--collect-only` run). This
is accepted as a known price of measuring the floor from outside pytest
itself rather than as an in-suite test (a floor check that only runs when
some subset of the suite happens to be selected would not be a floor
check at all).

The operating convention:

1. The value is the previously-recorded main-branch measurement. It is
   updated only at a phase's completion gate, by the supervisor -- never
   mid-WP (raising it mid-WP would make every other in-flight WP's merge
   go red against a floor it never measured against).
2. Lowering the floor requires an explicit commit, and that commit's
   message must state the reason. Lowering is not forbidden -- deleting
   tests is a legitimate thing to do -- but it must never happen silently.
3. Raising the floor is free to do (collecting more tests than the floor
   is always fine, and does not fail the check on its own), but the
   commit that raises it to match a new measurement is likewise made only
   at a completion gate, by the supervisor, for the same reason as (1).
4. **Residual risk (disclosed, not fixed by this mechanism):** the path
   from a real collected count back down to the recorded floor is
   entirely manual. Between two completion gates, any test-count decrease
   up to `(actual collected count at gate time) - (recorded floor)` goes
   undetected -- the floor catches a *large* drop, not "not one test was
   removed." Shortening the interval between gates is the only mitigation;
   there is no mechanical fix for this gap.
