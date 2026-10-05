# 引き継ぎ書 — 2026-10-06 R-123 r2db `pg_text_format` の実 PG との不一致 (閉止)

本書は作業機の監督チャット (Fable) の記録である。対象は台帳 R-123 (R-39 の棚卸しで起票、規模 S)。着手は依頼者指示 2026-10-06 (逐語:「台帳 R-123 … に着手してください」。棚卸しから実装・レビュー・受け入れまで本チャットで一気通貫)。変更セット `r123` (Class B、規模 S。`tools/change_class.py` の下限 B) の 1 つで閉止した。内容の記録は台帳の閉止記録 `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の `## R-123` 節の【追記 2026-10-06 (v1.183)】にある。

## 1. 現在地 (2026-10-06、本書の commit の時点の記録)

- local main `7e48c23` (変更セット r123 の merge。変更セット本体の commit は `2a87d17`)。本書の変更はその上の 1 commit と merge commit である。origin/main は `092e1a1` のままで未送信 (送信は Mitate の監督が依頼者の指示で行う。`OPERATING_CONDITIONS.md` §2 の 20。このチャットから送らず、CI も起動しない)。
- 契約 `spec/data-service-api.v1.json` は 1.16.0 (不変)。
- `security/CONTROL_MAPPING.md` は 3.26 (不変。`pg_text_format.py` / `inmemory_predicate.py` への位置参照は無く、版上げなし)。
- 台帳は v1.183 (R-123 閉止)。`tools/dev/ledger.py --open` は open=16 (印なし 10、印あり 6。未着手 9、進行中 7。`7e48c23` の木で計測)。
- `conformance-tests/COLLECTION_FLOOR` は 5276 → 5280 (新テスト 4 本)。
- 完了ゲート (監督): `gate: 5280 passed, 2 subtests passed in 473.50s (0:07:53)`、judge=PASS、label r123、pg_database/pg_roles diff 0、log `gate 20261006-064721`。tools/tests は finalize の `--tools-tests` で 814 passed。

## 2. 本チャットで閉じたもの

| 変更セット | commit (merge) | 内容 |
|---|---|---|
| r123 (Class B、規模 S) | `2a87d17` (`7e48c23`) | in-memory の text 形を実 PG に合わせた 4 点 (台帳の 2 点 + 棚卸しで出た ≥ 1e16 の境界値 + レビューで出た typed number 列の int)。完了条件 C-1〜C-4 と変異 M-1〜M-4 + M-3b、赤→緑の集計行、実 PG との corpus 12268 値の不一致 0、docstring 3 本の CH-1130〜CH-1132 登録 + §9.3 訂正記録、性能 0.4〜0.5 µs/値。詳細は台帳の閉止記録 `## R-123` 節 |

却下した代替案 (枠の転記):

- repr の桁列を使い [1e15, 1e16) だけ指数形に組み替える — ≥ 1e16 の 6.7% が不一致のまま残る。
- コードだけ直して docstring を残す — docstring が事実と食い違う。
- docstring を登録せずに直す — 来歴検査器の `--base` が §4.1 (2) で赤。正規経路は登録 + 訂正記録。
- 契約に number 列の text 形を定める — Class C になり、MitateDB に対応物が無い (Z-1)。
- 第 3・第 4 の不一致を別起票する — 先送り (Z-2)。

## 3. 次の一手

- 依頼者の事後確認 (§4 の表)。
- 次の項目は `tools/dev/ledger.py --open` の順 (印なし先) で選ぶ。台帳 R-124 (order_by 項目の details.field path の peer 差、規模 S) が R-39 起票の残り。
- worktree `r123` は監督が畳む。

## 4. 依頼者判断待ち・未決

### 4.1 監督裁定 (事後確認待ち)

推奨で進め、事後確認を取る (依頼者方針 2026-10-03)。Z-1〜Z-6 は台帳の閉止記録の監督裁定 (a)〜(f) と同じ順・同じ内容である。最終節「裁定」(指摘ごとの処置) とは別。

| # | 裁定 | 理由 | 事後確認 |
|---|---|---|---|
| Z-1 | 契約は number 列の text 形を定めない | text 形は PostgreSQL の float8out / jsonb の形で、r2db in-memory plug が PG に追随する実装責務。契約文を足すと Class C になり MitateDB に対応物が無い | 待ち |
| Z-2 | 第 3 の不一致 (≥ 1e16 の区間境界値。PG の Ryu は両端を除外) と第 4 (typed number 列の int) を同じ変更セットで直し、規模 S のまま | 同じ関数の同じ性質。別起票は先送り | 待ち |
| Z-3 | docstring 3 本を CH-1130〜CH-1132 で登録し訂正記録を付ける | コードだけ直して文を残さない | 待ち |
| Z-4 | `tools/tests/test_leaf_import_direction.py` の allowlist に stdlib `math` を足す枠外変更を受理 | stdlib で leaf 性を崩さない | 待ち |
| Z-5 | Class B の S では必須でないレビュー担当を 1 起動 + 再確認 1 起動 | 製品コードの数値変換を変えるため | 待ち |
| Z-6 | inf / nan は `_float8out_text` で repr のまま (PG は `Infinity` / `NaN`) とし、観察に留める | JSON 入力では生じない | 待ち |
| Z-7 | 性能の差し戻しを監督が要求し (差し戻し 1: 全値探索 60 µs/値 → repr 先行。差し戻し 2: \|x\| < 2**53 の近道)、最終 0.4〜0.5 µs/値 (旧 0.14〜0.2 µs) を受理 | 行ごとに呼ばれる leaf。依頼者方針 (高性能が大前提) | 待ち |

### 4.2 未決

- なし (台帳 R-123 の問い「契約が number 列の text 形を定めるか」は Z-1)。

## 5. 運用上の教訓

- 来歴検査器の `--base` は完了ゲート・finalize・CI のどれも呼ばない、コメント整理の変更セット用の道具である。コードを直す変更セットでは §4.1 (1) が必ず赤になる。CH-ID の無い docstring の文を直す正規経路は新規登録 + §9.3 訂正記録 (R-123 で 3 塊、約 30 行/塊)。
- 棚卸しの reader に、実 PG で境界値だけでなく無作為の大量比較をさせると、台帳の外の不一致 (≥ 1e16 の 6.7%) が着手前に出る。
- 行ごとに呼ばれる leaf の性能は、実装報告に timeit を必ず要求する (差し戻し 1 の前は 60 µs/値で旧の約 400 倍だった)。
- 文書の log 名はハイフン形 (`gate-r123-20261006-…`) が公開値スキャンに project id として掛かる。`gate 20261006-064721` の空白区切りで書く。
- レビュー指摘 1 (int 経路) は、枠の C-1 が float しか入れていなかったために残った穴である。parity テストの入力は型の軸 (int / float) も列挙する。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1 (中): typed number 列の int が float8out を通らない | 直した | C-4、M-4 |
| レビュー 2 (低): `other` 候補は fast path の後では到達しない | 直した | 削除 |
| レビュー 3 (低): 性能が旧の 13〜15 倍 | 直した | 2**53 近道、0.4〜0.5 µs/値 |
| レビュー 4 (低): `_shortest_digits` docstring の「CLOSED interval」 | 直した | 偶数仮数は閉区間・奇数は開区間の文に |
| レビュー 観察 5: untyped 列の -0.0 の読み戻しが in-memory で -0.0 のまま | 観察 | in-memory は test double で DB の利用者は気づかず、§0.1 の終了条件を破らない。predicate の text 形の外 |
| 再確認 新指摘 1 (低): `_shortest_digits` docstring の 2**53 の根拠文の厳密さ (2 の冪の下端は 2**(m-54)、非正規数は 2**-1075) | 直した | 監督が直接。CH-ID 無しの新規塊 |
| 実装 観察: `_float8out_text` docstring 第 1 文の `` (`structured.py`) `` は指す先が不正確だが保護参照 | 観察 | R-22 の次の変更セットの候補だが台帳 R-22 行には足さない。再起票は自由 |
| 実装 観察: PG の別 major での tie 扱いは未確認 | 観察 | 本機は 16.14 のみ。別 major で corpus テストが赤になれば検出される |
| 実装 観察: float に丸まる int (2**53 超) の読み戻しが in-memory は int・PG は float | 観察 | test double |
| 実装 観察: `float(10**400)` の OverflowError | 観察 | `value_types.py` の入力検証が number 列の範囲外を VALIDATION_FAILED で止める。到達しない |
| 実装 観察: inf / nan は repr のまま | 観察 | Z-6 |
