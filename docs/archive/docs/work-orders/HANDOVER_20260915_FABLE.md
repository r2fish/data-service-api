# 引き継ぎ — 2026-09-15 (第18次。R-37 巨大モジュール分割と R-22 コメント出所整理。契約は 1.8.0 のまま)

前書 `docs/work-orders/HANDOVER_20260910_FABLE.md` の全項を継承する。このチャットの規律は `docs/work-orders/OPERATING_CONDITIONS.md` (§1.5 の 40a〜40c、§1.10 の 64〜67) にある。

## 1. 現在地 (main)

- main は `d236d0b`。R-37 WP-3c 統合後、root gate は 3388 passed (pg_database/pg_roles 差分 0)、tools/tests は 392 passed で緑。push は GitHub の請求上限のため停止中で、ローカルの main だけを進めている。
- 作業ツリー:
  - `.claude/worktrees/r37-wp0` (R-37 用): main と同じ位置で、未コミットの変更は無い。
  - `.claude/worktrees/ccp-cs0` (R-22 コメント出所用): **ブランチに WIP コミット `0ba9521` がある。未レビューで、main にはマージしていない** (§4-1)。
  - `.claude/worktrees/mitatedb-operation-depth-platform-plan`: 別のエージェントの作業ツリー。触らない。

## 2. 到達した状態

### 2.1 R-37 (設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md`、作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md`)
- WP-1 の抽出 (1-0、1a〜1n) はすべて完了した。記録は設計 §10.1〜§10.7 にある。
- WP-2a を統合した。削除確認 phrase の契約規則を、両 peer の tests で固定した。同型性の表には登録していない (裁定 Y-6)。R-39 の (1b)・(1g) を閉じ、conformance のベクトルは R-41 に回した。記録は §10.8。
- WP-3a (`service_results.py`)、WP-3b (`capabilities_document.py`)、WP-3c (`request_shape.py`) を統合した。いずれも r2db だけで、認証・rate・slot・audit の順序は facade に残した。
  - WP-3b: ロールとデプロイ設定の 240 通りで出力が同一であることを、レビューで確認した。
  - WP-3c: 認証の後に形の検査が走ることと、拒否が監査に残ることを、tests で固定した。
  - **WP-3a〜3c の設計記録 (§10.9) は未記入** (§4-2)。

### 2.2 R-22 コメント出所 (設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md`、作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md`)
- 統合済み:
  - 変更セット 3 と 4
  - 0e と 0f: 境目の述語 B (条件 1〜8)
  - 0g: 受け皿への訂正の記録、訂正で保護参照を減らさない規則、`#:` の扱い
  - 事実訂正 (CH-0239、CH-0139)
- 登録済みの CH-ID は 378 (main)。

## 3. クライアント連携状態
前書から変更なし。

## 4. 次の一手 (優先順)

### 4-1. 変更セット 5 と 0h を仕上げる (ccp-cs0 の WIP `0ba9521`)
- **中身:**
  - 変更セット 5: r2db `credential_store.py` の 28/70 塊、MitateDB `ops.py` の 32/53 塊。CH-0381〜0441 で、CH-0425 は欠番。
  - 0h: span の隠蔽順の修正と、述語 B の条件 9 (CJK の改行は空白なしでつなぐ)。
  - 経緯は 2 回の差し戻しを経て、新しい実装担当が修正した。修正後の最終レビューはまだ。
- **残りの手順:**
  1. 作業ツリーを main に揃える。WIP を main の上に載せ直すか、`git reset --soft` で未コミットに戻してから揃える。
  2. 条件 9 が、変更セット 1〜4 で統合済みの src に空白入りの日本語の改行を 17 か所見つける。
     - 内訳: r2db `postgres.py` CH-0012、`control_plane.py` 1、`ops.py` 7、`service.py` 1、MitateDB `backend_sqlite.py` 4、`http.py` 2。
     - チェッカーが示す「should be」の形で、空白なしにつなぎ直す。受け皿は触らない。
     - 検出はコミットした clone で `tools/tests` を流すと出る (`test_q4_real_repo_postgres_unchanged_is_green` と `test_0f_both_peers_all_src_rev_vs_itself_is_green`)。
  3. 独立レビュー (Opus): 0h、全変更文と基準の 1 文ずつの照合、§13.2 の安全上の理由、§13.4 の判定表 144 行。
  4. `tools/dev/gate.py -C .claude/worktrees/ccp-cs0 --label cs5`
  5. 2 段で finalize する。
     - まず `finalize.py --allow 'tools/*' --allow 'docs/design/CODE_COMMENT_PROVENANCE_V1.md' --leave '<変更セット5の対象>' --no-merge`
     - 次に `finalize.py --allow '<変更セット5の対象>' --tools-tests`

### 4-2. 記録
- R-37: 設計 §10.9 に WP-3a〜3c を書き、ロードマップの R-37 行に追記する。
- 移動前からの穴を R-39 に足す:
  - `r2db-api/tests/test_foundation.py:439` が、ソースに存在しないコメントを参照している。
  - WP-3a の review が見つけたコメントの崩れ: `service.py:837`「every existing caller --, the in-process」と、`service_results.py:14`「CCR-13 introduced `items`/`next_page` adds `revisions`」。
- R-22: 設計に 0h と変更セット 5 を記録し、ロードマップの R-22 行に追記する (4-1 の統合後)。

### 4-3. 後続
- 上の 2 か所のコメントの崩れを、訂正の記録を付けて直す。
- R-37 WP-3d 以降 (ST8〜ST10、CE5〜CE7) を実測して起草する (裁定 W3-1)。
- MitateDB `backend_postgres.py` のコメント整理 (裁定 Y-5。WP-4 の前、BP3 は WP-4)。
- 変更セット 6 の候補: 設計 §6 の優先順から実測する。

### 4-4. 依頼者判断待ち
- R-40: `number` の NaN/±Infinity を契約で禁止するか。共通契約の判断で、フェーズ11。
- R-38 / R-39 / R-41 はフェーズ11 (Class B/C)。

### 4-5. GitHub 復旧後にすること
前書 §4-5 を継承する。push は停止中。

## 4-6. 運用規律 (本チャットで足したもの)
- **道具:** 定型手順は `tools/dev` の道具 (pt / mutate / gate / finalize / section / handover_ready) で行う。subagent のプロンプトには必ず `export SP=...` を入れる。終了コード 75 は迂回しない。
- **モデルの使い分け:**
  - 所在の特定は Haiku に任せ、出力は scratchpad のファイルに書かせる。決め手になる検査は監督が再実行する。
  - 読解は Sonnet。
  - 実装は Sonnet、起草・レビュー・監査は Opus。
- **コミットと統合:**
  - src のコメントを変えるコミットは、コミットした後の HEAD で tools/tests を流す (rev guard が HEAD を読むため)。
  - src の行数が変わる変更は、コメントだけでも root gate を通してから統合する (行番号 pin があるため)。
  - CH-ID の付いた塊に括弧書きを足すときは、受け皿に訂正の記録を足す (0g の項 4)。
  - 共有文書を下書きさせる前に、その worktree を main に揃える。
- **エージェントの扱い:**
  - 文脈が大きいエージェントや、長く待機したエージェントに修正を頼むときは、新しいエージェントを引き継ぎファイル 1 つで起動する。
  - 実装担当が spawn_task で脇道のチップを出したら、取り下げて本流に取り込む。

## 5. 教訓の追加
- 機械的な除去 (4)(6) は許可であって義務ではない。文法や意味 (特に安全上の理由) が崩れるなら使わない。判定表は §3 の区分だけを使う。
- 改行の規則は、検査を足す前に全境目を調べてから決める (0e〜0f、条件 9 でも同じ型が繰り返した)。
- 監督の手順漏れで main を 2 回赤にした:
  - 事実訂正の後に tools/tests を流さなかった。
  - 0g の行ずれで root suite が赤になった。
  - どちらも、道具 (`finalize.py --tools-tests`、`gate.py`) を通すことで防ぐ。
