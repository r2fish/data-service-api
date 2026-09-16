# F9 execution assets v1.x (moved from Mitate)

These ten files were drafted on 2026-09-13 in the Mitate product repository under
`docs/work-orders/f9-execution-assets/` for the F9 operation-depth production
validation (probing an isolated Data Service on Cloud Run). They were moved here
on 2026-09-16 unchanged, byte for byte, because Mitate must not hold implementation
code (Mitate decision DM-0009) and the Mitate work order
`docs/work-orders/f9-data-service-production-validation.md` leaves their move
out of Mitate or their deletion to the parent work.

## Status — do not use as evidence

- They are **v1.x assets**. The current Mitate design
  `docs/design/f9-data-service-production-validation.md` (v2.1) states that they
  must not be used as evidence for v2.1.
- They have **not** been reviewed under this repository's process and are not
  wired into any build, test, CI or deployment here. Treat them as reference
  material only.
- They reference secrets only by Secret Manager resource path patterns and
  environment-variable names; they contain no credential values.

## Integrity note

`SHA256SUMS` was written at 2026-09-13 20:41 JST. `f9-isolation-gate.sh` and
`f9-job-entrypoint.sh` were modified at 20:45 JST, after the manifest, so
`shasum -a 256 -c SHA256SUMS` reports those two as FAILED. The mismatch already
existed in Mitate before the move; the manifest was left as it was so that it
still records the 20:41 state. The other seven listed files match.
