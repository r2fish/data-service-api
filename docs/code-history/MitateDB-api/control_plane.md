## CH-0543

- moved from: `src/mitatedb_api/control_plane.py` (`ControlPlaneService.control_capabilities`)
- parent commit: `0fee6e52cc81da1178f06ed88e0a12260ee705ac`
- kind: comment

```
# Phase 4 WP-3(b) (P4-D4, contract `versioning.version_binding`),
# flipped to 1.5.0 in Phase 5 WP-3 (design D-1, subordinate
# ruling 10 item 1, same commit as the `operations`/
# `target_kinds` declaration keys below -- flip and behavior
# land together, never separately): unconditional (every
# instance of this service declares 1.5.0 now, whether or not
# `audit_query` itself is `enabled` on this deployment; the
# 1.4.0/1.5.0 obligations conditional on `audit_query` being
# provided stay conditional per version_binding's own text).
# Phase 6 WP-3 (design D-1/D-2, subordinate ruling 11):
# flipped to 1.6.0 -- same commit as `surfaces` (already
# present, WP-3 D-2) and the composed-bearer issue/rotate
# responses (`control_http.py::_with_composed_secret`).
#
# Phase 9 WP-3e (design D-1 (5)/(7), F-1): flipped to 1.7.0 --
# the SAME commit as the data-plane document's own identical
# flip (`cell.py::ApplicationRuntime.capabilities`) -- C-19's
# own data/control `contract_version` agreement assert is
# what this pairing keeps green.
#
# Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again
# to 1.8.0 -- the SAME commit as the data-plane document's own
# identical flip and this host's own `process_ceilings`
# mapping (D-5 (ii)).
```

### correction: 2026-09-25

- reason: Phase 11 WP-3 (docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md §7.1 訂正註「control plane の宣言版」) -- the control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert)

old:
```
Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again to 1.8.0 -- the SAME commit as the data-plane document's own identical flip and this host's own `process_ceilings` mapping (D-5 (ii)).
```

new:
```
Phase 10 WP-6b/pair-closing (design D-5 (v)): flipped again to 1.8.0 -- the SAME commit as the data-plane document's own identical flip and this host's own `process_ceilings` mapping (D-5 (ii)).

This control-plane document also flips to 1.9.0 in the same commit as the data-plane document's own identical flip (C-19's cross-plane version-match assert). The control surface's own `capabilities` (`control_plane`/`audit_query`) are unaffected -- 1.9.0's `common_baseline` obligation governs the data surface's application-plane operations only.
```
