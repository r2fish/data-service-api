# 作業指示書 — R-58 `tools/perf_baseline.py` が process の環境変数を戻さない

## 0. 版数・位置づけ

- **v1.0 (2026-09-20)。** 基点 main `2172fb0`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-58。変更クラスは **Class B** (`tools/change_class.py` 実測。契約・不変条件に触れない)。設計文書は持たない (本書 §1 が枠)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 枠 (監督確定)

### 1.1 起票文の訂正 (実測 2026-09-20)

台帳の起票文と `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` §8 (訂正註 1) は、原因を「`tools/testpg/dsa_testpg.py` が `PGPASSWORD` を消すため」とした。**これは不正確であった。** 二分法と、session 終了時の環境を書き出す probe の実測では、原因は次のとおりである。

- `tools/perf_baseline.py` の `main()` は、自分のクラスタを起動した後に `os.environ.update(c.env())` と `os.environ.pop("PGPASSWORD", None)` で process の環境を直接書き換え、**戻さない**。
- `tools/tests/test_perf_baseline.py::test_perf_baseline_takes_the_exclusive_lock_and_uses_its_own_cluster` は偽のクラスタ (`PGHOST` と `PGPASSFILE` が実在しないパス) で `main()` を同じ process の中で呼ぶ。monkeypatch を通らない代入なので、以後その process の `PGHOST`・`PGPASSFILE` は偽の値のままになる。
- conformance の session 終了時の adapter の `close()` は、実行中に作った database・role を掃くために admin DSN で新しい接続を開く (例: `r2db-api/conformance/conformance_adapter_r2db_http.py` の `close()` → `_cleanup()` → `_sweep_prefix()`)。DSN は password を持たず `PGPASSFILE` に頼るので、`fe_sendauth: no password supplied` で落ちる。
- 最小の再現: `conformance-tests/test_control_mapping_register.py` と上のテスト 1 件を 1 回の pytest に結合する。`tools/tests/test_perf_baseline.py` を抜くと出ない。
- 結合実行の後に owned クラスタの process と run dir は残らない (実測)。

### 1.2 決定

`main()` は、クラスタを使い終えた時点で `os.environ` を**呼び出し前の状態へ戻す** (成功・失敗・例外のどれでも)。戻す対象は `c.env()` が書いた名前と `PGPASSWORD` で、呼び出し前に無かった名前は消し、在った名前は元の値へ戻す。止めたクラスタを指す環境を process に残す理由は無い。CLI としての動作 (`_run()` の間は自分のクラスタの環境で動く) は変えない。

却下: テスト側だけで monkeypatch する — `main()` を同じ process から呼ぶ次の呼び手が同じ穴に落ちる。

## 2. WP-1

### 2.1 触ってよいパス

- `tools/perf_baseline.py` (`main()` のみ)
- `tools/tests/test_perf_baseline.py`
- `docs/code-history/` の companion — `tools/check_comment_provenance.py --base 2172fb0 tools/perf_baseline.py` が求めた場合だけ、`docs/code-history/README.md` の形で。
- 件数を固定する既存の静的テストがこの変更で赤になる場合だけ、その pin (実測して報告に書く)。

### 2.2 完了条件

1. `main()` が正常に終わった後、`os.environ` の `PGHOST`・`PGPORT`・`PGUSER`・`PGPASSFILE`・`PGPASSWORD` と `c.env()` が書く全ての名前が、呼び出し前と同じである (無かった名前は無い、在った名前は同じ値)。テストは呼び出し前に `PGPASSWORD` と `PGPASSFILE` を monkeypatch で番兵の値に置き、観測対象が 1 件以上あることを assert する。
2. `_run()` が例外を上げた場合と `TestPgError` の場合も 1 と同じ。
3. `_run()` の間は自分のクラスタの環境で動く (既存のテストの `seen_env` の assert を保つ。既存の docstring の変異 2 が今も赤になる)。
4. §1.1 の最小の再現 (`tools/dev/pt.py -C <worktree> -- conformance-tests/test_control_mapping_register.py tools/tests -q`) が error 0 で終わる。
5. `tools/check_comment_provenance.py --base 2172fb0 tools/perf_baseline.py` が 0 で終わる。
6. 下の対応表に対応の無い行が無い。

### 2.3 完了条件 → 変異 (expect=red)

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 復元を外す → 赤 / M1b: `PGPASSWORD` だけ復元から外す → 赤 |
| 2 | M2: 復元を `finally` から正常系の後ろへ移す → 例外のテストが赤 |
| 3 | M3: `os.environ.update(c.env())` を外す → 既存テストが赤 |
| 4 | 監査照合 (M1 を入れた状態で結合実行が `1 error` に戻ることを 1 回実測し、集計行を報告する。`mutate.py` の 1 entry として `conformance-tests/test_control_mapping_register.py tools/tests/test_perf_baseline.py` を対象にしてよい) |
| 5・6 | 監査照合 |

`mutate.py` は最初の失敗で止まるので、変異 1 件につきテスト 1 件を指す。

### 2.4 道具の引数 (main checkout を cwd にし、`SP` を export する)

- `tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- tools/tests -q`
- `tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- conformance-tests/test_control_mapping_register.py tools/tests -q`
- `tools/dev/mutate.py "$SP/r58-mutations.json" -C .claude/worktrees/inspiring-dewdney-461b95`

## 3. 記録 (統合時に監督が埋める)

- **実施 2026-09-20。** 変更は `tools/perf_baseline.py` (`main()` が書き換える前の環境を保存し `finally` で戻す)、`tools/tests/test_perf_baseline.py` (テスト 3 件)、`tools/tests/test_testpg.py` (WP-1b、テスト 1 件)。
- **訂正註 1 (完了条件 5)**: 「0 で終わる」は監督の書き誤りである。`tools/check_comment_provenance.py --base` の §4.1 (1) はコードを変える差分で必ず出る。**「(2)〜(5) が 0 件」と読み替える** (先例は R-52・R-56)。実測は `FAIL (§4.1 (1)) tools/perf_baseline.py:996 code changed` の 1 行だけ。§2.1 の `docs/code-history/` の companion の条項は `tools/` には当たらない (同書の対象は両 peer の `src/`) ので使っていない。
- **訂正註 2 (WP-1b、コードレビュー 1 回目の中 1 件への監督裁定)**: 同じ形の穴が `tools/tests/test_testpg.py` の autouse fixture `_isolated_state` に在った — 元々無い名前への `monkeypatch.delenv(name, raising=False)` は undo を記録しないので、その後にテストが `dsa.ensure_for_pytest()` を偽のクラスタで呼ぶと、直書きされた `PGHOST` 等が process に残る (root conftest が先に設定済みの起動条件では発火しない)。**別件にせず同じ変更セットで直した**: fixture が `_ENV_NAMES` の呼び出し前の状態を保存し、teardown の最後に戻す。`tools/testpg/dsa_testpg.py` の `ensure_for_pytest()` の直書きは conftest から呼ばれる本番経路の仕様なので触らない。完了条件 7 = `_ENV_NAMES` のどれも無い状態から偽のクラスタで `ensure_for_pytest()` を呼んだ後、どれも `os.environ` に無い。変異 M4 (復元を外す) → 赤。
- **道具**: `pt: 532 passed` (`tools/tests`)、`pt: 566 passed` (`conformance-tests/test_control_mapping_register.py` と `tools/tests` の結合実行。直す前は `562 passed, 1 error`)。`mutate.py`: M1・M1b・M2・M3・M1-conformance-audit (`1 failed, 42 passed, 1 error` = 復元を外すと結合実行の error が戻る)・M4 の 6 件とも `expect=red got=red`、復元は sha256 2 回で照合済み。レビューの追加変異 2 件 (保存を書き換えの後ろへ移す / 復元ループが 1 つの名前を飛ばす) も赤。
- **完了条件 → 観測**: 1 ← M1・M1b、2 ← M2、3 ← M3 (既存テストの `seen_env`)、4 ← 結合実行の集計行と M1-conformance-audit、5 ← 訂正註 1、7 ← M4、6 ← 本表。
- **コードレビュー** 2 回 (1 回目: 低 4・中 1・情報 1、2 回目: 差し戻し不要)。監督裁定: コメントに台帳 ID を書かない / 中 1 件は WP-1b として同じ変更セットで直す / 2 回目の任意の指摘 (fixture 側に残った復元ループの複製 5 行) は監督が削り、結合実行 `566 passed` を取り直した。範囲外の記録: adapter の import 時の `os.environ.setdefault` (`r2db-api/conformance/conformance_adapter_r2db_http.py`) は既存値を壊さず、復元の対象にしていない。
- **完了ゲート** (worktree、`gate.py -C`、基点 main `2172fb0`): `3763 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **起票文の訂正**: 台帳 R-58 行と `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` (訂正註 7) に記録した。
