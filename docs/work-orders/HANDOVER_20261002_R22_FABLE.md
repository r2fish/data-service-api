# 引き継ぎ書 — 2026-10-02 R-22 問い 3 の続き (変更セット 6b・7、cloud session)

本書は台帳 (`RM`) R-22 (問い 3: コード内の経緯コメントを記録へ移す) の変更セット 6b (R6-4 の日付の除去) と変更セット 7 (MitateDB `cell.py`) を cloud session (PostgreSQL 無し) で実施したチャットの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-22 問い 3 の正本は設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.27 (以下 設計) と作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` v1.15 (以下 作業指示書。§16 = 変更セット 6b、§17 = 変更セット 7) である。本書の Y6b-N は作業指示書 §16.5、Y7-N は作業指示書 §17.5 の監督裁定の番号、D-N は設計の番号である。前のチャットの記録: `docs/work-orders/HANDOVER_20261001_R108_FABLE.md`。

**本書の時点で変更セット 6b・7 は完了していない。** 両 peer の suite、gate、台帳の【追記】、設計 §10 の実施記録は作業機で行うまで未完である (「次の一手」)。

## 1. 現在地

- session: cloud (root コンテナ、PostgreSQL 無し。clone は shallow 241 commit で `80fad55` を持たない)。基点 = origin/main の先頭 `4241b55` (2026-10-02)。作業 branch `claude/loving-lamport-nwcoko` (origin に push 済み)。main には merge も push もしていない。
- commit 1: `802a24d` = 変更セット 6b (R6-4 の日付の除去) + 作業指示書 v1.14 (§16 = 6b の manifest、§17 = 変更セット 7 の manifest)。`tools/dev/finalize.py --no-merge` で commit した (identity は r2fish の noreply、branch を同じコマンドで確認。作業指示書 Y6b-7)。
- commit 2: `3915abf` = 変更セット 7 (MitateDB `cell.py`) + 作業指示書 v1.15 (§16.4・§17.4 の記録、§16.5 の Y6b-7〜Y6b-11、§17.5 の Y7-9〜Y7-21)。
- 作業機の main が先行している: `tools/dev/ledger.py --show R-121` が `RM` §8.1 の未閉止行を返し、台帳 R-121 の閉止と台帳 v1.150 が本 branch に無い (未送信)。本 branch は台帳・設計・`COLLECTION_FLOOR` に触れていない。
- 記録の置き場: 本書を commit する変更セットでは archive への移動を行わない (作業機の main が先行しているため)。移動は作業機で行う (「次の一手」の 6)。

### 1.1 変更セット 6b (`802a24d`)

- cloud で確認したこと: `--base 4241b55` (2 module: `comment provenance OK: 135 blocks checked`)、`--register` (`95 files scanned, 418 CH-IDs`)、`tools/check_doc_refs.py` 0 dangling、`tools/public_value_scan.py` 0、pre-commit 3 hook 緑、AST 同一 (P (1))、監査スクリプト exit 0 (REMOVED 7 = date 5 + ruling-word 2)、CLI の赤の変異 19 件が全部 red (`mutate: 19 mutations, 19 as expected`)、手作業の変異 15 (OTHER → exit 1、sha256 2 回一致)、`tools/tests` (基点 786 passed / 3 failed = PG 2 + shallow 1; 変更後 785 passed / 4 failed = 同 3 + `test_perf_baseline.py::test_real_server_default_client_processes_is_eight` (負荷依存、単独で緑))、L1 scan の非公式 `--noconftest` 12 passed (証拠にしない)。
- cloud で確認できなかったこと (作業機): 両 peer の suite (前 = `4241b55`、後)、conformance、`tools/tests` の正式実行 (PG あり)、行番号 pin の test (完了条件 14)、`removesuffix` の文字列検査 (完了条件 13)、`gate.py`、台帳の版上げと R-22 行の【追記】、設計 §10 の実施記録 (v0.28)、`COLLECTION_FLOOR`。

完了条件 → 変異 (作業指示書 §16.3 の 1〜19。変異の記録は作業指示書 §16.4):

| 完了条件 | 変異 / 照合 | 状態 |
|---|---|---|
| 1 | c1-r2db・c1-mdb | cloud で red |
| 2 | c2 | cloud で red |
| 3 | c3 | cloud で red |
| 4 | c4a・c4b・c4c・c4d | cloud で red |
| 5 | c5 | cloud で red |
| 6 | c6 | cloud で red |
| 7 | c7 | cloud で red |
| 8 | c8a・c8b | cloud で red |
| 9 | c9a・c9b (c9b は node c9a で観測。作業指示書 Y6b-8) | cloud で red |
| 10 | c10a・c10b | cloud で red |
| 11 | c11 | cloud で red |
| 12 | c12 | cloud で red |
| 13 | c13 (spec は「次の一手」の 3) | 作業機に残す (作業指示書 Y6b-5) |
| 14 | c14 (spec は「次の一手」の 3) | 作業機に残す (作業指示書 Y6b-5) |
| 15 | 監査照合 (固定スクリプト) + 手作業の変異 15 (OTHER → exit 1) | cloud で照合と赤を確認 (作業指示書 Y6b-6) |
| 16 | 監査照合 (点検語の候補 0) | cloud で照合 |
| 17 | 監査照合 (経緯トークン 50→46 / 117→115。suite の集計行は作業機) | 集計行は作業機 |
| 18 | 監査照合 (gate と `tools/tests`) | 作業機 |
| 19 | 監査照合 (`OC` §1.5 の 40) | 本表。対応の無い行は無い |

### 1.2 変更セット 7 (`3915abf`)

- WP 7a〜7d の 4 つの直列 WP (Opus の実装担当、各 WP の終わりに `--base` exit 0) で 211 塊を読み、46 塊を移し、レビュー A の指摘 (ラベル削除で前の文の `THIS commit` / 出所付きラベルの射程に次の文が入る) で 8 塊を基点に戻して欠番にした。移した塊は 38 (CH-0556〜CH-0602、欠番 9 = CH-0560 (入れ子の括弧の日付をチェッカーが拒む)、CH-0561・0569・0570・0575・0588・0592・0598・0600 (作業指示書 Y7-17))。除去は (6) ラベル 18 か所、(4) 括弧の語 ≈21 か所、(3) 文 1。経緯トークン 415 → 349。
- cloud で確認したこと: `--base 4241b55` = `comment provenance OK: 211 blocks checked`、`--register` = `95 files scanned, 456 CH-IDs`、監査 `SUMMARY ch_blocks=39 unchanged=1 ws_only=0 unpaired=0 removed_rows=40` (除いた語の一覧と 1 行ずつ一致)、変異 20 件 red (`mutate: 20 mutations, 20 as expected`)、手作業の変異 23・25 red、`_validate_delete_confirmation(` の count 1/2 不変、`#:` 20 不変、helper 4 塊の差分 0、AST 同一。`tools/tests` (PG 非依存) は 786 passed / 3 failed (基点と同じ PG 2 件 + shallow 1 件)。
- cloud で確認できなかったこと (作業機): 両 peer の suite、`MitateDB-api/tests/test_application_audit.py` の文字列検査 (変異 c21、spec は「次の一手」の 3)、gate。
- レビュー: A (低 2: ラベル削除で前の文の射程に次の文が入る 2 + 6 塊) / B (中 1: 根拠が scratchpad の裁定を指す、軽微 2、観察 1) → 差し戻し 1 (8 塊を戻して欠番、作業指示書 §17.5 に Y7-9〜Y7-21、§17.4 の記録の修正、変異のやり直し 20 件 red) → 再確認 (軽微 3: c8 の該当なしの記録、7b-x2 の件数、版数行 v1.15。全部直した)。

完了条件 → 変異 (作業指示書 §17.3 の 1〜30。変異の記録は作業指示書 §17.4 の差し戻し 1 の後の表):

| 完了条件 | 変異 / 照合 | 状態 |
|---|---|---|
| 1 | c1 | cloud で red |
| 2 | c2 | cloud で red |
| 3 | c3 | cloud で red |
| 4 | c4a・c4b・c4c・c4d | cloud で red |
| 5 | c5 | cloud で red |
| 6 | c6 | cloud で red |
| 7 | c7 | cloud で red |
| 8 | 該当なし (CH を付けた 38 塊に版数付き文書名が無い)。監査照合 | 作業指示書 Y7-19 |
| 9 | 監査照合 (helper 4 塊の差分 0、`_ISOMORPHIC_TARGETS` の差分 0) | cloud で照合 |
| 10 | 該当なし (訂正の記録 (0g) が 0 件)。監査照合 | 作業指示書 §17.4 |
| 11 | 監査照合 (`#:` 20 不変) | cloud で照合 |
| 12 | c12a・c12b・c12c | cloud で red |
| 13 | c13a・c13b・c13b-md (c13b-md は node c13a) | cloud で red (作業指示書 Y7-16・Y7-18) |
| 14 | 監査照合 (候補一覧とコードレビュー) | cloud で照合 |
| 15 | 監査照合 (判定表の根拠とレビュー) | cloud で照合 |
| 16 | 監査照合 (grep の結果と参照先一覧) | cloud で照合 |
| 17 | c17a・c17b | cloud で red |
| 18 | c18 | cloud で red |
| 19 | c19 | cloud で red |
| 20 | 監査照合 (件数 pin `"cell.py": 44` の差分 0) | 作業指示書 Y7-18 |
| 21 | c21 (spec は「次の一手」の 3) | 作業機に残す。cloud では `_validate_delete_confirmation(` の count 1/2 不変だけ |
| 22 | 監査照合 (判定表 211 塊、目印 95 文) | cloud で照合 |
| 23 | 監査照合 (固定スクリプト) + 手作業の変異 23 | cloud で red |
| 24 | 監査照合 (固定スクリプトの再実行の出力) | cloud で照合 |
| 25 | 監査照合 (固定スクリプト) + 手作業の変異 25 | cloud で red |
| 26 | 監査照合 (監査一覧と判定表) | cloud で照合 |
| 27 | 監査照合 (変えた docstring の 1 文字ずつの照合) | cloud で照合 |
| 28 | 監査照合 (経緯トークン 415 → 349。suite の集計行は作業機) | 集計行は作業機 |
| 29 | 監査照合 (gate と `finalize.py --tools-tests`) | 作業機 |
| 30 | 監査照合 (`OC` §1.5 の 40) | 本表。対応の無い行は無い |

## 2. 本チャットで閉じたもの

cloud で行える範囲だけを閉じた。作業機の検証 (suite・gate・台帳・設計 §10) は「次の一手」。

| 段 | commit | 内容 | レビュー | 変異 |
|---|---|---|---|---|
| 変更セット 6b | `802a24d` | 5 塊: `control_main.py` の手順 5b の docstring = CH-0551、`(design amendment, N-7)` の塊 = CH-0552、CH-0509 の再編集 (日付だけ); `backend_postgres.py` の `field_domains` の except = CH-0553 (日付だけ。`supervisor ruling,` は残る)、`add_field` の M-6 = CH-0554。CH-0555 は欠番。`_BACKEND_LAYER_ALLOWLIST` 19 件中 17 件の値を +1/+2。経緯トークン 50→46 / 117→115 | A 軽微 1・B 4、再確認 3 (全件裁定は「裁定」節) | 19 (CLI の赤) + 手作業 15。13・14 は作業機 |
| 変更セット 7 の選定 | `802a24d` (manifest) | MitateDB `cell.py` (設計 §6 優先 1 の残り 2 module を行数順で: `cell.py` 82 塊/1714 行 (helper 除き 79/1643) > `structured.py` 24/366)。census は作業指示書 §17.2。CH-ID 予約 CH-0556〜CH-0762 | — | — |
| WP 7a (L1-1000) | `3915abf` | 43 塊 / 移した 4 (CH-0556〜0559) / 欠番 0 | (変更セット 7 のレビューに含む) | — |
| WP 7b (L1001-2000) | `3915abf` | 68 塊 / 移した 17 (CH-0561〜0577) / 欠番 1 (CH-0560、7b-x1) | 同 | — |
| WP 7c (L2001-3000) | `3915abf` | 54 塊 / 移した 10 (CH-0578〜0587) / 欠番 0 | 同 | — |
| WP 7d (L3001-3908) | `3915abf` | 46 塊 / 移した 15 (CH-0588〜0602) / 欠番 0 | 同 | — |
| 差し戻し 1 | `3915abf` | レビュー A-1/A-2 (作業指示書 Y7-17) で 7b の 4 塊 (CH-0561・0569・0570・0575) と 7d の 4 塊 (CH-0588・0592・0598・0600) を基点に戻して欠番 → 最終 38 塊 | A 低 2・B 中 1・軽微 2・観察 1、再確認 軽微 3 | 20 (CLI の赤、やり直し) + 手作業 23・25。21 は作業機 |

- 判定表は作業指示書 §17.4 (7a-1〜7d-82、211 塊、目印 95 文)。
- 移せた塊が少ない (差し戻し前 46、最終 38、対象 207) のは設計のとおり: `Phase N WP-X (design D-n):` 型のラベルは除外 2 (保護参照) で消せず、入れ子の括弧の日付も (4) の部位にならない (依頼者の判断材料: 「依頼者判断待ち・未決」の設計への疑義)。

## 3. 次の一手

作業機で行う。

1. `git fetch origin claude/loving-lamport-nwcoko` → `git worktree add .claude/worktrees/r22-cs6b origin/claude/loving-lamport-nwcoko` (branch を main の先頭に rebase せず、main を merge するなら `--no-ff`)。作業機の main が先行 (台帳 R-121 の閉止、台帳 v1.150) していれば、worktree で main を取り込む (作業指示書と台帳は衝突しないはず: 本 branch は台帳・設計・`COLLECTION_FLOOR` に触れていない)。
2. 両 peer の suite の前後 (40a): 前 = `4241b55` (作業機の main の先頭ではない点に注意) で `tools/dev/pt.py -C <WT> -- r2db-api/tests -q` / `-- MitateDB-api/tests -q` / `-- conformance-tests -q`、後 = commit `3915abf` (6b と 7 を含む branch の先頭)。
3. 変異 13・14 (下の 1 つ目の JSON) を `tools/dev/mutate.py <spec> -C <WT>` で。変更セット 7 の変異 c21 (下の 2 つ目の JSON)。どちらも cloud session の scratchpad にあった spec の全文で、`tests` の node id はリポジトリ相対である。作業機の scratchpad にファイルとして置いてそのまま渡す。

   変更セット 6b の変異 13・14 (完了条件 13・14):

   ```json
   {
    "pytest": ["-q"],
    "mutations": [
     {"id": "c13", "expect": "red",
      "file": "r2db-api/src/r2db_api/control_main.py",
      "old": "    # history: CH-0552\n",
      "new": "    # never via removesuffix\n    # history: CH-0552\n",
      "tests": ["r2db-api/tests/test_ops_declarations.py::test_no_naming_convention_role_derivation_remains_in_composition_roots"]},
     {"id": "c14", "expect": "red",
      "file": "MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py",
      "old": "    (\"backend_postgres.py\", 702),   # field_domains: generic driver-exception translation\n",
      "new": "    (\"backend_postgres.py\", 701),   # field_domains: generic driver-exception translation\n",
      "tests": ["MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites"]}
    ]
   }
   ```

   変更セット 7 の変異 c21 (完了条件 21):

   ```json
   {
    "pytest": ["-q"],
    "mutations": [
     {"id": "c21", "expect": "red",
      "file": "MitateDB-api/src/mitatedb_api/cell.py",
      "old": "            # capability gap, not a malformed request.\n            # history: CH-0584\n",
      "new": "            # capability gap, not a malformed request.\n            # (not self._validate_delete_confirmation( here)\n            # history: CH-0584\n",
      "tests": ["MitateDB-api/tests/test_application_audit.py::test_dispatch_point_is_the_destructive_confirmation_choke"]}
    ]
   }
   ```

4. `tools/dev/gate.py -C <WT> --label r22-cs7` (branch の先頭 `3915abf` で 1 回。6b と 7 は同じ branch の連続する commit なので gate は 1 回でよい。作業指示書 §16.3 の完了条件 18 の label `r22-cs6b` は、この 1 回の集計行を 6b の記録にも書くことで満たす (訂正註は作業機で §16 に足す)。台帳の【追記】は変更セットごとに書く)。
5. 台帳 (`RM` v1.151 以降) の R-22 行に【追記 2026-10-02】(6b: 5 塊、CH-0551〜0554、`802a24d`; 7: `cell.py` 211 塊中 38 塊、CH-0556〜0602 (欠番 9)、`3915abf`)。設計 v0.28 §10.8 に実施記録 (6b と 7 の選定、教訓)。`COLLECTION_FLOOR` は gate の実測で。`security/CONTROL_MAPPING.md` の位置参照 6 件 (作業指示書 §16.4 の表) の取り直しは、`CONTROL_MAPPING` の次の版上げ (台帳 R-28 の是正と同じ変更セットでよい、Class D) で。
6. `tools/dev/finalize.py -C <WT> --branch claude/loving-lamport-nwcoko --allow ... -m ...` で main へ `--no-ff` merge (CI は main の push で走る。push は Mitate 側の監督セッションが統制)。`HANDOVER_20261001_R102_FABLE.md` を `docs/archive/` 配下へ移す (`OC` §1.16 の 78。cloud では行わなかった)。
7. 変更セット 7 の残り: `evidence-auditor` の受け入れ監査 1 回 (規模 L。cloud では起動していない。作業機の suite・gate の後に起動し、材料は作業指示書 §16.4・§17.4 と本書の「裁定」節)。変更セット 8 の候補は r2db `structured.py` (作業指示書 §17.2 の census)。

## 4. 依頼者判断待ち・未決

- 依頼者判断待ちは無し (登録 helper の Class C の変更セット (設計 §7 Q-1) は着手時に依頼者確認)。
- 設計への疑義 (依頼者の判断材料。本変更セットでは設計を変えていない):
  1. 移せた塊が 38/207 と少ない理由 = `Phase N WP-X (design D-n):` 型のラベルは除外 2 (保護参照) で消せず、入れ子の括弧の日付は (4) の部位にならず、`L-3/M-4` の `/` 結合 ID はラベルの語数に数えられる (作業指示書 Y7-12)。許容操作の追加 (部分的なラベル削除、外側の括弧の部位化) はチェッカーの設計変更 (設計 §8・§9 の追補) になる。
  2. (6) でラベルを消すと前の文の `THIS commit` / 出所付きラベルの射程に次の文が入る (作業指示書 Y7-17)。設計 §3 の「削除前の確認」に足す候補。
  3. 0g は CH-ID の塊にしか使えず、CH-ID の無い塊の今は事実でない文 (`cell.py` L3664-3683 の cursor pagination の文、`self.rollback()`・`filters_path` の名、位置の語のずれ) は直す経路が無い (作業指示書 Y7-10)。別のコメント訂正の変更セットが候補。
  4. `契約 1.7.0` (日本語の版数付き文書名) は `_VERSIONED_DOC_RE` で保護されない (作業指示書 Y7-20)。checker の Known gaps に書く候補 (tools の変更セット)。
  5. 監査スクリプト `tokens()` の `.` の穴 (作業指示書 Y7-16)、作業指示書 §14.3 の 13(b) の雛形 (作業指示書 Y7-18) は次の変更セットの manifest で直す。
- `security/CONTROL_MAPPING.md` の位置参照のずれ: 6b で 6 件 (作業指示書 §16.4 の表)、7 で `cell.py:NNN` の参照 (作業指示書 §17.4 の表の「WP 7d の後」の列。差し戻し 1 の後の最終値は再計測が要る: 8 塊の戻しで行数 3966 → 3958)。`CONTROL_MAPPING` の次の版上げ (Class D) で取り直す。
- 確認を求めるもの (再審議ではない): 作業指示書の裁定 Y6b-1〜Y6b-11、Y7-1〜Y7-21 (作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` §16.5・§17.5。Y7-17 = レビュー A の指摘で 8 塊を基点に戻して欠番にした裁定を含む)。

## 5. 運用上の教訓

- repo 外に置いた pytest の wrapper は root conftest を読まないので、CLI の赤の変異は PG 無しで `mutate.py` が回せる (18/22 passed の wrapper)。
- clone は shallow: 古い基点 (`80fad55`) は参照できない。基点は clone した origin/main の先頭にし、旧位置は原文の一致で同定する。
- `--noconftest` で静的テスト (L1 scan) を参考実行できるが、証拠には使わない。
- 枠の判定を別 worktree (`git worktree add --detach`) で先に試すと、チェッカーが拒む除去 (塊 4 の句の除去) を発注前に知れる。
- `tools/tests` は PG 2 件と shallow 1 件が必ず赤; `test_perf_baseline.py` の 8 プロセスの test は負荷で揺れる (単独で緑)。
- 位置参照のずれ (`CONTROL_MAPPING`) は provenance の変更セットが新たに作る。§x.2 の参照表を必須にした (作業指示書 Y6b-11、Y7-8)。
- `finalize.py --no-merge` は main checkout の branch でも使える (identity・allowlist・doc-refs・公開値の検査が走る)。`--tools-tests` は PG 無しでは付けない。

## 6. 裁定

`OC` §1.15 の 77。語は 起票 R-N / 既知の穴 (§1.12 の 71) / 観察 / 直した の 4 語。材料は変更セット 6b の実装報告・レビュー A / B・再確認、変更セット 7 の実装報告 (WP 7a〜7d、変異、差し戻し 1)・レビュー A / B・再確認。表の順は時系列。節番号は断りの無い限り作業指示書の節、Y6b-N・Y7-N は作業指示書の裁定番号である。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 6b 実装・逸脱 5(a) (変異 9b を node c9a で観測、c9b は (3) に届かない) | 直した | 記録 (Y6b-8)。fence だけの変異は (2) で止まるのが正しい信号 |
| 6b 実装・逸脱 5(b) (完了条件 1 を 2 module に分けた) | 観察 | 受け入れ。module ごとの赤を見る方が強い |
| 6b 実装・逸脱 5(c) (40b の pin は 19 件、値の変更 17 件) | 直した | 記録 (Y6b-10)。§16.3 の 20 行は起草の誤り |
| 6b 実装・逸脱 5(d)(e) (mutate のログの置き場と名前の置き換え) | 観察 | 受け入れ。公開値走査 R3 の誤検出を避ける開示済みの置き換え |
| 6b 実装・疑義 6 (塊 4 の `supervisor ruling,` が残る) | 観察 | Y6b-9。R6-1 は日付だけ。後の変更セットで (4) により判定 |
| 6b レビュー A・軽微 (`backend_postgres.md` の空行 2 つ) | 直した | 空行 1 つに |
| 6b レビュー B-1 (`CONTROL_MAPPING` の位置参照 6 件のずれ) | 観察 | Y6b-11 (§16.4 に前後の表)。検査器の穴 (台帳 R-88 の Known gaps 1) を通る製品の欠陥は無く、DB の利用者は気づかない。作業機で `CONTROL_MAPPING` の次の版上げ (台帳 R-28 の是正と同じ変更セットでよい) に取り直しを含める |
| 6b レビュー B-2 (§16.3 の 9b と 40b が実測と食い違う) | 直した | 記録 (Y6b-8・Y6b-10)。本文は書き換えず §16.5 に追記 |
| 6b レビュー B-3 (CH-0552 と R6-3 の CH-0508 の関係が辿れない) | 直した | 判定表の行 2 の根拠に 1 文 |
| 6b レビュー B-4 (§1.9 に文書名が無い) | 直した | `OPERATING_CONDITIONS.md` §1.9 |
| 6b レビュー B・注記 (変更後の `tools/tests` が未実測) | 直した | 監督が回した: `4 failed, 785 passed` (PG 2 件・shallow 1 件・負荷依存 1 件 `test_perf_baseline.py::test_real_server_default_client_processes_is_eight` は単独で緑) |
| 6b 再確認 R-1 (句点) | 直した | — |
| 6b 再確認 R-2 (code span の中の backtick) | 直した | 2 重の backtick |
| 6b 再確認 R-3 (参照表の置き場所 §x.2 と §17.4) | 直した | Y6b-11 の括弧を「起草済みの変更セット 7 は §17.4」に |
| 7 実装 7a・5c ((6) で消せるラベルを、次の文の `this WP` の指示先が消えるため残した) | 観察 | 受け入れ。設計 §3 の指示語の確認を (6) にも当てる読み。移せる塊は減るが誤削除を防ぐ側に倒す |
| 7 実装 7a・5d (`Phase N WP-X (design D-n):` 型のラベルは除外 2 で消せず、移せた塊が 4/38) | 観察 | 設計への疑義として本書「依頼者判断待ち・未決」に残す。部分的なラベル削除は許容操作の追加 = チェッカーの設計変更。本変更セットではしない。依頼者の判断材料: `cell.py` の多くの塊が「残す」で終わる |
| 7 実装 7a・5f (移した塊の中の位置の語・行番号のずれを 0g で直さず記録だけ) | 観察 | 設計 §3 の別件、§14.4 の先例。直すなら新文の事実照合が要る。記録は §17.4 の判定表 |
| 7 実装 7a・5g (`test_http.py:123` の参照先の docstring が無い、`config.py:41` の参照先が基点に無い) | 観察 | 移動前からの穴 (§14.2 の「無い」の先例と同じ) |
| 7 実装 7a・5b (`CONTROL_MAPPING` の `:373` の `cell.py:3570` が基点で既にずれている) | 観察 | Y6b-11 と同じ扱い。作業機の `CONTROL_MAPPING` の次の版上げで取り直す |
| 7 実装 7b・欠番 CH-0560 (入れ子の括弧の日付を (4) で消せず、0d の文言で拒まれる) | 観察 | 設計への疑義として本書「依頼者判断待ち・未決」に残す。チェッカーの部位は最内の括弧。外側も部位にするのは許容操作の拡張 = 設計変更。診断の文言は読み取りにくいが、製品の欠陥がゲートを抜ける穴ではない。残り L1960・L2258 は「残す」 |
| 7 実装 7b・5a (欠番の直後に監査スクリプトを再実行していない) | 直した | 記録。実行 2 で全ファイル走査、byte 一致は確認済み。7c 以降は欠番の直後に再実行する指示を足した |
| 7 実装 7b・5b (ラベル削除で 1 語だけ残った行を次の行に寄せた) | 観察 | 受け入れ。語の並び不変の局所の折り返し。塊全体の折り返し直しではない |
| 7 実装 7b・5d (`監督裁定 N-1` を他の塊が参照するので日付だけ除いた) | 観察 | 受け入れ。判定に迷う → 残す (設計 §3) |
| 7 実装 7b・6 ((6) の後の小文字始まり) | 観察 | 設計 §8.1 の「変形しない」のとおり。可読性の論点は依頼者の判断材料として本書に |
| 7 実装 7b・6 (`追補 L-1`・`監督裁定 N-2`・`m-1`・`m-2` を裸の局所 ID として除いた) | 観察 | レビューで確認。設計 §3 の「出所を持たない裸の局所 ID」。L-1 が他の塊にラベルとして残る点はレビュー B に照合させる |
| 7 実装 7c・5a/6 (出所の無い裁定 ID の境目: K-1 は消し、I-7 は残した) | 観察 | 裁定: (i) 同じファイルの docstring で定義された規則の名は残す / (ii) 参照の無い裁定・指摘のタグは消せる / (iii) 他の塊や test が参照して同一性が判らないものは残す。設計 §3 の「判定に迷う → 残す」の具体化。7d の発注に逐語で入れた |
| 7 実装 7c・6 (名前の食い違い `self.rollback()`・`filters_path` を 0g で直さず記録だけ) | 観察 | 訂正候補として本書に。位置の語と同じ扱い。直すなら新文の事実照合を独立レビューで |
| 7 実装 7c・6 (`L-3/M-4` の `/` 結合 ID をチェッカーが内容語 1 語と数え、ラベルが消せない) | 観察 | 設計への疑義として本書に。設計 §9 規則 4 がラベルの語数に効いていない穴の可能性。製品の欠陥がゲートを抜ける穴ではない。設計変更は本変更セットの外 |
| 7 実装 7c・5c (行末の閉じ `"""` を次の行に分けた) | 観察 | 受け入れ。設計 D-2 の形 (末尾に `History:` 行) を満たすための最小の編集。7a の CH-0559 と同形 |
| 7 実装 7d・6a (CH-0589 で scratchpad の裁定ファイルの名を (4) で除いた。監査スクリプトの REMOVED に出ない) | 観察 | 受け入れ。設計 §9 規則 2 のとおり。受け皿の写しには残る (先例あり) |
| 7 実装 7d・6b (CH-0593 で行頭に残る `: ` を前の行末に寄せた) | 観察 | 受け入れ。局所の折り返し。語の並び不変 |
| 7 実装 7d・6g/7 (CH-ID の無い塊 L3664-3683 に今は事実でない文 (`this peer implements no cursor pagination ...`)。0g は CH-ID の塊にしか使えない) | 観察 | 訂正候補として本書に (設計への疑義)。本変更セットでは直さない。訂正だけの CH-ID を許す設計変更は依頼者の判断材料。別のコメント訂正の変更セット (台帳 R-28 の是正と同じでよい) が候補 |
| 7 実装 7d・7 (出所の無い ID の境目: tests が参照する K-1・L-1 は消し、鍵として参照される K-3・O-2・M-3 は残した) | 観察 | 裁定: 「他の箇所がこの箇所を指す鍵として使うか」を境目とする。tests に現れるだけの ID は経緯。レビュー B に一貫性を照合させる |
| 7 実装 7d・7 (`THIS commit` が指すラベルを残した) | 観察 | 受け入れ。指示語の指示先を残す側に倒す (7a の 5c と同じ) |
| 7 実装 変異・(d) (監査スクリプト `cs7_removed_tokens.py` の `tokens()` が `` `). `` の形の実在ファイル名を数えない) | 観察 | 次の変更セットの固定スクリプトでは `.` を strip してから照合する。スクリプトは scratchpad の固定スクリプト (リポジトリの検査器ではない)。P (0d) が保護参照の除去を拒むので製品の欠陥は通らない。本変更セットでは basename の出現数が基点と作業ツリーで全件一致 (レビュー B に照合させる) |
| 7 実装 変異・(b) (13(b) をコード側 c13b と受け皿側 c13b-md の 2 形で観測) | 観察 | 受け入れ。Y6b-8 の解釈の両方を覆う |
| 7 実装 変異・(c) (変異 19 の番号を 2 桁 + 枝で作った) | 観察 | 受け入れ。roadmap に R-1〜R-99 が全部ある。`check_doc_refs` の dangling 1 件で赤を観測 |
| 7 実装 変異・(a) (1 回目の mutate のログが scratchpad の外に出た) | 観察 | 6b と同じ。結果は同じ 21 OK、2 回目を記録 |
| 7 レビュー A・1 (CH-0598・CH-0600 で K-1 のラベルを消し、前の文の `THIS commit` の射程に移動の経緯が入る) | 直した | Y7-17: 基点に戻し欠番。経緯の帰属が事実でなくなる除去は許容しない |
| 7 レビュー A・2 (CH-0561・0588・0592・0569・0575・0570 でラベルを消し、前の文の出所付きラベルに帰属して読める) | 直した | Y7-17: 基点に戻し欠番。不確実の指摘だが、残した出所付き参照が正しいことが目的そのもの。規律を Y7-17 に、設計 §3 への追補候補を本書に |
| 7 レビュー B-1 (判定表の根拠が scratchpad の裁定を指し作業指示書で閉じない) | 直した | §17.5 の Y7-9〜Y7-16 に逐語で追記。6b の Y6b-8〜11 の先例と同じ |
| 7 レビュー B-2 (完了条件 20 の監査照合の記録が無い) | 直した | Y7-18 |
| 7 レビュー B-3 (c13b の赤が折り返しの実在パスの保護に依存しない) | 直した | 記録の注記 (Y7-18)。作業ツリーに D-2 の無い対象が無い。§14.3 の 13(b) の雛形は次の変更セットで直す (観察) |
| 7 レビュー B-4 (7b-d5 の根拠に test の N-2 の参照が無い) | 直した | Y7-18 |
| 7 実装 fix1・7a (c8 の対象が無い) | 観察 | Y7-19: 完了条件 8 は該当なしを監査照合で記録。元の 3 件は欠番にした塊にあった |
| 7 実装 fix1・8 (`契約 1.7.0` が版数付き文書名として保護されない) | 観察 | Y7-20。作業機で checker の Known gaps に書く候補。製品の欠陥は通らない。`tools/` は本変更セットの外 |
| 7 実装 fix1・7b (c2・c13a・c19 の受け皿の対象も CH-0588 だったので CH-0593 に移した) | 観察 | 受け入れ |
| 7 実装 fix1・7f (戻した塊に関わる §17.4 の既存記述を書き換えていない) | 観察 | Y7-21: 差し戻し 1 の行が上書き。`OC` §1.8 の 57 |
| 7 再確認・R-1 (完了条件 8 の該当なしが §17.4 に無い) | 直した | 監督。Y7-19 の記録の行を変異表の直後に足した |
| 7 再確認・R-2 (7b-x2 の件数 16 → 15) | 直した | 監督。未確定の記録なので直接直し、版数行に明記。実測 15 + 3 = 18 |
| 7 再確認・R-3 (版数行) | 直した | 監督。v1.15。`OC` §1.8 の 56 |
| 7 再確認・観察 1 (Y7-9 の読み替え表に裸の「(監督の裁定)」等が無い) | 観察 | 内容から Y7-11 / Y7-12 に一意に辿れる |
| 7 再確認・観察 2 (13(b) の実在パスだけの拒否に機械の証拠が無い) | 観察 | Y7-18 で裁定済み。次の変更セットで雛形を直す |
