# 引き継ぎ書 — 2026-10-05 R-39 テストの穴と古い位置参照 (閉止)

本書は作業機の監督チャット (Fable) の記録である。依頼は台帳 R-39 (複数のテストの穴の一括追跡、規模 M。着手条件は「運用開始後」だった) の前倒し着手 (依頼者指示 2026-10-05、逐語:「R-39を着手するチップを出して」)。変更セット 1 (テストの穴、Class B) と変更セット 2 (行番号形の位置参照の修正とガード、Class C) で閉止した。作業指示書は `docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md` (記録は同書 §10)。

## 1. 現在地 (2026-10-05、本書の commit の時点の記録)

- local main `7b902e6` (変更セット 2 の merge)。本書の変更はその上の 1 commit と merge commit である。origin/main は `092e1a1` のままで、`git rev-list --count origin/main..main` は本書の前の時点で 16。GitHub へは送信していない (送信は Mitate の監督が依頼者の指示で行う。`OPERATING_CONDITIONS.md` §2 の 20)。
- 契約 `spec/data-service-api.v1.json` の contract_version は 1.16.0 (本チャットでは変えていない)。
- `security/CONTROL_MAPPING.md` は 3.26 (本チャットでは変えていない。配備の受入の範囲も変えていない)。
- 台帳は v1.181 (R-39 閉止)。`tools/dev/ledger.py --open` は open=17 (印なし 11、印あり 6。未着手 10、進行中 7)。
- `conformance-tests/COLLECTION_FLOOR` は 5276 (変更セット 1 で 5248 → 5276)。
- 完了ゲート (監督): 変更セット 1 `gate: 5276 passed, 2 subtests passed in 2634.21s (0:43:54)`、label r39-cs1。変更セット 2 `gate: 5276 passed, 2 subtests passed in 753.62s (0:12:33)`、label r39-cs2。どちらも judge=PASS、pg_database/pg_roles diff 0。変更セット 2 の時点の tools/tests は 814 (監督の記録)。

## 2. 本チャットで閉じたもの

| 変更セット | commit (merge) | 内容 |
|---|---|---|
| 変更セット 1 (テストの穴、Class B) | `d220c15` (`3042774`) | 両 peer の新規テスト 10 本 (r2db 6、MitateDB 4) で 28 性質を固定。既存テストと `src/` の変更 0。変異 28 件 + レビューが足した 2 件が赤。台帳 v1.180 で R-39 着手 (印を外した、Y-1)、R-123・R-124 を起票 (Y-5)、R-22 行へ `src/` 側の古いコメントを引き渡し (Y-2)。記録は作業指示書 §10.1 |
| 変更セット 2 (位置参照、Class C) | `258326c` (`7b902e6`) | tests / conformance / conformance-tests / MitateDB README の「現在の所在の主張」の行番号形を行番号に依らない形へ (最終の検出形で 206 → 48、除去 158)。時点の記録と位置参照でないものは新ガード `tools/tests/test_no_line_number_position_refs.py` の allowlist (45 entry・48 件、件数固定) に置いた。不正確な文 3 種と README の 2 文を現物に合わせた。R-95 の床を実測へ下げた (Y-9)。`src/` の変更 0、assert・期待値の変更 0。ガードの変異 10 件と R-95 の変異 29 件が期待どおり。`tools/dev/mutate.py` に Known gaps 3 (Y-19)。台帳 v1.181 で R-39 閉止。記録は作業指示書 §10.2 |

- 棚卸しで閉止済み・前提消滅とした件 ((1b)(1g)(3a) 閉止済み、(1m) 既存の literal pin が固定済み、(1h) の bool の offset は前提消滅) は作業指示書 §4 にある。
- 置換件数の数え方 (実装報告の段階集計 138 は逐語に再現しない) は作業指示書 §10.2 にある。
- 受け入れ監査 (変更セット 2、1 回): C2-1・C2-2・C2-5・C2-6 と受入 2〜5 は充足。C2-3・C2-4 は §10.2 に逐語の記録を残して充足。監督は変更セット 2 を受け入れた。

却下した代替案 (作業指示書 §2.2・§9.5 の転記):

- 既存の parity テスト (`test_postgres.py` / `test_foundation.py`) に値を足す — CS-2 と同じファイルを触るので却下。
- C-xx 条件への昇格 — `pg_text_format` の parity は r2db の plug 内の一致であり共通契約の文言ではない。契約が number 列の text 形を定めるかは起票先で決める (§8 の Y-4)。
- 行番号を現在値に引き直す — 次の編集で再び腐る。R-37 以降 4 回引き直している。
- `src/` のコメントも同じ変更セットで直す — 来歴検査器 (CH-ID の無い塊は変更が全て赤) と R-22 の受け皿に衝突する (§8 の Y-2)。
- ガードを conformance-tests 内に置く — 走査対象が両 peer の tests と README を含み、リポジトリ衛生の検査器は `tools/tests` が置き場 (前例 `tools/tests/test_leaf_import_direction.py`、`tools/tests/test_src_import_cycles.py`)。

(上の「§8」は作業指示書 `WORK_ORDER_R39_TEST_GAPS_V1.md` の §8。)

## 3. 次の一手

- 依頼者の事後確認 (§4 の表)。
- 次の項目は `tools/dev/ledger.py --open` の順 (印なし先) で選ぶ。
- 台帳 R-22 の次の変更セットの候補に、R-39 から渡した `src/` 側の古い位置参照・不正確なコメントが加わっている (台帳 R-22 行の【追記 2026-10-05 (R-39 からの引き渡し)】、R-39 の監督裁定 Y-2)。
- worktree `r39` と `r39-refs` は監督が畳む。

## 4. 依頼者判断待ち・未決

### 4.1 監督裁定の逐語 (事後確認待ち。最終節「裁定」= 指摘ごとの処置とは別)

以下は監督裁定の逐語である (推奨で進め、事後確認を取る。依頼者方針 2026-10-03)。Y-1〜Y-6 は作業指示書 §8 にも同文がある。

| # | 裁定 | 推奨の理由 |
|---|---|---|
| Y-1 | 台帳 R-39 の印「あり」(着手条件: 運用開始後) を「なし」に改め、着手条件の欄に「依頼者指示 2026-10-05 で前倒し」と記す | 固定欄が正 (LEDGER_FIXED_FIELDS D-2)。条件が消えた行に印を残すと `ledger.py --open` の並び (印なし先) が実態と食い違う。経緯は【追記】に残す (R-14、行を消さない) |
| Y-2 | 両 peer の `src/` にある古い位置参照・不正確なコメント (structured.py L146-148、cell.py L1910/1916/1981/2546/3869/3934、limits.py L315-316、capabilities_document.py L335/374/376、config.py L56) は R-39 で直さず、台帳 R-22 の次の変更セットの候補として R-22 行へ【追記】で渡す | 来歴検査器は CH-ID の無い塊の変更をすべて赤にし (設計 §4.1 (2) v0.22、reader 実測)、正規の経路は CH-ID 登録 + 訂正記録 (§9.3) = R-22 の作業そのもの。R-39 で同じ塊を触ると受け皿と衝突する。R-22 側は CM の位置参照の引き直しも手順に持つ |
| Y-3 | tests/・conformance/・conformance-tests/・README の `file.py:NNNN` 形の参照は、「現在の所在の主張」なら行番号に依らない形 (`file.py::symbol`) に直し、「時点の記録」は触らない。再発防止に tools/tests へ静的ガード (行番号形の位置参照 0 件、時点の記録は逐語 allowlist) を置く | 行番号は設計上腐る (R-37 以降 4 回引き直している)。symbol 形は移動に追随しないが grep で検証できる。ガードが無いと同じ穴が再び開く |
| Y-3a | Y-3 のガードの対象は `(structured\|cell\|service).py` に限らず、tests/・conformance/・conformance-tests/・両 peer README にある全ての `<module>.py:NNNN` 形 (reader が同じ hunk に見つけた 25 件を含む)。時点の記録 8 件は逐語の allowlist (file、トークン、記録である理由) に置く | 行番号参照が腐る性質は module を選ばない。同じファイルの同じ種類の欠陥を残すと、ガードを allowlist で広げるしかなくなる |
| Y-4 | `pg_text_format` の実 PG parity を C-xx 条件へ昇格しない | r2db の plug 内 (in-memory と PG) の一致であり共通契約の文言ではない。契約が number 列の text 形を定めるかは起票先 (pg_text_format の不一致の行) で決める |
| Y-5 | 製品コードの変更が要る疑い 2 件を台帳に起票する: (R-123) r2db `pg_text_format` の実 PG との不一致 (1e15〜1e16 の指数表記、jsonb `-0.0` → `0.0`)、(R-124) order_by 項目の details.field path の peer 差 (r2db `order_by/direction`、MitateDB cell 層 `order_by/<i>/direction`) と契約の path 規則の確認 | R-39 の枠 (挙動を変えない) の外。R-39 で直すと Class B の製品変更が混ざる |
| Y-6 | MitateDB README L267-269 の「`deployment_required` はどの peer の宣言コードにも無い」は `capabilities_document.py:57` が返す現状と食い違うので、CS-2 で実装担当が確認して文を直す (位置参照ではなく内容の古さ) | 同じ README の同じ節を触る変更セットで直すのが最小 |
| Y-7 | CS-1 実装報告 §5 の疑義 (1d の request 計測の peer 差: r2db は兄弟の共有も循環扱い・未知型 VALIDATION_FAILED、MitateDB は祖先経路のみ・未知型 8) は観察とする | 各 peer は自分の request_bytes の bound と計測を宣言し、契約 (C-05) が求めるのは宣言と実施の一致であって peer 間で同一の計測ではない。DB の利用者は宣言値を読んで振る舞い、計測差を契約違反として気づく経路が無い |
| Y-8 | C1-8b (到達不能な leaf の `PG_x` 通過の pin) は残す | 設計 §10.6 の 17 が名指しした穴であり、`startswith` の大小区別という変異の穴を塞ぐ。identifier 構文が変わって大文字が通るようになった日に、この pin が「予約名の検査は大小を区別する」事実を見える形で問い直す |
| Y-9 | CS-2 と R-95 (`conformance-tests/test_conformance_docstring_position_refs.py`) の衝突は両論 (a) を採る: R-95 の実コーパスの床 (SHAPE_A=22 ほか) を CS-2 後の実測へ下げ、行をまたぐ参照の pin は実在が無くなったので合成 fixture に替える。R-95 の作業指示書の変異 (join 規則を壊す M5a 等) を床を下げた後に再実行し、緑になるものがあれば fixture 側のテストで赤にする。CS-2 の触ってよいパスに同ファイルを足す | 床は R-95 自身の走査が各 shape を実際に通ることの保証であり、コーパスの行番号参照を残すための装置ではない。(b) は行番号参照 22 件を allowlist に残すことになり、CS-2 の目的 (行番号参照を腐らない形へ) と矛盾する。R-95 の検査 (参照の実在と範囲) は allowlist の記録に対して今後も働く |
| Y-10 | CS-2 実装報告 §4 の、既存テストに残る `{scratchpad}` 参照 (r2db test_ops_declarations:475、l1_details:734、MitateDB test_main:147、adapter:2044 ほか) は観察とし、台帳に載せない | OC §1.9 の 62 は新規の持ち込みを禁じる規律で、既存分は過去の変更セットで受け入れられている。製品の利用者が気づく経路は無い。後日の S 項目として再起票は自由 |
| Y-11 | MitateDB README :257 の「requests_per_minute と concurrency は enforced」は現物では条件付き (ceiling > 1 かつ共有機構なしなら `deployment_required`) なので、C2-4 と同じ節の内容の古さとして CS-2 で直す | Y-6 と同じ理由 (同じ README の同じ節を触る変更セットで直すのが最小) |
| Y-12 | CS-2 レビュー指摘 1 (ガードが見ない形の行番号参照: `` `x.py`:N ``、`x.py:` + 改行 + N、`.md:N`) は CS-2 で直す。ガードの正規表現を「`.py` / `.md` / `.json` の後ろに backtick 任意、`:`、空白・改行・コメント接頭辞 `#` を挟んで数字」まで広げ、残る穴は「直前の path を継ぐ bare `:N`」だけにして Known gaps に書く。`.md:N` の現在の主張は行番号に依らない形 (`CONDITIONS.md` の `C-NN` 行、見出し名) へ。R-95 の床は再実測 | 先送りしない (依頼者原則)。ガードが見ない形を残すと同じ穴が次の日に開く。直す費用は同じ変更セットが最小 |
| Y-13 | 新ガードの行を `tools/dev/README.md` の Known gaps 一覧に足す (触ってよいパスに加える) | OC 1.12-71 が一覧の置き場を定めている。先例が割れているのは一覧側の抜けであり、新規は従う |
| Y-14 | レビュー指摘 5 のうち README :266「(same function)」は語を直す。`conformance_adapter_r2db.py:318` の元からの矛盾 (「before `_transact_locked` … executes anything」) と R-95 の `SHAPE_B_FLOOR = 0` で常に真になる assert は観察 | :266 は同じ変更セットの同じ文の明確化。:318 は元からの文で CS-2 の規則 (文を変えない) の外、利用者が気づく経路なし。床 0 の assert は fixture が同じ shape を検査しており検査器の穴ではない |
| Y-15 | 再確認の指摘 1・3 (backtick 付きの bare `` `:N` `` と「line NNN」「lines NNN-MMM」の語形。6 件は既に腐っている) も CS-2 で直す。ガードの検出形に「`` `:[0-9]+` `` (backtick で囲まれた bare)」と「`\blines? [0-9]+(-[0-9]+)?\b`」を足し、残る Known gap は「backtick 無しで直前の path を継ぐ bare `:N`」と「`.py`/`.md`/`.json` 以外の拡張子」だけにする。R-95 の床は再実測 | Y-12 と同じ理由 (先送りしない)。backtick 付き bare と語形は path 継承の解析なしに正規表現で拾え、偽陽性は allowlist で吸収できる |
| Y-16 | 再確認 2 回目の指摘 1 (拡張子の無い `name:NNN`、`~:NNN`、`L<数字>` の形。3 件は腐っている) も CS-2 で直す。ガードの検出形に「英字で始まる名前 (`-`・`_`・`.` を含む) に直接付く `:NNN`」(`\b[A-Za-z][A-Za-z0-9_.-]*:[0-9]+(?:-[0-9]+)?\b`、既存の 3 形を包含) と `~:[0-9]+` を足し、偽陽性 (時刻・版数等) は allowlist の not-a-ref で吸収する。`L<数字>` は L1 語彙 (`L1`、`L7-19`) と衝突するので検出形に入れず、Known gap に書いて現物 2 件だけ名前の形に直す。`test_ops_apply_platform_migration.py` は走査対象 dir 内なので触ってよいパスに含める | Y-12・Y-15 と同じ理由。偽陽性は件数固定の allowlist で見えるので、規則を広げる費用は 1 回で済む |
| Y-17 | ガードは host:port 形 (名前が `.invalid` で終わる、または `localhost` の後の `:NNNN`) を一致から除く。偽陽性 14 件を allowlist から外す | `example.invalid:5432` は公開リポジトリ規律 (OC §1.9 の 60) が定める合成ホスト名の常用形で、新しいテストが書くたびに allowlist を触らせるのは検査器を保守の負債にする。位置参照の形とは文法で区別できる |
| Y-18 | 再確認 3 回目の指摘 1 (`_` 始まりの名前、大文字 `Line`) は (i) 検出形を広げる (`[A-Za-z_]`、`[Ll]ines?`) で直す。走査対象で増える一致は 0 件 (レビュー実測) | 検出形の 1 文字の差で、Known gap に書くより直す方が安い。allowlist は動かない |
| Y-19 | tools/tests を対象にした `mutate.py` の entry は suite lock を取らず (lock は root conftest.py が取り、tools/tests は独自 root)、完了ゲートの測定中に suite ファイル (test_foundation.py) へ変異を書いて復元した (2026-10-05 23:22、ゲートは 23:14 開始・収集済み)。これは検査器の既知の穴とし、`tools/dev/mutate.py` の Known gaps 3 に書く。起票しない。ゲートの判定は有効とする | OC 1.12-71 の問い: この穴を通って製品の欠陥が完了ゲートを抜けられるか → いいえ (変異は復元され、収集は変異の前に済んでいる。ゲートが測る code は commit される code と同じ)。監督の手順の穴 (ゲート中に tools/tests の変異を発注した) は引き継ぎ書の教訓に書く |
| Y-20 | 監査の設計疑義 (R-95 の床 2 が c05 の時点の記録 2 件の存在に依存する) は観察とし、床は余裕なしの実測 2 のまま維持する | 床の役割は走査の後退をすぐ赤にすること (M14 の 7 件が赤で実証)。記録 2 件はガードの allowlist に件数付きで固定されており、消すときは意図した変更セットで床も再実測する。先に 0〜1 へ下げると後退が見えなくなる |

### 4.2 事後確認の表

**確認済み (2026-10-06)**: 依頼者 (逐語): 「事後確認は了承します」 — 下表の全行 (Y-1〜Y-20、Y-3a を含む) を了承。台帳 v1.182 と記録ファイルの R-39 節末尾に記録した。下表は起草時のまま残す。

| Y 番号 | 要旨 | 確認欄 |
|---|---|---|
| Y-1 | 台帳 R-39 の印「あり」を「なし」にし、着手条件の欄に前倒しを記す | |
| Y-2 | `src/` 側の古い位置参照・不正確なコメントは R-39 で直さず R-22 へ渡す | |
| Y-3 | 現在の所在の主張は `file.py::symbol` 形へ、時点の記録は触らず、tools/tests に静的ガードを置く | |
| Y-3a | ガードの対象を全 module の `<module>.py:NNNN` 形に広げ、時点の記録は逐語の allowlist に置く | |
| Y-4 | `pg_text_format` の実 PG parity を C-xx 条件へ昇格しない | |
| Y-5 | R-123 (`pg_text_format` の実 PG との不一致) と R-124 (order_by 項目の details.field の peer 差) を起票する | |
| Y-6 | MitateDB README の `deployment_required` の文を CS-2 で現物に合わせる | |
| Y-7 | 1d の request 計測の peer 差は観察 | |
| Y-8 | C1-8b (到達不能な leaf の `PG_x` 通過の pin) を残す | |
| Y-9 | R-95 との衝突は両論 (a): 床を実測へ下げ、行またぎの pin を合成 fixture に替え、R-95 の変異を再実行する | |
| Y-10 | 既存テストに残る `{scratchpad}` 参照は観察 | |
| Y-11 | MitateDB README :257 の enforced の文を CS-2 で条件付きに直す | |
| Y-12 | ガードの検出形を `.py`/`.md`/`.json` + backtick・改行・`#` まで広げ、`.md:N` の主張も直す | |
| Y-13 | 新ガードの行を `tools/dev/README.md` の Known gaps 一覧に足す | |
| Y-14 | README「(same function)」は直し、`conformance_adapter_r2db.py:318` の元からの矛盾と `SHAPE_B_FLOOR = 0` の assert は観察 | |
| Y-15 | backtick 付き bare `` `:N` `` と「line(s) NNN」語形も検出形に足して直す | |
| Y-16 | 拡張子の無い `name:NNN` と `~:N` を検出形に足し、`L<数字>` は Known gap とし現物 2 件だけ直す | |
| Y-17 | host:port 形 (`.invalid`、`localhost`) を一致から除く | |
| Y-18 | `_` 始まりの名前と大文字 `Line` も検出形に含める | |
| Y-19 | tools/tests 対象の mutate.py が suite lock を取らない件は既知の穴 (`tools/dev/mutate.py` Known gaps 3)、起票しない、ゲートの判定は有効 | |
| Y-20 | R-95 の床 2 が記録 2 件に依存する件は観察、床は実測 2 のまま | |

### 4.3 未決 (起票のみ。判断は次の着手時)

- 台帳 R-123 (r2db `pg_text_format` の実 PG との不一致): 契約が number 列の text 形を定めるか。
- 台帳 R-124 (order_by 項目の details.field path の peer 差): 契約の path 規則。

## 5. 運用上の教訓

- 負荷 (他プロジェクトの vitest と fseventsd、load average 50〜100) 下の完了ゲートは 44 分かかり、1 回目は背景の 30 分上限で止まった。負荷が高いときは 2 時間上限で起動する。
- haiku の explorer は複数語の句の grep で行の折返しを見落とし、「削除済み」と誤報した (limits.py、test_audit_query の 2 件、structured.py L146-148)。句は 2〜3 語に切って grep させ、否定の結論は監督が 1 件 grep で確かめる。
- 位置参照の検出形は、1 巡目の `.py:NNNN` から 6 形 + host:port 除外まで 4 回広がった (レビュー 1 巡 + 再確認 3 回)。行番号形の列挙は最初から「拡張子・backtick・改行・語形・拡張子無し」を全部試す。
- tools/tests だけを対象にする `mutate.py` は suite lock を取らず、ゲート測定中に suite ファイルへ変異を書いた (Y-19、`tools/dev/mutate.py` Known gaps 3)。ゲート中は tools/tests の変異も発注しない。
- 来歴検査器は CH-ID の無い塊の変更をすべて赤にするので、`src/` のコメント修正は R-22 の経路 (CH-ID 登録 + 訂正記録) でしか行えない (Y-2)。
- 公開値スキャンは `pt` の log 名 (ハイフン区切りの日付と時刻) を project id と誤検知する (既知)。文書には `pt YYYYMMDD-NNNNNN` の形で書く。
- R-95 の実コーパスの床は、参照を減らす変更セットで下がる。床を下げる変更セットは R-95 の変異を再実行する。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー (CS-1) 1: C1-9 の境界値が生文字 (U+D7FF / U+E000) | 直した | エスケープ表記に |
| レビュー (CS-1) 2: docstring の出所 "3c-24" が設計に無い | 直した | 設計 §10.9 の 24 行目の記録と現行コードの順序に書き換えた |
| レビュー (CS-1) 3: "both peers' r2db cells" の誤読 | 直した | r2db-api の 2 cell に |
| レビュー (CS-1) 4: 作業指示書 C1-10c の例 (best_effort) が現行と食い違う | 直した | 作業指示書 §3 に訂正註 |
| 実装 (CS-1) 疑義 1: 1d の request 計測の peer 差 | 観察 | Y-7 |
| 実装 (CS-1) 疑義 2: C1-8b は到達不能な leaf の pin | 観察 | Y-8 (pin は残す) |
| レビュー (CS-2) 1: ガードが見ない形 (`` `x.py`:N ``、改行、`.md:N`) に腐った参照 4 件 | 直した | Y-12 |
| レビュー (CS-2) 2: Known gaps に `.md:N` が無く、DEVTOOLS の一覧に行が無い | 直した | Y-13 |
| レビュー (CS-2) 3: test_application_audit の 2 箇所の参照が 1 つになった | 直した | `tamper_vectors` 経由の文に |
| レビュー (CS-2) 4: test_process_ceilings_declaration の指す先が曖昧 | 直した | kwarg を名指しした |
| レビュー (CS-2) 5a: README :266「(same function)」 | 直した | Y-14 |
| レビュー (CS-2) 5b: `conformance_adapter_r2db.py:318` の元からの矛盾 | 観察 | Y-14 (元からの文。CS-2 の規則の外、利用者が気づく経路なし) |
| レビュー (CS-2) 5c: R-95 の `SHAPE_B_FLOOR = 0` で常に真の assert | 観察 | Y-14 (fixture が同じ shape を検査) |
| 実装 (CS-2) §4: 既存テストの `{scratchpad}` 参照 | 観察 | Y-10 |
| 実装 (CS-2) §5: R-95 の床との衝突 | 直した | Y-9 (両論 (a)) |
| 実装 (CS-2) §4: README :257 の enforced が条件付き | 直した | Y-11 |
| 再確認 1 の 1: bare `` `:N` `` 27 候補、6 件腐敗 | 直した | Y-15 |
| 再確認 1 の 2: R-95 作業指示書の訂正註の床が古い | 直した | 経緯と最終値に |
| 再確認 1 の 3: 「line NNN」語形、同一ファイルで直し方が割れる | 直した | Y-15 |
| 再確認 1 観察: allowlist 件数の報告誤り、c12/c30 の書き方の不揃い | 直した | 差し戻し 3 で件数を訂正し、書き方を揃えた |
| 再確認 1 観察: c04 旧 `:218` の文の書き換え | 観察 | 述べている事実は正しい |
| 再確認 2 の 1: 拡張子の無い `name:NNN`、`~:N`、`L<数字>`。3 件腐敗 | 直した | Y-16 (`L<数字>` は検出形に入れず Known gap、現物 2 件は直した) |
| 再確認 2 観察: `` `:125-130` `` の分類 | 観察 | 分類は許容範囲 (差し戻し 6) |
| 再確認 2 観察: 作業指示書 §9.3 の旧い正規表現 | 直した | 作業指示書 §9 の訂正註 |
| 監督 (実装報告): host:port の偽陽性 14 件が allowlist に | 直した | Y-17 |
| 再確認 3 の 1: `_` 始まりの名前、大文字 `Line` が検出されない | 直した | Y-18 |
| 再確認 3 観察 1: 作業指示書 §9.2 が未更新 | 直した | 訂正註 |
| 再確認 3 観察 2: record `test_c05:371` は今は別の行 | 観察 | 時点の記録 (当時の集計) |
| 監督: tools/tests 対象の mutate.py がゲート測定中に suite ファイルへ変異を書いた | 既知の穴 (§1.12 の 71) | Y-19、`tools/dev/mutate.py` Known gaps 3 |
| 監査 設計疑義: R-95 の床 2 が c05 の時点の記録 2 件の存在に依存する | 観察 | Y-20 |
| 監査 §2: C2-1 の「138 置換」は証拠不足 (現物は検出形 206 → 48、除去 158。原文の正規表現で 120 → 29) | 直した | 作業指示書 §10.2 を現物の再計数に置き換えた。台帳 v1.181 の版数行と閉止行の「91 件 / 記録 16 件 / 138 件」は段階集計の値であり、記録ファイルの R-39 節末尾の【追記】で現物の値を補った |
| 監査 §7-1: 作業指示書 §10 の CS-2 記録が未記入 | 直した | §10.2 に集計行・変異表・C2-3 / C2-4 の新文 (diff の追加行の逐語) を置いた |
| 監査 §7-2: 訂正註に `tools/dev/mutate.py` が無い | 直した | 訂正註に Y-19 の 1 文を足した |
| 監査 §7-3: 監督の記録の下書きの古い数値 (変異 9 件 / 差分 46) | 直した | §10.2 は 10 件 (mutate 20261005-232256) / 47 ファイル |
| 監査 §7-4: 138 の併記 | 直した | 上の §2 と同じ |
| 監査 §7-5: §9.4 の 1 の 2 ファイル同時の再実行 | 直した | 最終形で `pt: 31 passed in 3.32s` (pt 20261005-233907) |
| 監査 §7-6: ゲートの log に測った木が残らない | 観察 | `tools/dev/gate.py` の Known gaps 2 (`-C` の指し間違いは検出しない) が既に記す。製品の欠陥がこの穴で完了ゲートを抜ける経路は無い (測った木と commit した木の同一性は監督が §1.3 の 19 の `-C` で保証する) |
