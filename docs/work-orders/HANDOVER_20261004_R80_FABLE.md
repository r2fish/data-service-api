# 引き継ぎ書 — 2026-10-04 R-80 の修正の着手 (往復数の取り直しと候補の実測)

本書は作業機の監督チャット (Fable) の記録である。依頼は「台帳 R-80 の『運用開始後』の印を外し、修正に着手する。枠決めから実施・レビュー・受け入れ・commit まで一気通貫で行う」(依頼者 2026-10-04。印を外す根拠は依頼者指示 (逐語): 「R-80開始チップを出してください。」)。

## 1. 現在地 (2026-10-04、本書の commit の時点の記録)

- 基点は local main `6635064`。本変更はその上の 1 commit と merge commit で、文書だけである (`tools/change_class.py` は Class A)。GitHub へは送信していない (`OPERATING_CONDITIONS.md` §2 の 20)。
- 台帳は v1.173。R-80 は open のまま、規模 L、印なし、着手条件「設計レビュー」。`tools/dev/ledger.py --open` は open=16。
- コード・テスト・`security/CONTROL_MAPPING.md`・契約・`conformance-tests/COLLECTION_FLOOR` は変えていない。
- 完了ゲート (監督、main `6635064` + 本変更の作業ツリー): `gate: 5248 passed, 2 subtests passed in 686.80s (0:11:26)`、judge=PASS、label r80、pg_database/pg_roles diff 0。

## 2. 本チャットで行ったこと

- `tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1 --roundtrip` を main `6635064` で取り直した。文/要求は R-82 の閉止時の記録と一致した (r2db runtime 5 / 6 / 10、MitateDB runtime 3 / 4 / 8 / 5、developer 3 / 3 / 3 / 3)。
- 依存表を現物で作り直し、候補を使い捨てクラスタ (直結と遅延 proxy 経由) で測った。記録は `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` v0.3 §5 (出力は逐語)。
- 結果: (A) の pipeline は、psycopg が transaction を管理する形のままでは 6 往復が 5 往復になるだけで (B) と変わらず、直結では遅くなる。(B) は要求の p50 の 0.6%〜2.5%。レビュー担当が示した形 (autocommit の接続 + 文としての `BEGIN` / `COMMIT` + 要求ごとの pipeline) は 6 → 2 往復だが、直結では時間の差が無い。
- コードは変えていない。完了条件と変異の対応、性能の前後は無い。

## 3. 次の一手

- 依頼者の事後確認 (§4)。確認の後、台帳 R-80 行と本書に 1 行ずつ追記する。
- R-80 の設計 (新しいチャット、規模 L): 先に、往復の時間を変えて測る手段 (同メモ 5.3 の proxy を `tools/perf_baseline.py` に入れるか、配備先で測るか) と判定の閾値を決める。その後に、両 peer の transaction の境界を autocommit + 文としての `BEGIN` / `COMMIT` + pipeline に移す設計を書き、設計レビューに掛ける。守る性質は同メモ 5.5 の 3 の (b) の列挙 (SI-11、idempotency の savepoint、R-79、R-42、error code への対応、timeout が最初の data 文より前に効くこと、lock の後に token を読む順)。
- 本チャットの worktree と branch を `tools/dev/fold.py` で畳む。

## 4. 依頼者判断待ち・未決

事後確認を求める監督裁定 (依頼者の方針 2026-10-03「裁定事項は監督の推奨で進めて記録し、事後に確認を取る」による):

1. psycopg が transaction を管理する形のままの pipeline (候補 (A) の当初の形) は実装しない。
2. `SET LOCAL` 2 文の `set_config` 1 文化 (候補 (B)) は実装しない。
3. R-80 を「実測の結果、不要」として閉じず、open のまま規模を M から L に上げ、着手条件を設計レビューにする。残る候補は autocommit + 文としての `BEGIN` / `COMMIT` + 要求ごとの pipeline の形である。依頼者が「開発機で差が出ないので閉じる」と裁定するなら、台帳行を記録ファイルへ移すだけで済む。
4. 設計は、往復の時間を変えて測る手段と判定の閾値を先に決める (P-8)。
5. 規模 M の作業指示書は書かず、同メモ §5 を記録とする (実装が無い)。監査担当は起動していない (Class A)。

**【追記 2026-10-04】依頼者の事後確認 (逐語): 「確認事項は了承します」 — 上の 5 件の全件。台帳 v1.174 に記録した。**

手元で未検証:

- 実際の配備 (DB が別ホストの MitateDB-api) での往復 1 回の時間。遅延 proxy の値は開発機での模擬である。
- autocommit + pipeline の形の正しさは、`SET LOCAL` の効き方・`COMMIT` 後に残らないこと・書き込みの可視性・失敗後の `ROLLBACK` の 4 点だけを確かめた。savepoint、timeout による取り消し、prepared statement の保持、`PipelineAborted` の写し方は確かめていない。
- K=1 の時間の前後 (`--warmup 20 --n 200`) と K=32 は取っていない (コードを変えていない)。
- CI。本変更は未送信である。

## 5. 運用上の教訓

- psycopg 3.3.5 の pipeline は、暗黙の `BEGIN` の直後・`commit()`・pipeline の出口で sync する。「独立な文の連続は 1 往復になる」は、psycopg に transaction を管理させる形では成り立たない。往復数は机上で数えず、遅延 proxy で測る (transaction の時間 ÷ 1 文の往復の時間)。
- 遅延 proxy は塊ごとに「届いた時刻 + D」で送る形にする。塊を順に sleep して送る形は、pipeline の burst を不当に遅くする。
- 開発機の load average は別プロジェクトの処理で数分のうちに 5 から 70 に上がった。計測の出力に load average を入れ、高い run は捨てる。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1: 「要求ごとの pipeline は 1 往復しか減らない」は psycopg の性質ではなく、autocommit + 文としての `BEGIN` / `COMMIT` の形は 6 → 2 往復 | 直した | メモ 5.3 の (3)・5.4 の (iii) に実測を足し、5.5 を書き直した。R-80 を閉じる裁定を取り下げ、open のまま規模 L にした |
| レビュー 2: query の形の測定を data 操作に一般化している。独立区間から token が落ちている | 直した | 5.2 の末尾と 5.4 の (i) を直し、data 操作の形の値を足した |
| レビュー 3: `SET LOCAL` を名指す r2db-api 節の行は 3 | 直した | 5.5 の 2 |
| レビュー 4: 出力の末尾 2 行の欠落、v0.2 の所在、§4 と F4 を置き換える旨 | 直した | 5.3 の (1)、§5 の冒頭 |
| レビュー 観察: MitateDB の `_retime` と pool の ping は本計測の経路に出ない往復 | 観察 | 設計のときに分母に数える。利用者は気づかない |
