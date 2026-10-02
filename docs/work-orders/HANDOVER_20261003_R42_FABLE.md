# 引き継ぎ書 — 2026-10-03 R-42 (期限切れ要求の意味論) 設計完了・作業指示書へ

本書は台帳 (`docs/design/ROADMAP_POST_PHASE7_V1.md` §8) R-42 の作業機チャット (2026-10-02〜03) の記録の続きである。前の記録は `docs/archive/docs/work-orders/HANDOVER_20261002_R42_FABLE.md` (cloud session の記録 §1〜§6 と、作業機の追記 §7.1〜§7.4。別チャット (R-33) の変更セットで archive へ移った)。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-42 の正本は設計 `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md` v0.10 (以下「設計」)。

## 1. 現在地

- local main `a0872b2` (台帳 v1.156、設計 v0.10) + 本変更セット (本書と、v1.151 の版数行の archive への回転の完了。前の変更セットでは監督の script が途中で止まり、台帳から外した行が archive に入らず本書も作られないまま commit された — 監督の取りこぼし。本変更セットで補った)。worktree `.claude/worktrees/r42` (branch `r42`)。main は未送信 (`OC` §2 の 20、Mitate 経由の送信)。
- 済んだこと: 設計 v0.4 (作業機の照合と実測 M-1〜M-8)、v0.5 (依頼者裁定 U-1〜U-9、全件 (a))、v0.6〜v0.9 (設計レビュー 2 回目: 1 巡目 A / B 並列 → 再確認 → 再々確認 → §9 の最終確認。依頼者裁定 V-1〜V-3)、v0.10 (契約文の依頼者確定)。設計レビューは契約を触るので 2 回 (`OC` §1.7 の 50) で、2 回とも済み。
- 契約の版: merge 順の帰結で **minor 1.16.0・従属判断 21** (台帳 R-118 が 1.15.0・従属判断 20 を先に使う)。確定文の「1.15.0」「subordinate ruling 20」「1.14.0」は契約 WP で「1.16.0」「21」「1.15.0」に置き換える (設計 v0.10 の版数行)。R-118 の merge 後に r42 へ main を取り込むと、`spec/` の version_binding の末尾 (1.14.0 の段落の後に 1.15.0 の 1 文、その後に version-flip の文) が変わっている。R-42 の段落は 1.15.0 の文の後・version-flip の文の前。
- 触っていないもの: `spec/`、`security/`、`conformance-tests/`、両 peer の製品コード。完了ゲートは回していない (文書だけの変更セット)。
- 記録ファイル `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` の先頭の並びは、別チャットの回転で v1.149 が v1.150 より上に入っており降順が崩れている (記録は書き換えないので直していない。観察)。

## 2. 次の一手

1. 作業指示書 `docs/work-orders/WORK_ORDER_R42_EXPIRED_REQUEST_SEMANTICS_V1.md` (Change Set Manifest。`drafter`)。WP の順: 契約 1.16.0 (確定文の逐語複製と pin、設計 D-6 の pin と記録の列挙) → conformance (port v1.22 の新 primitive と handle、stall 点の統一、新条件 = C-35 の次の番号を見込む (番号は conformance の WP で採番)、version gate と非空振りの guard、C-05 / C-24 / `security/CONTROL_MAPPING.md` の書き換え。設計 D-7、§6) → r2db (設計 D-9) → MitateDB (設計 D-9。SQLite の文の bound を含む) → 版の flip と新条件を統合 branch 上の同じ 1 commit に (設計 D-6 (B)) → 完了ゲート (`tools/dev/gate.py`。契約ファイルを触るので root suite の完走と性能差分) → 受け入れ監査 (`evidence-auditor` 1 回) → 台帳の閉止。完了条件番号 → 変異の対応表は設計 §6.6 と、レビュー B の変異案 (scratchpad に残したもの。次のチャットからは読めないので作業指示書に写す) から確定する。
2. R-118 の merge を待ち、r42 に main を取り込んでから契約 WP に入る。
3. 設計 §11.7 の範囲外の観察 (`limit_enforcement.execution_ms` の値 `reference_wall_clock` に契約の定義文が無い) を契約 WP で扱う。

## 3. 依頼者判断待ち

- なし (U-1〜U-9、V-1〜V-3、契約文の確定は済み)。作業指示書の確認は Class D の手順どおり (`ROLES` Class C・D の 4)。

## 4. 裁定

`OC` §1.15 の 77。2 回目の設計レビューの 1 巡目・再確認の裁定は前の記録の §7.3〜§7.4。本書の分:

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 再々確認 F-1〜F-14 (設計 §11.7) | 直した (v0.8) | 全件監督裁定。F-11 は (A) (文の定義を storage の操作に広げる)、F-12 は中間 commit が main に入らないことを D-6 に書いた |
| 再々確認の範囲外の観察 (`reference_wall_clock` に契約の定義文が無い) | 観察 (起票しない。契約 WP で扱う) | 本件の契約 WP が同じ節を触る。DB の利用者が気づく差は無い |
| §9 の最終確認 FC-1〜FC-6 (設計 §11.8) | 直した (v0.9) | 全件監督裁定。FC-3 は (A') (in-memory は義務 (b) にだけ縛る) |
