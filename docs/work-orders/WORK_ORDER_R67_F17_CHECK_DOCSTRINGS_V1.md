# 作業指示書 — R-67 両 peer の `check_auditreader_statement_timeout` に docstring を置く

## 0. 版数・位置づけ

- **v1.0 (2026-09-22)。** 基点 main `b3dd0c3`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-67。変更クラスは **Class B** (判定は §1 の D-4)。設計文書は起こさず、決定は本書 §1 に置く。契約 `spec/`・`security/`・`conformance-tests/` は触らない。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: 両 peer の `check_auditreader_statement_timeout` (`r2db-api/src/r2db_api/platform_declarations.py:1142`、`MitateDB-api/src/mitatedb_api/platform_declarations.py:1116`) は docstring を持たない。同じ module の他の `check_*` は持つ (例: `check_role_connection_limits`)。R-56 の時点で `tools/check_comment_provenance.py` が新しい関数の docstring を赤にしたので、docstring 無しで置いた (R-56 の監督裁定 A-1)。

**台帳の前提の訂正 (実測 2026-09-22)**: 台帳は「道具は R-63 で直ったので書ける」と書くが、R-63 が直したのは**基準 rev に無い symbol** への追加だけで (R-63 の D-1)、基準 rev に在る対象への追加は今も赤である (同 D-2)。この関数は今は基準 rev に在るので、docstring を足すと `--base` は次を出す (監督が worktree で実測):

`FAIL (§4.1 (2)) r2db-api/src/r2db_api/platform_declarations.py:1143 scope/anchor ('check_auditreader_statement_timeout', 'stmt#0'): the sequence of CH-ID-less blocks changed (old 0, new 1)`

`--register` は緑のまま。`--base` は CI・pre-commit・`tools/dev/finalize.py` のいずれにも入っておらず (grep 0 件)、変更時に人が読む照合である。

**決定**:

- **D-1。** 両 peer の `check_auditreader_statement_timeout` に同じ docstring を置く。文は監督の確定文 `$SP/r67-final/docstring.txt` を逐語で複製する (`OPERATING_CONDITIONS.md` §1.5 の 35)。経緯 (誰がいつ決めたか、台帳 ID、WP、日付) は書かず、今の挙動と、読み手が誤解しやすい点 (判定するのは宣言であって実効値ではない / 見る per-database 行はこの接続の database のものだけ / 起動時には走らない) だけを書く。
- **D-2。対象はこの 2 本だけ。** R-56 の読み替えが効いていた期間に docstring 無しで入った関数を実測した (基準 `80d1495` = 2026-09-18 より前の main に無く、現行で docstring を持たない関数): 両 peer の `_f17_message` と `check_auditreader_statement_timeout` の 4 本だけ。`_f17_message` は同じ module の `_f1_message`・`_f6_forward_message`・`_f6_reverse_message`・`_f7_message`・`_f9_message`・`_f13_message`・`_f15_shape_message`・`_f16_message` がいずれも docstring を持たない形に揃っているので足さない。台帳が挙げた R-52 WP-3 は `security/` と文書だけの変更で、関数を足していない。
- **D-3 (`--base` の赤の扱い)。** `--base b3dd0c3` の赤は、上の `§4.1 (2)` の行が peer ごとに 1 行、計 2 行だけであることを完了条件にする。`§4.1 (1)` (コード不変) は**緑でなければならない** — 本件は docstring だけの変更で、(1) の赤は意図しないコード変更を意味する。(2) の赤を消すための登録 (CH-ID) はしない: CH-ID は移した経緯の塊のためのもので、挙動を説明する新しい docstring の受け皿ではない。道具の側 (既存の対象に docstring を足すと赤) は R-22 の問い 3 を別のチャットが実施中なので本件では触らず、台帳の R-89 の行に材料として追記する。
- **D-4 (変更クラス)。** `tools/change_class.py` の下限は B。`RM` §9 の 8 の「`_ISOMORPHIC_TARGETS` に登録された helper の本体 = C」は当たらないと判定する: 同型性テストの `_normalize` は比較の前に先頭 docstring を落とす (`r2db-api/tests/test_audit_query.py` の `_strip_leading_docstring`) — 登録表が「本体」として比べる範囲に docstring は入っていない。(1) が緑であることが、実行される本体が 1 字も変わっていない証拠になる。両 peer を同じ文で同時に変えるので片 peer だけの変更でもない。レビュー担当はクラスを上げられる。
- **却下した代替案**: (a) docstring を足さず台帳を「道具が赤にするので不可」で閉じる — 道具の照合は人が読むもので強制ではなく、読み手が誤解しやすい 3 点が関数に書かれないまま残る。(b) `tools/check_comment_provenance.py` を直して赤を消してから足す — 別のチャットが同じ道具の領域 (R-22 問い 3) を実施中で、衝突する。R-89 に合流させる。(c) `_f17_message` にも足す — 同じ module の 8 本の形から 1 本だけ外れる。

## 2. WP-1 — docstring を置く

### 2.1 触ってよいパス

- `r2db-api/src/r2db_api/platform_declarations.py` と `MitateDB-api/src/mitatedb_api/platform_declarations.py` の `check_auditreader_statement_timeout` の `def` 行の直後だけ

### 2.2 完了条件

1. 両 peer の関数の先頭に、確定文 `$SP/r67-final/docstring.txt` が逐語で在る (字下げ込み。言い換えない、折り返しを変えない)。両 peer の docstring は同一。
2. 差分は 2 ファイル、追加行だけ (削除 0 行)。
3. `tools/check_comment_provenance.py --base b3dd0c3 <2 ファイル>` の出力が `§4.1 (2)` の 2 行だけ (`('check_auditreader_statement_timeout', 'stmt#0')`、`old 0, new 1`)。`§4.1 (1)`・`(5)` の行が無い。`--register` は終了コード 0。
4. `tools/dev/pt.py` で `r2db-api/tests/test_ops_verify_declarations.py`・`r2db-api/tests/test_audit_query.py`・`MitateDB-api/tests/test_ops_verify_declarations.py`・`MitateDB-api/tests/test_audit_query.py` が緑 (F-17 のテストと同型性テスト。件数 pin 143 は変わらない)。両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` も回す (`platform_declarations.py` を行番号で固定する allowlist が在れば、28 行ぶんの行送りで赤になる。赤なら直さず報告する — 裁定は監督)。
5. `tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。
6. docstring の各主張が現物と一致する (レビューが照合する): 読み手の特定 (両表の `SELECT`、owner を除く)、該当 role 無しは通る、fail の 2 条件と報告の順、`_role_setting_rows` が見る行の範囲、呼び出し元が `ops verify-declarations` だけであること。

### 2.3 完了条件 → 変異

docstring は実行されないので、壊して赤になるテストは無い。全行が監査照合である。主張を固定している既存のテスト (レビューが主張と突き合わせる先): 両 peer の `tests/test_ops_verify_declarations.py` の `test_verify_declarations_f17_fails_when_declared_timeout_is_zero`、`…_is_reset`、`…_when_a_per_database_override_exists`、`test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant`、`test_verify_declarations_f17_passes_when_auditreader_role_is_absent`。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 | 監査照合 (確定文ファイルと、各 peer の関数の docstring の `diff` が空であることを逐語で記録する) | — |
| 2・3・4・5 | 監査照合 (実行したコマンドと出力行を報告に逐語で残す) | — |
| 6 | 監査照合 (コードレビューが主張ごとに file:line を挙げる) | — |

### 2.4 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r67 -- r2db-api/tests/test_ops_verify_declarations.py r2db-api/tests/test_audit_query.py r2db-api/tests/test_l1_details_vocabulary_ast_scan.py -q`、同じ 3 ファイルを `MitateDB-api/tests/` で (peer ごとに 1 回ずつ、前景・同期、Bash timeout 600000)
- python は main checkout の `.venv/bin/python`。道具は worktree を cwd にして実行し、終了コードは pipe の外で取る。

## 3. レビューと受け入れ

コードレビュー 1 回 (別に起動した `reviewer`)。受け入れは監督がゲートの集計行と本書の表を照合して行う (Class B。機械判定の証拠が少ないので受け入れ監査は入れない)。

## 4. 記録 (統合時に監督が埋める)

### 4.1 訂正註と監督裁定 2026-09-22 (§1〜§3 の本文は書き換えない)

- **確定文を 1 回改めた** (コードレビュー 1 の中 1・中 2)。1 文目の「without a bounded statement」は条件 2 (per-database の行は値を見ずキーの有無で赤) と合わないので「fails either condition below」に、条件 2 に `whatever its value` を足した。末尾の「pooled connection … until the process that holds it restarts」は、監査 reader が呼び出しごとに接続を開く MitateDB-api (`MitateDB-api/src/mitatedb_api/audit_query.py` の `PostgresAuditQueryStore.query`) で成り立たないので、両 peer で成り立つ形に改めた。docstring は 24 行から 26 行になった。
- **触ってよいパスを広げた** (同 高 1)。本件で偽になる注記 — 両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` の F-17 の行の上の「`check_auditreader_statement_timeout` carries no docstring and no peer-specific literal」— を、今の理由 (先頭 docstring は比較の前に落ちる) に直した。両 peer 同一。`tools/check_comment_provenance.py` は `src/` だけを走査するので、この注記は照合の対象外である。
- 低 3 件 (「negative」は `ALTER ROLE` の範囲検査で通常は到達しない / 「FIRST role」「not parseable」を直接固定するテストが無い / `information_schema.role_table_grants` の可視範囲) は現状維持 (レビューの評価どおり。docstring はコードの記述として正しい)。
- `pt.py -C .claude/worktrees/r67` は worktree を cwd にすると二重パスになる。`-C .` の読み替えを可とした。

### 4.2 実施と受け入れ

- 差分: `src` 2 ファイル各 `26 0`、`tests` 2 ファイル各 `3 2`。確定文と両 peer の docstring・注記の `diff` は空 (実装担当と監督がそれぞれ確認)。
- `tools/check_comment_provenance.py --base b3dd0c3 <src 2 ファイル>`: `FAIL (§4.1 (2)) … ('check_auditreader_statement_timeout', 'stmt#0') … (old 0, new 1)` が peer ごとに 1 行、計 2 行だけ (監督が再実行)。`--register` は `comment provenance register OK: 87 files scanned, 430 CH-IDs`。`check_doc_refs` 0 dangling、`public_value_scan` `total_flagged=0`。
- 対象テスト: r2db-api `pt: 122 passed`、MitateDB-api `pt: 113 passed` (F-17・同型性・L1 details の走査。件数 pin 143 は不変)。
- コードレビュー 1 回 (高 1 / 中 2 / 低 3、クラス引き上げなし。docstring 11 文を両 peer の本体と照合)。
- 完了ゲート (監督が単独実行): `3844 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0 (テストの増減なし)
- **最終判定: 受け入れる。**

