# 依頼者指示 (2026-09-16 18:52 JST) — R-37 を閉止に絞って閉じ、R-45 を次に置く

- 状態: **依頼者指示 (確定)**。次の data-service-api 監督チャットが着手時に読む。再審議しない。
- 経路: 依頼者の指示を Mitate の監督セッションが起草し、本書として本リポジトリへ置いた。事実の節は Mitate の監督が 2026-09-16 18:30〜18:50 JST に本リポジトリの main (`ca74236`) を実測したもの。
- 対象: `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 (WP-5 の manifest、v1.22)、`docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 B・付録 C、`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` (R-45、v1.1)、`docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.50)。
- 変更クラス: 本書は文書のみ (A)。本書が指示する WP-5 の縮小版は manifest どおり Class B の見込みで、最終判定は `RM` §9 の 8 の表で行う。

## 1. 依頼者の問題認識

「data-service-api のリファクタリングが終わらない、ずっとやっている。」

## 2. 事実 (main `ca74236`、2026-09-16)

| 項目 | 実測 |
|---|---|
| R-37 の開始 | 2026-09-14 10:51 (WP-1 の是正 `b2d996a` が最古の R-37 commit) |
| R-37 の commit | 119 (非マージのうち `refactor` 27、`docs` 31) |
| 2026-09-10 以降の非マージ commit | 138 (`feat`/`fix`/`refactor`/`test` 53、`docs` 74) |
| 1 日の commit | 09-14: 69、09-15: 107、09-16: 76 |
| 小 WP の数 | 22 (1a〜1n、2a、3a〜3i、4a〜4c) |
| roadmap の版上げ | 09-16 だけで v1.39 → v1.50 |
| 作業指示書の長さ | R-37 2,325 行、コメント来歴 CS1 3,635 行、設計 `MODULE_REFACT_ARCHITECTURE_V1.md` 689 行 |
| 残り | WP-5 のみ。ただし manifest §5.46 は範囲 6 件 (Z5-1)、完了条件 22 項目 |
| 最大ファイル | `MitateDB-api/src/mitatedb_api/cell.py` 3,757 行、`r2db-api/src/r2db_api/postgres.py` 2,353 行 |
| worktree / 未 push | 14 本 / 310 commit |

依頼者と Mitate の監督の見立て (事実ではなく評価):

1. 小 WP ごとに manifest・実装・独立レビュー・実施記録・roadmap 版上げが付き、コード 1 commit に文書 1.1 commit の比率になっている。固定費が刻みの数に比例している。
2. レビューで見つかった「移動前からの穴」が R-39・R-42・R-44・R-46 として起票され、R-44 は 09-16 に R-37 の合間で WP-1〜4 まで実行された。発見が即、仕事になっている。
3. 設計 §4 の WP-5 は「facade 縮小と閉止」だが、manifest では SQL 安全性の静的走査の新設、循環 import 検査の新設、文字列注釈の読み手検査まで含む。閉止のための WP に新機構が 3 つ入っている。
4. 製品を止めている R-45 (Mitate F9 の阻害要因、mitate-application の本番反映を阻む) が「WP-5 の統合後」に並んでいる。

## 3. 指示

### 3.1 R-37 WP-5 を閉止だけに絞る

manifest §5.46 の Z5-1 の 6 件のうち、**行うのは次の 3 件だけ**。

- (3) 真に読み手 0 の import 2 件 (`MitateDB-api/src/mitatedb_api/backend_postgres.py` の `CONTRACT_TYPES`、`MitateDB-api/src/mitatedb_api/config.py` の `build_surfaces`) の削除。
- (4) 残る再 export を「意図的な facade 互換」として記録 (訂正註 8-4 の実測どおり `_escape_like_literal`・`_FIELD_TYPE_SQL`・`_JSONB_SQL` は外部テストに読まれているので残す)。
- (6) R-37 の閉止記録。

**行わないもの (着手しない。指示書から外す)**: (1) SQL 安全性の静的走査の新設、(2) 循環 import の静的検査の新設、(5) 文字列注釈の読み手検査の手当て。この 3 件は roadmap の R-37 行に「閉止後の残余 (未着手)」として 1 行ずつ記録する。新しい台帳番号を起こすかは監督判断だが、起こす場合も**起票のみ**とし、§3.3 に従う。

(5) を外した代わりに、(3) の再照合は次で置き換える: 削除する 2 名を `git ls-files` の全ファイル (`.py` に限らない。`docs/code-history/` を含む。`MitateDB-api/docs/f9-execution-assets-v1/` を除く) に対して**文字列として grep** し、件数と `file:line` を報告に貼る。文字列 grep は文字列注釈も拾うので、(5) の偽陰性は起きない。付録 B の A と食い違う参照が 1 件でもあれば止めて監督へ上げる (manifest の既存条件のまま)。

完了条件は manifest §5.46 の表のうち (3)・(4)・(6) に掛かる行だけを残す。設計 §5.3 の完了ゲート (root suite の単独実行) は閉止時に 1 回行う。`COLLECTION_FLOOR` は変えない。削除前後の両 peer の集計行 (Z5-14) は残す。

### 3.2 R-37 を閉じる

縮小版 WP-5 の main 統合をもって R-37 を閉じる。閉止記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10 の WP-5 実施記録と roadmap R-37 行に**各 1 回**書く。設計の閉止条件「責務・依存方向・回帰証拠」に対する記録は、WP-1〜4 の実施記録と本書 §2 の表を指す 1 段落でよい。line count が減っていないことは記録するが、閉止の障害にしない (設計 §4 WP-5 の「line count は成果指標ではない」)。

### 3.3 新規起票は「起票のみ」に凍結する

R-45 が閉じるまで、レビューや実測で見つかった穴は roadmap §8 に **1 行足すだけ**にする。設計メモ・作業指示書・worktree を起こさない。既に起票済みの R-39・R-42・R-46 も着手しない。例外は R-45 の作業そのものを止める欠陥だけで、その場合は依頼者に上げてから着手する。

### 3.4 R-45 を次に置く

順序: **縮小版 WP-5 の統合 → R-45 WP-A → WP-B / WP-C → WP-D** (R-45 作業指示書 v1.1 §2 の順序のまま。WP-5 の縮小で前提が変わらないことは、WP-5 が触るのが上の 2 import だけであることから明らか)。R-45 の各 WP は `WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` v1.1 と付録 C の制約 (本番を変えない、credential を出力しない、push しない、spec と Mitate の契約を変えない) をそのまま守る。

### 3.5 工程の固定費を落とす (R-45 以降に適用)

- roadmap の版上げと設計の実施記録は**小 WP ごとではなく WP の統合ごとに 1 回**。
- 引き継ぎ書は**チャット終了時に 1 本**。WP の途中で書かない。
- manifest は WP ごとに 1 本。小 WP に分ける場合も manifest は分けない。
- 独立レビューと監査は `OPERATING_CONDITIONS.md` のとおり維持する (省かない)。落とすのは記録の回数だけで、検証の回数ではない。

### 3.6 片付け (区切りで。今は行わない)

- worktree 14 本のうち、main に統合済みで未コミット 0 のものは削除する。`mitatedb-operation-depth-platform-plan` は R-45 の起票を取り込み済みか確認してから扱う。
- 310 commit の push は依頼者が言うまで行わない (`OPERATING_CONDITIONS.md` §1 の 20)。Mitate 側の履歴書き換え・移設と同じ機会にまとめる。

## 4. 依頼者への報告事項

- 縮小版 WP-5 の統合コミットと、R-37 の閉止記録の所在。
- (1)(2)(5) を残余として記録した roadmap の版。
- R-45 WP-A の着手コミットと基点 main。
- 付録 C の報告事項 (Gate-0 の各項目の confirmed / blocked / unknown) は変更なし。

## 5. 本書が上書きするもの

- `HANDOVER_20260916_FABLE2.md` 付録 B の監督裁定 Z5-1 (範囲 6 件) → 本書 §3.1 (3 件)。付録 B の他の裁定は (3)(4)(6) に掛かる範囲で有効。
- `WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 の完了条件表 → (3)(4)(6) の行だけ。**§5.46 の本文は書き換えず、冒頭に本書への参照 1 行を足す** (監督が行う)。
- R-45 作業指示書 v1.1 §2 の「R-37 WP-5 の統合後」は**縮小版 WP-5 の統合後**と読む。
