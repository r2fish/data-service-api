# 引き継ぎ — 2026-09-30 (R-114 `audit_requests_per_minute` の窓の形。Class C、規模 S、契約 1.11.0 → 1.12.0)

本書は前書の全項を写さない。前書は `docs/work-orders/HANDOVER_20260930_FABLE.md`。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`。

記録: `docs/archive/docs/work-orders/HANDOVER_20260929_FABLE2.md` (本変更セットで回転、`OC` §1.16 の 78)

## 1. 現在地

- 依頼者裁定 2026-09-30 (逐語): 「1は(i)、2は着手、Dで進めてください、別セッションで。」 本件は「1は(i)」(契約の文言を「窓の形は定めない」に改める)。「2」と「D」は R-115 への回答。
- 契約 1.12.0 (`spec/CCR_DISPOSITION.md` 従属判断 17)。`limits.audit_requests_per_minute_note` は窓の形を定めず、どの 1 窓でも宣言値を超えて通さないことと、`control_requests_per_minute` とは別の窓であることを保証する。義務は足さない (`versioning.obligations` は 1.11.0 まで)。
- 両 peer は data / control とも 1.12.0 を宣言。挙動は不変。`security/` は不変 (src は行数を変えない編集のみ)。
- `RM` v1.135。R-114 は閉止し、行は `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の末尾。
- 完了ゲート: `gate: 4611 passed, 2 subtests passed in 394.31s (0:06:34)`、`judge=PASS`、`pg_database/pg_roles diff 0` (label `r114`)。`COLLECTION_FLOOR` 4609 → 4611。
- push は停止中 (`OC` §2 の 20)。

## 2. 指摘の裁定 (`OC` §1.15 の 77)

| 指摘 | 裁定 | 理由 |
|---|---|---|
| r2db `limits.py` に "pre-auth fixed window" が残る | 直した | 本件の範囲 |
| minor 版とする理由が `versioning.compatibility` と突き合わされていない | 従属判断 17 に理由を追記。契約本文には足さない | 保証は変わらず、挙動も変わらない |
| `control_http.py` の D-5 の言い回し、register test の docstring、記録の文言 2 か所 | 直した | 本件の範囲 |
| note の「宣言値を超えて通さない」と `limit_enforcement` の適用単位 | 観察 | `limits.profile` の既存の文と重複する |
| r2db `control_plane.py` の CH-0259 の塊の "enforced" が 1.8.0 以降の宣言の分岐より古い | 観察 | コメントのみ。利用者は気づかない |

## 3. 次の一手

1. 契約の版を次に上げる変更セットは 1.13.0。`conformance-tests/test_contract.py` の 1.12.0 の文の pin の右端 (version-flip 文) を動かす。
2. 前書 §3 の各項 (R-101 / R-102 / R-115 / R-116) は変わらず残る。

## 4. 本チャットで足した運用上の教訓

- (i) 契約の既存の値を書き換えるときは、`spec/CONTRACT_HISTORY_MANIFEST.json` の当該 entry に値全体の `rewrite` を足すと、`CONTRACT_HISTORY.md` の引用を書き換えずに register test を緑に保てる。
- (ii) 義務を足さない版は、`version_binding` に "Only an implementation declaring ..." の opener を使わない文を置き、`obligations` に entry を足さない (version label 集合の一致を保つ)。
- (iii) src のコメントを行数を変えずに直すと、`security/CONTROL_MAPPING.md` の行参照がずれず、Class D の経路に触れない。
- (iv) `tools/contract_catalog.py` は `--help` を受け付けず、引数なしと同じく catalog を書き直す。
