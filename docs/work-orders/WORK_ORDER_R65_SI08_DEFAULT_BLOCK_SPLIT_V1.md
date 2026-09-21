# 作業指示書 — R-65 `security/CONTROL_MAPPING.md` の SI-08 の既定の小ブロックを名前付き小ブロックへ分ける

## 0. 版数・位置づけ

- **v1.0 (2026-09-21)。** 基点 main `a6a224f`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-65。変更クラスは **Class D** (`security/` を触る。契約は触らない。R-59 の作業指示書の訂正註 2026-09-20 と同じ判定)。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 **2.16** が当たる。
- 設計は新しく起こさない。方法は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v1.0 (§5 の見出しの書式、§6 の照合、§7 の訂正註) がそのまま定めており、本件はその 4 回目の適用である。先例は `docs/work-orders/WORK_ORDER_R59_SI09_MITATEDB_BLOCK_SPLIT_V1.md`。適用の計画のレビューは §1.6 のコードレビューが兼ねる。**R-59 と違い受け入れ監査を入れる** (§2)。
- **R-70 とは変更セットを分ける** (監督裁定 2026-09-21)。R-70 は文の訂正で `missing` / `added` が 0 にならず、純粋な移動の機械照合 (完了条件 1) と同じ変更セットに入れると照合が効かなくなる。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. WP-1 — Phase 10 の (a)〜(e) の主張を名前付き小ブロックへ移す (両 peer)

**目的**: SI-08 / r2db-api の既定の小ブロックは 14,105 字 (上限 15,200 まで残り 1,095、文書の最長)、SI-08 / MitateDB-api の既定は 13,023 字 (残り 2,177。いずれも台帳の記録値で、着手時に測り直す)。主張の文を 1 字も変えずに、主題の塊を名前付き小ブロックへ移して余地を作る。

### 1.1 枠 (監督確定)

- 名前付き小ブロックは peer ごとに 1 本、同じ主題名で: `### r2db-api -- capacity and concurrency` と `### MitateDB-api -- capacity and concurrency`。MitateDB-api は `ops inventory` の後ろに置く (名前付きは 2 本になる。上限 3)。
- 移す候補は、各 peer の Control の `**Phase 10 (WP-4/WP-6/WP-8, 2026-09-10) …` の bullet から (e) の最後の bullet までの連続した塊 — (a) `process_ceilings`、(b) DB 側の件数の上限、(c) 接続容量と role の `CONNECTION LIMIT` / F-16、(d) 認証前の `concurrency` slot、(e) threadpool。基点の行で r2db-api は `:587`-`:596` (10 行・約 6,400 字)、MitateDB-api は `:626`-`:639` (**`:632` の `**F-17 runs on this peer too (R-56)**` は主題が違う (reader の statement bound) ので候補から外す**。13 行・約 7,500 字)。MitateDB-api の `:633`-`:634` (`0014_role_connection_limits_rollout.sql`) は (c) の続きとして候補に入れる。
- 候補の Evidence / Status に対応する bullet が無ければ、名前付き小ブロックの当該軸は `- —` とする (先例の形)。在れば同じ軸へ移す。
- 帰属の判断は bullet ごとに行い、主題に収まるか迷う bullet は**移さず**報告に挙げる (裁定は監督)。1 つの bullet が 2 つの主題を語る場合は分けない (文を変えない)。
- 指示語の検査は**両側**で行う: 移した側と残った側の両方について、`above` / `below` / `the same` / 裸の `` `::name` `` / `this file` / `this peer` / `own entry` / `own SI-08 row` の類が指す先が、分割の後も辿れること。peer を跨ぐ指し方 (`r2db-api's own entry` 等) は、指す先の bullet が**相手 peer のどの小ブロックに在るか**まで見る。辿れなくなる・一意でなくなる行が在れば、移す範囲を変えて解消できるかを先に試し、文の訂正が要るなら実装せず報告する (裁定は監督)。`:632` を残すことで `:631` / `:633` との間の指示語が切れないかを必ず見る。
- 他 SI・他文書から SI-08 のこの塊を指す現在形の箇所 (`security/CONTROL_MAPPING.md` の中の `SI-08` を指す文、runbook、README、現行の設計文書) を grep し、`SI-08 / <peer> / <軸>` の形で現在形に指しているものだけ `SI-08 / <peer> / capacity and concurrency / <軸>` に合わせる。`security/CONTROL_MAPPING.md` の中の他の主張行を直す必要が出たら**実装せず報告する** (文の訂正になる)。記録文書には、R-59 の先例どおり日付つきの訂正註の**追記**が要る箇所を報告に挙げる (追記は監督が行う)。
- **preamble**: 版数行を 2.15 → 2.16 に先例の書き方で足す。`Length cap measurement` の段 (`:26` 以下) の `SI-14's r2db-api block, now 15,122 …` と `78 left today` は時点つきの古い実測なので、**分割後の実測 (文書の最長ブロックとその字数、残り) に in place で直し、旧文は同じ段の中に日付つきの訂正註として逐語で残す** (R-60 の申し送り。`security/CONTROL_MAPPING_HISTORY.md` は SI の見出ししか持たないので移せない)。確定文は実測の後に監督が確定するので、実装担当は**実測値と旧文の逐語を報告し、preamble の段の文案は監督の確定文ファイル `$SP/r65-preamble-final.txt` を待って逐語複製する** (`OPERATING_CONDITIONS.md` §1.5 の 35)。版数行は先に入れてよい。

### 1.2 触ってよいパス

- `security/CONTROL_MAPPING.md`
- §1.1 で現在形の所在を直す必要が出た文書 (報告に列挙)。無ければ 0。
- それ以外 (テスト・道具・`security/CONTROL_MAPPING_HISTORY.md`) は触らない。既存の検査が新しい小ブロックで赤になったら直さず報告する。

### 1.3 完了条件

1. 分割の前後で (SI, peer, 軸, 本文) の多重集合が一致する: `tools/check_control_mapping_split.py --base a6a224f --expect "<期待行>"` が終了コード 0。期待行は `missing=0 added=0 moved=<移した bullet 数> empty_axis_added=<足した - — の数> empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`。preamble の差分は版数行と `Length cap measurement` の段だけ。
2. `conformance-tests/test_control_mapping_register.py` が緑。
3. 分割後の 4 つの小ブロック (両 peer の既定と `capacity and concurrency`) と、文書の最長ブロックを、登録テストの `_subblock_block_text` で測って報告する。**両 peer とも既定の小ブロックの残りが 5,000 字以上、名前付きの残りも 5,000 字以上**であること (足りなければ移す範囲を監督に上げる)。
4. 指示語の検査 (§1.1) の結果を、peer ごと・移した側と残った側それぞれ「確認した指示語 → 指す先 → 辿れるか」の表で報告する。辿れなくなった行が 0。
5. `tools/check_doc_refs.py` が 0 dangling、`tools/public_value_scan.py` が 0 flagged。
6. preamble の `Length cap measurement` の段が監督の確定文と byte 一致し、その中の実測値が完了条件 3 の実測と一致する。
7. 下の対応表に対応の無い行が無い。

### 1.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 移した bullet の 1 つを別の peer の同名の小ブロックへ置く → `check_control_mapping_split.py` が非 0 (scratchpad の複製の上で `--new` を使って 1 回行う。作業ツリーを変異させない) |
| 2 | M2: 名前付き小ブロックの見出しを `### r2db-api -- capacity  and concurrency` (空白 2 つ) にする → register テストが赤 (`tools/dev/mutate.py`) |
| 3・4・5・6 | 監査照合 (報告の表、道具の出力行、確定文ファイルとの `cmp`) |
| 7 | 監査照合 (本表) |

### 1.5 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- tools/tests -q -k control_mapping` (conformance と 1 回に結合しない)
- `./.venv/bin/python tools/check_control_mapping_split.py --base a6a224f` (worktree の中で。インタプリタは main checkout の `.venv`)
- `tools/dev/mutate.py "$SP/r65-mutations.json" -C .claude/worktrees/<担当 worktree>`

### 1.6 レビュー

コードレビュー 1 回 (別起動)。観点: 帰属の判断 (特に `:632` を残す判断と `:633`-`:634` を移す判断)、両側・両 peer の指示語、字数の独立再測、preamble の確定文と実測の一致、他文書の所在。結果はファイルに書かせる。

### 1.6a 訂正註 2026-09-21 (コードレビューの 3 件、監督裁定)

- **指摘 1 (高) — 採る。同じ変更セットに畳む。** SI-09 / MitateDB-api / platform upgrade / Control の `0014_role_connection_limits_rollout.sql` の主張は、引き上げた ceiling の所在を `` `SI-08`'s `MitateDB-api` `default block` `` と名指していた (R-60 の成果)。その ceiling の主張は本 WP で `capacity and concurrency` へ移ったので、この行は移動の結果として偽になる。偽の指し先を持つ版を main に置かないため、別変更セットにせず、**移動が原因の指し先の訂正 1 件だけ**を Update convention で同じ版 2.16 に入れた (現行行を in place で直し、旧文を逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` へ)。R-70 (移動と無関係な文の訂正) を分ける §0 の裁定は変えない。これに伴い §1.2 の触ってよいパスに `security/CONTROL_MAPPING_HISTORY.md` を足し、完了条件 1 は **2 段**で読む: (A) 純粋な移動の段で `missing=0 added=0 moved=23 empty_axis_added=4 … ` が終了コード 0 (`$SP/split-final.txt`)、(B) 訂正を入れた最終の木で `missing=1 added=1 moved=23 empty_axis_added=4 …` が終了コード 0 (`$SP/split-final2.txt`)。(B) の 1 件が当該行であることは差分で照合する。
- **指摘 2 (中) — 直さない。** MitateDB-api 既定の F-17 の主張の `r2db-api's own SI-08 row` は、`row` = (SI, peer) の subsection の水準の指し方で、subsection は分割の後も 1 つである。指す内容 (F-17) は r2db-api の既定の小ブロックに残っており辿れる。R-60 が直したのは `block` の語で複数ブロックの 1 つを指す文であり、同型ではない。
- **指摘 3 (中) — 採る。** preamble の `Blocks per subsection` の段に版 2.16 の再実測文を足した (先例は版 2.8〜2.15 の各文)。§1.1 の枠がこの段を挙げていなかったのは監督の枠の漏れである。
- preamble の 2 つの段と SI-09 の 1 行・履歴の 1 件・版数行の追記は、確定文を監督がスクリプトで差し替えた (実装担当の再開はしていない)。

### 1.7 記録 (統合時に監督が埋める)

- 実施 2026-09-21。移した bullet は Control 23 (r2db-api 10 = 基点 `:587`-`:596`、MitateDB-api 13 = 基点 `:626`-`:631`・`:633`-`:639`)。Evidence / Status に対応する主張は無く、名前付き小ブロックの両軸は `- —` (4 本)。
- `tools/check_control_mapping_split.py --base a6a224f --expect …`: (A) 純粋な移動の段 `missing=0 added=0 moved=23 empty_axis_added=4 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` 終了コード 0、(B) 最終の木 `missing=1 added=1 moved=23 …` 終了コード 0。受け入れ監査が (B) の 1 件は SI-09 の当該行だけであること、履歴へ移した旧文が基点の行と byte 一致すること、当該 1 行だけ戻した複製で (A) が再現することを確かめた。register テスト `34 passed`、`tools/tests -k control_mapping` は `58 passed, 510 deselected` (別呼び出し)。`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged。
- 字数 (登録テストの `_subblock_block_text`。実装・レビュー・監査・監督の 4 者の再測が一致): r2db-api 既定 7,682 (残り 7,518) / `capacity and concurrency` 6,422 (残り 8,778)、MitateDB-api 既定 5,555 (残り 9,645) / `ops inventory` 8,335 / `capacity and concurrency` 7,467 (残り 7,733)。分割前は 14,105 / 13,023。文書の最長は SI-14 / r2db-api の既定 12,624 (残り 2,576)。
- 完了条件 → 変異 → 結果: 1 ← M1 (複製の上で r2db-api の Phase 10 の導入文を MitateDB-api の同名の小ブロックへ置く) → 道具が終了コード 1、`missing=1 added=1 moved=22`。作業ツリーは変異させていない (手実行で、逐語ログは実装報告の本文だけ — 監査の留保) / 2 ← M2 (見出しの空白 2 つ) → `expect=red got=red`、赤は `test_control_mapping_md_subblock_headings_use_the_allowlisted_form`、復元は sha256 2 回で照合 / 3・4・5・6 ← 監査照合 / 7 ← 本表。
- コードレビュー 1 回: 高 1・中 2。裁定は §1.6a。クラスの引き上げ無し。
- 受け入れ監査 1 回: 未充足 0。留保への監督裁定 — (1) `Blocks per subsection` の段の追記は確定文ファイルを経ず監督がスクリプトで入れた (数値 6 値は監査の再測と一致。§1.5 の 35 の形からの逸脱として記録する)。(2) 記録文書への訂正註は**足さない**: 移した主張の所在を `SI-08 / <peer> / <軸>` の形で現在形に指す文書は 0 件で、記録文書に在るのは日付つきの行番号だけである (R-59 で註を足したのは所在を軸つきで述べる文だった)。(3) MitateDB-api 既定の Status の `Deployment caveat` は `audit_requests_per_minute` の in-process counter を述べる行で、既定に残る同じ主題の Control と組なので移さない。(4) §1.2 の本文と §1.6a の食い違いは、訂正註が本文に優先する (`OPERATING_CONDITIONS.md` §1.8 の 57)。
- 完了ゲート (監督が単独実行、最終の木): `gate: 3796 passed, 2 subtests passed in 323.15s (0:05:23)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。**受け入れる。**

## 2. 受け入れ

Class D なので、コードレビューの後に、別に起動した受け入れ監査を 1 回入れる。監督が完了ゲート (`tools/dev/gate.py -C .claude/worktrees/<担当 worktree>`) の集計行・§1.3・監査のパケットを照合して判定する。
