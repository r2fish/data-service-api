# 引き継ぎ書 — 2026-10-04 R-82 の閉止 (スキーマ情報のプロセス内キャッシュ)

本書は作業機の監督チャット (Fable) の記録である。依頼は「台帳 R-82 の『運用開始後』の印を外し、着手する。枠決めから実施・レビュー・受け入れ・commit まで一気通貫で行う」(依頼者 2026-10-04。印を外す根拠は依頼者指示 (逐語): 「R-82をチップで出してください」)。

## 1. 現在地 (2026-10-04、本書の commit の時点の記録)

- 基点は local main `b378989`。本変更はその上の 1 commit と merge commit である。GitHub へは送信していない (`OPERATING_CONDITIONS.md` §2 の 20)。
- 台帳は v1.171 (R-82 の閉止、R-80 行の追記)。`tools/dev/ledger.py --open` は open=16。
- `security/CONTROL_MAPPING.md` は 3.22。契約と `conformance-tests/CONDITIONS.md` は変えていない。`conformance-tests/COLLECTION_FLOOR` は 5232 → 5248。
- 完了ゲート (監督、main `b378989` + 本変更の作業ツリー): `gate: 5248 passed, 2 subtests passed in 556.94s (0:09:16)`、judge=PASS、label r82、pg_database/pg_roles diff 0。

## 2. 本チャットで閉じたもの

- **R-82**。作業指示書 `docs/work-orders/WORK_ORDER_R82_SCHEMA_CACHE_V1.md` (着手時の突き合わせ §1、実測 §2・§6、設計 §3、完了条件と変異 §4、訂正註 §7)。
- 両 peer の PostgreSQL 経路が catalog の読みをプロセス内の写しから返す。鍵は要求の transaction で 1 文で読む (database の oid, schema revision)。token を先に読み、data 操作は entity lock の後に読む。schema 操作・dry run・MitateDB の schema scope は写しを使わない。
- 文/要求 (K=1): r2db runtime 6 → 5 / 8 → 6 / 12 → 10、MitateDB developer 10 → 3 / 6 → 3 / 22 → 3 / 10 → 3。時間 (K=1、負荷の低い状態、http plug の p50): 1 組目 −13.4% 〜 −46.5%。数字は作業指示書 §6。
- R-80 行に、着手条件「R-82 を先にするかの依頼者裁定」が同じ指示で決着した旨を追記した。R-80 には着手していない。

## 3. 次の一手

- 依頼者の事後確認 (§4)。確認の後、台帳の記録ファイルの R-82 の節と本書に 1 行ずつ追記する。
- 本チャットの worktree と branch を `tools/dev/fold.py` で畳む。
- R-80 (pipeline 化、`SET LOCAL` の 1 文化) は印「運用開始後」が残る。着手するなら、R-82 の後に残る独立区間 (`BEGIN` + `SET LOCAL` ×2 + token の読み 1 文、savepoint 系) を対象に、`--roundtrip` を取り直すところから始める。

## 4. 依頼者判断待ち・未決

事後確認を求める監督裁定 (依頼者の方針 2026-10-03「裁定事項は監督の推奨で進めて記録し、事後に確認を取る」による):

1. 実測の結果、実装する (「不要として閉じる」を採らない)。
2. 鍵は (database oid, schema revision)。token が違う `put` は常に入れ替える (revision の大小で捨てない)。
3. schema 操作・dry run・MitateDB の schema scope はキャッシュを使わない。
4. reserved 名の判定は DB を読まないので対象外。
5. 稼働中の同じ DB への書き戻しは token で見分けられない。書き戻しの手順を作るときにプロセスの再起動を条件にする (両 peer の runbook に手順が無い。起票しない)。
6. application ごとの upgrade script の規則 (revision を上げずに catalog の読みの結果を変えない) は静的テストと許可表で固定し、既存の script は変えない。
7. クラスは D (台帳行の見込みは B)。契約の版は上げない。
8. 時間の前後は、負荷の高い間の値を判定に使わず、完了ゲートの後に取り直した値で読む。
9. `tools/check_comment_provenance.py --base main` の赤 7 行は正当な赤とする (作業指示書 §6.4)。

手元で未検証:

- 実際の配備先 (Cloud SQL ほか) で runtime / developer role が `pg_database` を読めること (PostgreSQL の既定では読める。使い捨てクラスタでは確かめた)。
- CI (Linux、Python 3.12)。本変更は未送信である。
- `test_r120_entity_lock.py` の lock 順序のテストは trace の畳み方を変えた (token の読みを catalog と同じ印にした)。変更後に R-120 の変異 M3 は取り直していない。
- 載せ直しの前に取った `--roundtrip` の事後の値 (作業指示書 §6.1) は、載せ直しの後には取り直していない (載せ直しで変わったのは並行チャットのコメントの変更だけである)。

## 5. 運用上の教訓

- 並行チャットの完了ゲートが suite lock を持っている間、`tools/perf_baseline.py` は REFUSED (75) を返す。計測の script は、終了コードを見て待ち直す形にする (本チャットは 5 本を空振りした)。
- K=32 は `--warmup 3 --n 15` で取る (`--warmup 10 --n 100` は rate 上限で `LIMIT_EXCEEDED` になる)。
- load average が 20 を超える間の K=1 の時間は、同じ行の 2 組の差の符号が割れ、前後の判定に使えなかった。往復数 (`--roundtrip`) は負荷に依らない。
- 並行チャットが main を進めたときは、未 commit の変更を patch に保存し、`git merge --ff-only main` の後に `git apply --3way` で載せ直した。位置参照を持つ `security/CONTROL_MAPPING.md` は載せず、新しい main から作り直した (版は先に取られていた)。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 実装 疑義: 順序 guard は書き戻しで古い内容を残す | 直した | guard を外した (作業指示書 訂正註 1) |
| 実装 逸脱: 既存の動作テスト 6 本の変更 | 直した | 観測点の移動。レビュー担当が 1 件ずつ確かめ、1 本 (レビュー 1) を直した |
| レビュー 1: `query` が制約 registry を読まないことのテストが空振り | 直した | query の直前に空のキャッシュへ差し替え、変異 X1 が赤 |
| レビュー 2: 偽になった文 3 箇所 | 直した | 来歴の手順で訂正 (CH-0526・CH-0569・CH-0570) |
| レビュー 3: 来歴の道具の `--base` の赤 | 観察 | コードの変更と、削除・移動に伴う道具の既知の穴の形。利用者は気づかない |
| レビュー 4: 書き戻しを扱えるように読める docstring | 直した | 両 peer 同文で「書き戻しの後は再起動」を足した |
| レビュー 4 (不確実): 新しい cluster で oid が一致する場合 | 観察 | 別の cluster へ繋ぎ直すには DSN の変更 = 再起動が要る |
| レビュー 5: `_TableInfo` が frozen でない | 直した | `frozen=True` |
| レビュー 6: D-8 の静的テストで bump 文の観測が 0 件 | 直した | 実物の文に一致する assert を足した |
| レビュー 7: migration 0009 前の registry での例外の対応 | 観察 | 起動時の台帳照合が先に拒否する。利用者は到達しない |
| レビュー 8: R4 の変異が指示書の文面と違う | 観察 | 文面どおりの X2 も赤 (作業指示書 訂正註 5) |
| 監査 (a) 観察 1: application ごとの instance を固定する変異が無い | 観察 | 共有しても oid が鍵に在り正しさは保たれる。利用者は気づかない |
| 監査 (b): 指示書 §2 の「timeout 設定 1 文」 | 直した | 訂正註 3 |
| 監査 (c): 文ごとの計測の出力が無く、token の文が実装と違う | 直した | 取り直して出力を置いた (作業指示書 §6.3、訂正註 4) |
| 監査 (d): SI-11 r2db の lock 順序の主張が `_load_catalog` の名のまま | 観察 | その文の主語は `apply_schema` で、`apply_schema` は今も `_load_catalog` を呼ぶ |
| 監査: D-8 のテストは transaction の範囲を見ない | 観察 | script の文の有無だけを見る。新しい script のレビューが受け止める。利用者は気づかない |
| 監査: R-120 の lock 順序テストの変異を取り直していない | 観察 | §4 の未検証に記載 |
| 監査 観察 2: conformance の log の atexit `_sweep_prefix` の traceback | 観察 | 本変更は adapter に触れていない。止まった使い捨てクラスタへの後始末の接続で、集計行と残骸の判定に影響しない |
