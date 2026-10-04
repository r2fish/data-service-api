# 引き継ぎ書 — 2026-10-04 R-44 の閉止 (WP-4: 運用条件・文書・CI の正式な改訂)

本書は作業機の監督チャット (Fable) の記録である。依頼は「台帳 R-44 の『運用開始後』の印を外し、残りの WP-4 に着手する。枠決めから実施・レビュー・受け入れ・commit まで一気通貫で行う」(依頼者 2026-10-04。印を外す根拠の逐語: 「R-44 の印を外して WP-4 に着手するチップを出してください」)。`OC` は `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` は `docs/design/ROADMAP_POST_PHASE7_V1.md` を指す。現在地の値は `OC` §1.8 の 55a の出所から読む。

## 1. 現在地 (2026-10-04、本書の commit の直前の local main `11e0568` の時点の記録)

- 本書を含む変更セットを local main `11e0568` の上に commit して merge した。GitHub へは送信していない (`OC` §2 の 20)。
- 台帳は v1.168 (R-44 の閉止)。R-44 の行は記録ファイルへ移した。
- 契約・`security/CONTROL_MAPPING.md`・`conformance-tests/CONDITIONS.md`・`conformance-tests/COLLECTION_FLOOR` は変えていない。変更クラスは C (下限。`conformance-tests/README.md` と `conformance-tests/test_testpg_cluster.py` の docstring 1 箇所に触れた)。
- 完了ゲート (監督、main `11e0568` を取り込んだ作業ツリー): gate: 5232 passed, 2 subtests passed in 1181.43s (0:19:41), judge=PASS, label r44wp4, pg_database/pg_roles diff 0。ゲートの開始後に変えたのは文書だけである。`tools/tests` は 808 passed。

## 2. 本チャットで閉じたもの

**R-44 (テストが共有 PostgreSQL を使う問題、規模 M)。** WP-1〜WP-3 は 2026-09-16 に統合済みで、残っていた WP-4 を実施した。枠と突き合わせの表は `docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md` §5.1、記録は設計 `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` v0.4 §11。

- **突き合わせ**: 2026-09-16 の枠の 16 項目を実物と照合し、済み 5 (WP-1〜WP-3 で入っていた)、実施 10、実施しない 1 (nginx の bind 再試行) に分けた。
- **運用条件**: `OC` §1.3 の 19〜21・23 を書き換え、20a・24a を足した。§1.5 の 39、§1.6 の 41、§1.10 の 64、§2 の 3・12・19・21、§3 の 3・10・14。§2 の 4・5・18 は失効 (番号は残す)。旧条項と 2026-09-16 の訂正註は §4 の 16〜28。役割の雛形と `.claude/agents/` の 5 定義の gate と pytest の記述を合わせた。
- **道具**: `gate_running()` は共有ロックだけでは真を返さない (`handover_ready.py` が普通の pytest で NOT READY にならない)。排他ロックの待ち切れと他の gate の生きた intent だけが 75、基底ディレクトリの検査失敗とクラスタの起動失敗は 78。`mutate.py` の `expect: "error"` は終了コード 2〜4。`DSA_TEST_PG=external` は `PGHOST`・`PGPORT` を要求し、DSN の host・port との一致を見る。
- **CI**: `docker run` に `-c TimeZone=Asia/Tokyo`、workflow の `env:` に `PGHOST`・`PGPORT`。総行数と 106 行目以降の行番号は変えていない。
- **文書**: README 4 通と両 peer の runbook の該当箇所。
- **記録**: 設計 §7 の完了条件 3 (起動の形 5 種) と 4 (`pytest tools/tests` がクラスタを起動しない)、性能の基準値 (K=1、`--warmup 20 --n 200`、21 行)。

## 3. 次の一手

- 依頼者の事後確認 (§4)。
- 次の送信の CI run で、§4 の「手元で未検証」の 2 点を確かめる (`OC` §2 の 21 の (b) は、`PGHOST`・`PGPORT` と起動の設定 2 つを足した形で行う)。
- 本チャットの worktree と branch を `tools/dev/fold.py` で畳む。
- 残件は `tools/dev/ledger.py --open` で読む。

## 4. 依頼者判断待ち・未決

- **事後確認を求める監督裁定** (依頼者の方針 2026-10-03 により監督の推奨で進めた): (1) 運用条件の条文 (§1.3 の 19〜21・20a・23・24a、§1.5 の 39、§1.6 の 41、§1.10 の 64。§2・§3 の改訂を含む)、(2) WP-2 の軽微な 3 件は既知の穴にせず直す、(3) `DSA_TEST_PG=external` は `PGHOST`・`PGPORT` を要求し、DSN の host・port との一致まで見る (CI の `env:` に 2 行)、(4) nginx の bind 再試行は 4 経路に足さない (観察)、(5) `gate.intent` の unlink の競合は直さず、`gate_running()` の `LOCK_SH` の試行で受け止める (観察)、(6) DSN の `hostaddr=` と環境の `PGHOSTADDR`・`PGSERVICE` は検査しない (観察)、(7) Class C (下限) だが契約 JSON に触れないので契約の版は上げず、設計レビューの回数は規模 M の表に従う、(8) 性能の基準値は `--warmup 20 --n 200` の 1 回を記録として残し、共有クラスタ上の旧値とは比べない、(9) 台帳 §9 の 8 の B 行の「root suite 単独実行」の語は今回は直さない。
  - 【追記 2026-10-04】依頼者確認 (逐語): 「裁定 9 件を了承します」。事後確認待ちは無くなった。
- **手元で未検証**: (a) `postgres:16` の image が `-c TimeZone=Asia/Tokyo` を受けて起動すること。(b) workflow の `env:` の `PGHOST`・`PGPORT` を継承した各 job が緑であること。どちらも次の送信の run で初めて確かめられる (作業指示書 §6 の追記)。

## 5. 運用上の教訓

- 完了ゲートの実行中に並行チャットが main を進めた (1 回目のゲートは 17 分 25 秒かかり、その間に R-122 の閉止が入った)。ゲートの前と finalize の前の両方で `git log -1 main` を見る。作業ツリーの変更が main の変更と重ならなければ `git merge --ff-only main` で取り込める。
- 文書の所在を grep で探すとき、出力を `head` で切ると該当行を落とす (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §8 を「対象なし」と誤判定し、レビューで直った)。件数を先に数える。
- 行番号で引かれる文書 (`conformance-tests/README.md`、`tools/PERF_BASELINE_README.md`、`.github/workflows/ci.yml`、両 peer の README と runbook) は、行数を変えずに書き換えると出所の付け替えが要らない。

## 6. 裁定

担当: コード = コードレビュー 1 回目、文書 = 文書レビュー 1 回目、再 = 修正後の再確認、監査 = 受け入れ監査。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| コード 1: `gate_running()` が intent の unlink の競合で排他の保持者を見落とす | 直した (競合そのものは観察) | `suite.lock` への `LOCK_SH` の非ブロッキング試行を足した。inode の照合までは直さない — 排他は `suite.lock` が保ち、影響は引き継ぎ判定だけで、それも試行が受け止める |
| コード 2 / 文書 F5: `conformance-tests/test_testpg_cluster.py` の docstring が manifest の外 | 直した | 作業指示書 §5.1 (d) の訂正註で監督の触るパスに加えた |
| コード 3: external が `PGHOST`・`PGPORT` の有無しか見ない | 直した | DSN の `host=`・`port=` との一致を要求する |
| コード 4: テスト docstring の変異の記述が実行した spec と違う | 直した | 実行した spec の文面に合わせた |
| コード 5: CI の `TimeZone` が未確認 | 直した (記録) | 作業指示書 §6 に、次の送信の run で確かめる項目として足した |
| 文書 F1: r2db の runbook §8 を「対象なし」とした判定が誤り。MitateDB の runbook の冒頭にも同種の記述 | 直した | 両方を現物に合わせ、突き合わせの表を改めた |
| 文書 F2: 「道具が待たせる」が現物と違う | 直した | 素の pytest は待ち、`pt.py`・`mutate.py` の既定と性能計測中の gate は REFUSED 75 |
| 文書 F3: `tools/dev/README.md` の gate の例と `gate.py` の docstring に `-C` が無い | 直した | 例と docstring、Rules 欄の番号 |
| 文書 F4: 役割定義 2 箇所に「単独実行」が残る。台帳 §9 の 8 の B 行にも同じ語 | 直した (台帳 §9 は観察) | 役割定義は直した。台帳 §9 の表は変更クラスの規約であり、今回の範囲に入れない |
| 文書 F6: 行番号の出所が引用の内容を指していない | 直した | `PERF-README`:91-103、`CT-README`:174-181 |
| 文書 F7: §4 の 18 の失効理由「引数は同じ」が偽 | 直した | `--durations=25` が加わったことを書いた |
| 文書 F8: `OC` §2 の 21 (b) に起動の設定が無い | 直した | `max_connections=300`・`TimeZone=Asia/Tokyo` を足した |
| 文書 F9: 作業指示書 (a) の 7 の列挙が実際と違う | 直した | 書き換え・新設・変えない条項を書き分けた |
| 文書 F10: 理由文、日付の註、Rules 欄、20a の列挙、24a の `gate.intent` | 直した | 5 点とも |
| 文書 観察: `MitateDB-api/README.md` の行数が 2 行増えた | 直した | 299 行に戻した |
| 文書 クラス: Class C の証拠列 (契約版数の更新、設計レビュー 2 回) との関係 | 観察 | 契約 JSON に触れないので版は上げない。役割と回数は規模 M の表が上書きする (`OC` §1.13 の 74) |
| 再 F-a: 設計 §11.3 の記録が `gate_running()` の修正と食い違う | 直した | 記録を実装に合わせた |
| 再 F-b: `_devlib.py` のコメントが偽になった | 直した | コメントを実装に合わせた |
| 再 F-c: M5 の docstring が実測 (`KeyError`) と合わない。「both cases」は 1 件目しか観測していない | 直した | 実測の理由と「先に走る 1 件」に改めた |
| 再 F-d: DSN の `hostaddr=` と環境の `PGHOSTADDR`・`PGSERVICE` を検査が見ない | 観察 | 手で external を使う場合だけで、このリポジトリの DSN は `hostaddr=` を使わない。DB の利用者は気づかず、台帳 §0.1 の終了条件も破らない |
| 再 F-e: `OC` §5 に §1.3-20a の鍵が無い | 直した | 鍵を足した |
| 再 F-f: (d)(ii) に対応する変異と完了ゲートが記録に無い | 直した | 作業指示書 §5.1 (d)(iii) と設計 §11.4 |
| 再 F-g: 記録の `pghost=<base>/None` が path に読める | 直した | `pghost=unset` |
| 監督: nginx の bind 再試行が 4 経路に掛かっていない (作業指示書 §4.1、2026-09-16 の裁定 R-7 の積み残し) | 観察 | 4 経路のポートは起動前に宣言値として確定しており、別ポートでの再試行は宣言と実体を食い違わせる。競争に負けた実行は赤で止まる |
| 監査 条件 9: 設計 §11.1 の 2 行が道具の生の出力と違う | 直した | 書き換えたことを開示する 1 句を足した |
| 監査 条件 10: `tools/tests` の実行の後にテストファイルが更新された / 変異表と完了条件の対応が文書に無い | 直した | commit の前に `tools/tests` を回し直し、対応を作業指示書 §5.1 (d)(iii) と設計 §11.4 に記録した |
| 監査 疑義 (a): `OC` §1.6 の 41 の旧文を §4 に移していない | 直した | §4 の 28 |
| 監査 疑義 (b): 完了ゲートに性能差分を添えていない | 観察 | 両 peer の `src` を変えておらず、設計 §11.2 が同じ作業ツリーの値である |
| 監査 観察 1: r2db の runbook に共有クラスタの接続の記述が残る | 直した | 2 行を現物に合わせた (行数不変) |
| 監査 観察 2: 完了ゲートを load average 15 / 27 / 28 で始めた | 観察 | 負荷は直前の自分のゲートの残りで、他の gate と pytest は走っていなかった。記録に値を書いた。所要は伸びたが判定は変わらない |
| 監査 観察 3: 「DSN に port 無し、`PGPORT` も無し」の組だけを押さえるテストが無い | 観察 | `PGPORT` の要求を外す変異は M5-port が赤にする。道具の穴であり製品の欠陥は通らない |
