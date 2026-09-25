# 引き継ぎ — 2026-09-24/25 (keyset ページング (高速化案 7、フェーズ11) の閉止。契約 1.10.0、C-30、main へ 1 回 merge)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `HANDOVER_20260924_FABLE6.md`。並走した最低共通機能プロファイル (R-29) のチャットの書は `HANDOVER_20260925_FABLE.md`。

本書は依頼者指示 2026-09-24「keyset ページングと R-29 を新しいチャットで開始する」で始まった 3 つのチャットの記録である。1〜2 つ目のチャットは設計 (v0.6)・作業指示書 (v1.2)・WP-1/2/5/3 まで。**3 つ目のチャット (2026-09-25、本チャット) は WP-4 のコードレビューから再開し、WP-4 → main 取り込み (番号の振り直し) → WP-6 → WP-7 → 完了ゲート → 受け入れ監査 → Q-4 → main へ 1 回 merge まで進めた。** 本書の名前は `HANDOVER_20260924_FABLE7.md` から改めた (§2)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260924_FABLE7.md`

## 1. 現在地

- **main への merge 済み**: `本書を含む閉止の変更セットを `finalize.py --tools-tests` で main `b283f48` へ no-ff で merge (branch HEAD の次の main の merge commit。依頼者裁定 Q-4 了承 2026-09-25)` (統合 branch `claude/cranky-visvesvaraya-616e67` を 1 回で merge)。統合 branch の commit: WP-1 `3af11b3` / WP-2 `a2ba943` / WP-5 `f3b10ca` / WP-3 `1c362fc` / WP-4 `cb64217` / 本書の改名 `c2a6a64` / main `b283f48` の取り込みと番号の振り直し `285cfe4` / WP-6 `5d988c6`。
- **契約 1.10.0** (両 peer の data 面・control 面が宣言)。共通条件 **C-30** (9 node、T は 7 変種、6 plug)。port v1.18、従属判断 15、migration 0015、`_ISOMORPHIC_TARGETS` 159 行、`security/CONTROL_MAPPING.md` 3.3、台帳 v1.121。
- 台帳: **R-109 閉止 / R-110 未着手 / R-111 起票** (規模 M、未着手)。
- 完了ゲート: `gate: 4168 passed, 2 subtests passed in 327.60s (0:05:27), judge=PASS, pg_database/pg_roles diff 0, label p11b (final tree; the first gate on ff6ad67, label p11, was 4167 passed in 327.83s, judge=PASS, before the SQLite tampered-cursor test was added)`
- WP-7 (性能の証拠、設計 §11): K=1 `perf_baseline.py --warmup 20 --n 200` (PERFRUN commit=5d988c6) 21 行すべて §0.1.4 の閾値内 (Δp50 最大 +24.2% / +40%、Δp95 最大 +25.5% / +50%、backend_calls 差分 +0.00。比較対象 PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1 §2.3 2026-09-23); 深いページ比較 (r2db PostgreSQL、N=20000、page.size=100、25 回): offset (0fee6e5) 走査 1.401 s / 末尾ページ p50 4.096 ms、keyset 0.823 s / 3.287 ms、両方とも末尾行 n=19999 に到達 (非空振り)。commit ff6ad67
- push は停止中 (GitHub 課金上限)。
- 本チャットの裁定の材料は監督チャットの scratchpad の `rulings-*.md` (4 本。「裁定」節に逐語で転記済み)。前チャットの `.handover-materials/` は削除済み。

## 2. 本チャットで決めたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 番号の振り直し (main `b283f48` の取り込み) | 並走の R-29 が main へ先に merge し仮番号を消費したため: 契約 1.9.0 → **1.10.0**、C-28 → **C-30**、R-106 → **R-109**、R-107 → **R-110**、従属判断 14 → **15**、port v1.16 → **v1.18**、`CONTROL_MAPPING` 3.2 → **3.3**、台帳 v1.120 → **v1.121**。不変: migration 0015、件数ピン 156 → 159 | 作業指示書 §9 の訂正註、設計 §0、`285cfe4` |
| 本書の名前 | `HANDOVER_20260924_FABLE7.md` → `HANDOVER_20260925_FABLE2.md` (main に R-29 側の同名の書があった) | `c2a6a64` |
| main を WP-6 の前に取り込む | WP-6 が確定番号で書けるように、WP-6 の前に取り込んだ。main への merge は WP-7 後の 1 回のまま | `285cfe4` |
| Opus 役のモデル実測 | reviewer の transcript の `"model"` 欄 18/18 件 `claude-opus-5-5` | — |
| WP-4 の逸脱 8 件 | 採用 1・2・3・5、差し戻し 4 (誤りは C-30 側の継続要求の page_size。監督が 5 箇所を発行時と同じ page_size に直し、孤立化 fixture は 5 / 50 のまま)、6 は R-111 で起票、7 は pin テスト `MitateDB-api/tests/test_sqlite_version_floor.py` (>= 3.30) に、8 は対象外 | 「裁定」節、`cb64217` |
| 遡及拒否の列挙 | main の Revision note 3 の方針に従い旧い遡及行を触らない (実装担当の機械的な拡張を戻した)。1.10.0 段落は自身の遡及文を持つ | 「裁定」節、`285cfe4` |
| 台帳 §0.1.2 の C-30 | 「要求を作る」「判定を受ける」の 2 段 (作業指示書の「SI の段」は軸の取り違え) | `5d988c6`、台帳 v1.121 |
| R-111 の併記撤回 | C-30 直列実行時の資源枯渇は main `f522610` 取り込み後の直列の再実測 (90 passed) で再現しないため R-111 から外した | 台帳 R-111 行、設計 §11 |
| `tools/tests` の pin 9 件 | 両 peer の `paging.py`・keyset 述語・`MAX_CURSOR_OFFSET` 削除が静的インベントリの pin に未反映で赤。どの WP の触ってよいパスにも root gate にも無かった。WP-6 で追随 (規則は緩めない) | `5d988c6` |
| 検査器 2 本の Known gaps | `tools/public_value_scan.py` と `tools/check_comment_provenance.py` は REPO_ROOT が道具自身の置き場 — worktree は worktree 側の copy で回す (§1.12 の 71 の 3 行形式) | `5d988c6`、`tools/dev/README.md` |

1〜2 つ目のチャット (2026-09-24/25) で決めたもの (前の版の本書のまま。番号は振り直し前の仮番号):

| 件 | 結果 | 記録 |
|---|---|---|
| 規模・クラス | 規模 L、**Class D** (着手指示は C だが `security/CONTROL_MAPPING.md` の Evidence 追加と `_ISOMORPHIC_TARGETS` 集合の増加は §9 の 8 で D。レビュー担当も D が正しいと判定) | 設計 §8 |
| 台帳 ID | R-106 (仮。R-105 まで使用済み。merge 直前に振り直す)。付随の起票 R-107 (仮): `order_by` 未知 field の拒否コードが r2db (NOT_FOUND) と MitateDB (VALIDATION_FAILED) で不一致、規模 S、Class C、本変更セットでは台帳行の追加のみ | 設計 §9・§10 |
| Q-1 (依頼者裁定) | 「D-2 (保存形の変更、保証は完全)で。」— MitateDB の全 collection table に隠し行順序列を足し、既存 application DB は R-45 の upgrade 経路で移行。代替 (order key + 同値群内 offset / ctid / 全列・hash / 一意 field 要求 / サーバ側 cursor / 非対応) は却下の記録として設計 §4 に残す | 設計 §5、`frame-keyset.md` §5 |
| Q-2 (依頼者裁定) | **A**: cursor の束縛は Application・entity・`where`・`order_by` のみ。「select/size の変更は取り違えではなく正当な意図でありうるなら束縛してはいけないように思う」。r2db が select/size を束縛していたのは `R2DB_CCR13_STORAGE_V1.md`:243 の訂正 m-3 の網が広かっただけで固有の理由は無い | 同上 |
| 監督裁定 (起草者の疑義 9 件) | C-28 (v) は同一 Application の別 credential で観測 (+ 決定性の観測 (viii))、MitateDB 両 backend に NULLS 句を明示、`validate_page_size` の details 是正を WP-5 に含める、他は観察・開示 | `rulings-draft-v01.md` |
| モデル選択 | 依頼者指示「Opus 役は Opus 5.5 (`claude-opus-5-5`)」。1 つ目のチャットの実測: `opus` 別名は `claude-opus-5` に解決。**2 つ目のチャット (2026-09-24) の実測: 役割定義は `model: opus` のまま、drafter の transcript の `"model"` 欄は 9/9 件 `claude-opus-5-5`** — 別名の解決はチャットごとに違いうる。毎チャットの最初の Opus 起動で transcript の `"model"` 欄 (`grep -o '"model":"[^"]*"' <task>.output`) を見て依頼者に報告する。自己申告は当てにならない | メモリ `opus-alias-is-opus-5-5` |
| 設計レビュー 1 の裁定 (2 つ目のチャット) | 18 件を裁定: **直す 17 件、観察 1 件 (#16 SQLite rowid の再利用 → §10 に開示、`AUTOINCREMENT` は採らない)**。監督の形で決めたもの: #4 版ゲートは (ii) 同時挿入判別 node だけ `xfail(strict=True)`、他 8 node は `< 1.9.0` で non-strict xfail、C-28 は 9 node; #9 `page.size` 省略時の既定 = その要求が運べる最大 (1000・宣言 `result_items`・`budget.result_items` の最小) を契約に置き義務 (7) とする (Q-3 に含む); #12 `page.size` 0 / 1001 は両 peer で `VALIDATION_FAILED` / `request_schema` / `page/size` (MitateDB は契約上限を検査していなかった。r2db 既存テスト 4 箇所を更新); #6 契約 C-6 は変えず観測を「既出行ちょうど 1 回 + 前に挿入した行は返らない」に絞る | `rulings-review1.md`、設計 v0.3、本書「裁定」節 |
| v0.3 起草担当の疑義 7 件 | 裁定済み (直す 4、採用 3)。**v0.4 で反映する** — 最大のものは「select 未指定の走査は契約上送れない (`select` は required + `minItems: 1`)」→ #18 の観測を「select = 宣言 field 全部 → key 集合が完全一致」に置き換える | `rulings-drafter-v03.md` |

## 3. 次の一手

WP-7 の後の手順 (作業指示書 §1.1 の 4、§8):

1. (済) 完了ゲート (`tools/dev/gate.py`、root から worktree を `-C` で指定、1 回): `gate: 4168 passed, 2 subtests passed in 327.60s (0:05:27), judge=PASS, pg_database/pg_roles diff 0, label p11b (final tree; the first gate on ff6ad67, label p11, was 4167 passed in 327.83s, judge=PASS, before the SQLite tampered-cursor test was added)`
2. (済) 受け入れ監査 (evidence-auditor、全 WP、作業指示書の完了条件ごと)。裁定は「裁定」節の末尾。
3. (済) Q-4 の依頼者確認 (§4)。
4. (済) `tools/dev/finalize.py --tools-tests` で main へ 1 回 merge: `本書を含む閉止の変更セットを `finalize.py --tools-tests` で main `b283f48` へ no-ff で merge (branch HEAD の次の main の merge commit。依頼者裁定 Q-4 了承 2026-09-25)`。
5. (済) 本書を最終状態に確定し、main 由来の `HANDOVER_20260924_FABLE7.md` を `docs/archive/docs/work-orders/` へ回転 (§1.16 の 78。`docs/work-orders/` には本書と `HANDOVER_20260925_FABLE.md` の 2 通)。

merge 後の残件:

- **R-110** (`order_by` 未知 field の拒否コードが両 peer で不一致。規模 S、Class C): 未着手。契約の文を先に決める。
- **R-111** (`test_c27_same_digest_executes_once[MitateDB-api-http]` の断続的な赤。規模 M): 未着手。
- **CI の sqlite 版の実測**: push 再開後。pin テストは `MitateDB-api/tests/test_sqlite_version_floor.py` (>= 3.30。NULLS FIRST/LAST)。
- **レビュー観察** (起票しない。「裁定」節): cursor 付き要求 1 回ごとに catalog を 2 回余分に読む (WP-7 で見る) / `tools/contract_catalog.py --help` が書き込む (内容は不変。道具の Known gaps 候補)。
- **push は停止中** (GitHub 課金上限)。

## 4. 依頼者判断待ち・未決

- **Q-4** (main への 1 回の merge の直前の確認。監督が完了ゲートの集計行と `git diff --stat` を添えて提示): **裁定済み 2026-09-25 (逐語)**: 「Q-4 了承」— 完了ゲート `4168 passed / judge=PASS` (label p11b) と main `b283f48` に対する diff の stat (85 files, +5884 / −452)、R-111 を抱えたまま merge する旨を添えて提示した形で了承
- (裁定済み 2026-09-24) Q-3 / Q-5 / Q-4 の形 — §2 の 1〜2 つ目のチャットの行と「裁定」節を見よ。
- 役割定義の `model:` の変更は不要 (`opus` 別名は 2 つ目・3 つ目のチャットで `claude-opus-5-5` に解決)。毎チャットの最初の Opus 起動で実測を報告する。

## 5. 本チャットで足した運用上の教訓

1. **並走する 2 チャットの仮番号は両方が同じ番号を使う。** merge 直前ではなく「main が進んだと分かった時点」で main を取り込み、番号を振り直す (本件は WP-6 の前に取り込み、WP-6 を確定番号で書いた)。
2. **検査器は自身の置き場を REPO_ROOT にする** (`tools/check_comment_provenance.py`・`tools/public_value_scan.py`・`tools/perf_baseline.py`・`tools/check_doc_refs.py`)。root の copy に worktree のパスを渡すと main を検査する — worktree は worktree 側の copy で回す。
3. **`tools/dev/mutate.py` の `-x` と xdist (`-n`) の相互作用で error(2) になる。** 変異は単一 node id・非並列で回す。
4. **同日の引き継ぎ書名は衝突する。** 命名の前に main の `docs/work-orders/` を読む。
5. **manifest の触ってよいパスに `tools/tests` の pin と runbook を列挙する。** root gate は `tools/tests` を回さず、どの WP のパスにも無い pin (本件 9 件) は WP-6 まで見つからなかった。
6. **部分集合の flake は原因を診断してから起票する。** r2db http adapter の孤立化 copy が共有 control client を閉じる既存欠陥 (main `f522610` で修正済み) が、item 配分の変化で C-30 の node に露出した例 (探索担当の診断で確定し、取り込みで解消。起票しなかった)。

1〜2 つ目のチャットの教訓 (前の版の本書のまま):

7. **サブエージェントのモデルは transcript の `"model"` 欄で確かめる。** 自己申告 (「Opus 5 (1M)」等) は frontmatter の値に関わらず同じ文を返した。
8. **役割定義の frontmatter はチャット開始後に変えても効かない** (worktree 側・root 側とも)。Agent ツールの `model` 引数は効く (haiku で実測) が別名 4 つのみ。
9. **worktree には `.venv` が無い。** 道具は `./.venv/bin/python tools/dev/<tool>.py -C <worktree>` を root から、または リポジトリ root の `.venv/bin/python` を絶対パスで (文書には相対表記だけ書く)。
10. **Mitate の要件 §3/§12 (f)/D4 は「cursor 走査で完全性を証明したい」であり、順序は Mitate 自身の typed field (`seq`) で指定している。** data-service-api 側に `seq` の実体は無い (探索の取り違えに注意)。
11. **MitateDB は PostgreSQL の collection table に内部 id 列を持たず `ctid` は不安定。** keyset の tie-break には保存形の変更が要る (Q-1)。
12. **`page.size` 省略時の挙動は両 peer で割れていた** (r2db 既定 100 + `next_page`、MitateDB は `effective max_result_rows` で黙って切り詰め `next_page` 常に null)。1.8.0 では `next_page` に意味が無いので違反ではなかったが、1.9.0 で「null = 末尾」を約束すると同じ要求の完全性判定が割れる — 契約に既定を置く (裁定 #9)。
13. **MitateDB は契約 schema の `Page.size` 上限 1000 を検査していない** (`_check_object_shape` は `minimum`/`maximum` を見ない)。`max_result_rows ≥ 1001` の配備では 1001 が無検査で通る (裁定 #12)。
14. **`opus` 別名の解決はチャットごとに違いうる** (同日に `claude-opus-5` と `claude-opus-5-5` の両方を実測)。

## 裁定

全件を載せる (`docs/work-orders/OPERATING_CONDITIONS.md` §1.15 の 77)。1〜2 つ目のチャットの行は前の版の本書のまま残す (番号は振り直し前の仮番号。「未裁定」の行は本チャットの行で裁定した)。本チャットの行は「WP-4 実装担当の逸脱 1」以降で、出所は監督チャットの scratchpad の `rulings-wp4.md` (WP-4 実装報告への裁定)・`rulings-wp4-review.md` (WP-4 コードレビューと再実測)・`rulings-wpm.md` (main 取り込みのレビュー)・`rulings-wp6.md` (WP-6 のレビューと実装報告) の逐語である。`rulings-wp4.md` の逸脱 1〜7 は `rulings-wp4-review.md` の表が同じ裁定を結果込みで再掲しているので後者を載せ、前者からは逸脱 8 と疑義 1〜3 の行だけを足した。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草担当の疑義 1〜9 (v0.1) | 直した (v0.2 に反映済み) / #4 は起票 (仮 R-107) / #6・#9 は観察 (開示) | `rulings-draft-v01.md` |
| レビュー 1-1 「発行していない cursor」は検査不能 | 直した (v0.3) | 拒否条件を 復号不能 / 個数・型不一致 / 束縛違い の 3 つに絞り、C-3 に署名なしの開示 |
| レビュー 1-2 順序項が select に無いと cursor を作れない | 直した (v0.3) | 内部射影に足して応答前に落とす。観測を C-28 (i) に追加 |
| レビュー 1-3 復号値の個数・型検査が無い | 直した (v0.3) | 述語を組む前に検査、外れは C-5 の拒否。SQLite / in-memory でも Python 側で同じ検査 |
| レビュー 1-4 strict xfail が現行 r2db と衝突 | 直した (v0.3、監督の形) | (ii) node だけ strict、他は non-strict。9 node に分割 |
| レビュー 1-5 「neither names nor observes」は偽 | 直した (v0.3) | 「receives as a field of an item」に替え hazard 文を足す |
| レビュー 1-6 C-28 (ii) が契約より強い | 直した (v0.3、(a)) | 契約は変えず観測を「既出行ちょうど 1 回 + 前に挿入した行は返らない」に絞る |
| レビュー 1-7 SI-08 無状態性は反証不能 | 直した (v0.3) | 主張を「session・connection・credential に紐づかない、nonce・時刻・連番を含まない」に縮め、残りは Status の開示 |
| レビュー 1-8 C-3 の性能文 | 直した (v0.3) | 1 文を削り D-7 の計測記録へ |
| レビュー 1-9 `page.size` 省略時の幅が両 peer で割れる | 直した (v0.3、監督の形) | 既定 = その要求が運べる最大を契約に置く (義務 (7)。Q-3 に含む)。観測は `budget.result_items` で既定を小さくする |
| レビュー 1-10 typed 列のバインド | 直した (v0.3) | 既存の `_bind_value` を通す |
| レビュー 1-11 件数ピン改名と comment | 直した (v0.3) | D-6 に 2 項 |
| レビュー 1-12 `validate_page_size` 是正の乗り合い | 直した (v0.3、(b)) | Revision note + C-28 の node (0 / 1001、6 plug)。MitateDB 側も是正 |
| レビュー 1-13 「1.8.0 で有効な要求は有効のまま」は偽 | 直した (v0.3) | 「形の上で有効」に狭め、§10 に限界を追加 |
| レビュー 1-14 挿入位置の曖昧さ | 直した (v0.3) | 1.7.0 の遡及文の直後、version-flip 文の直前 |
| レビュー 1-15 `maxLength` 除去の記録 | 直した (v0.3) | CONTRACT_HISTORY の Revision note |
| レビュー 1-16 SQLite rowid の再利用 | **観察** (§10 に開示) | 契約は tie-break の中身を約束しない。`AUTOINCREMENT` は採らない (形を増やさない) |
| レビュー 1-17 cursor が監査 event に載らない明示 | 直した (v0.3) | §7 SI-10 行 + CONTROL_MAPPING Status |
| レビュー 1-18 除外点が 1 箇所ではない | 直した (v0.3) | cell 側 helper 1 本に 6 箇所を通す。6 箇所目は :3424 |
| 起草担当の疑義 1〜7 (v0.3) | 裁定済み、**v0.4 で反映** (直す 4、採用 3) | `rulings-drafter-v03.md` |
| レビュー 2-1 版ゲートが完了ゲート (xfailed / xpassed = 0) と衝突 | 直した (v0.4、統合 branch) | 全 WP を worktree branch に積み main への merge は WP-7 後の 1 回。中間は `finalize.py --no-merge`、期待結果表で判定 |
| レビュー 2-2 C-6「移動した行は once or not at all」は keyset で偽 | 直した (v0.4) | 順序項が変わった行は 2・1・0 回のいずれも。§10 に消費者向け開示 |
| レビュー 2-3 r2db の tie-break `id` は宣言 field | 直した (v0.4) | 契約は tie-break を名指さない形に。宣言 field でない tie-break だけ非可視 |
| レビュー 2-4 MitateDB の page.size 検査位置と cell の next_page | 直した (v0.4) | 検査は `ApplicationCell.read`、cursor 読みは `(rows, next_page)` の新 cell メソッド |
| レビュー 2-5 port `query_page` に budget が無い | 直した (v0.4) | keyword-only `budget` を追加、`request_budget` 宣言で分岐 |
| レビュー 2-6 既定ページ文の二義 | 直した (v0.4) | 「as though it carried the page.size equal to the least of …」、obligation 名から could/may carry を外す |
| レビュー 2-7 cursor を運ぶ要求がどの行を返すかが無い | 直した (v0.4) | C-3 と A (3) に「その位置に続く行を返す」 |
| レビュー 2-8 CONTROL_MAPPING 案 3 件 (長さ / path / 真偽) | 直した (v0.4) | recorded binding の形、300 文字以内、backtick path |
| レビュー 2-9 「issued under」は改変 token で検出不能、C-4 と C-5 の矛盾 | 直した (v0.4) | recorded binding の語、C-4 は「他は refusal のとおり拒否」、where は同じ述語を同じ順 |
| レビュー 2-10 observed_branch の突合分岐 | 直した (v0.4) | `>= 1.9.0` の分岐でだけ突合 (フェーズ9 訂正註 7) |
| レビュー 2-11 C-1 の実装任意の範囲 (照合順序・型付き object) | 直した (v0.4) | C-1 最終文を差し替え、D-2a / §10 の「peer 内で順序が 1 つ」を NULL 位置に限定 |
| レビュー 2-12 Condition 文 3 箇所が観測と不一致 | 直した (v0.4) | before … in the order、connection / time の主張を消し Status に開示 |
| レビュー 2-13 WP のファイル列と register の順序 | 直した (v0.4) | CONDITIONS_HISTORY `## C-28` を WP-1、Status executable を WP-2、r2db / MitateDB の既存テストを列挙 |
| レビュー 2-14 復号値の型検査が null を落とす | 直した (v0.4) | `_check_type(..., "page/cursor")`、MitateDB は全 ValidationError を page/cursor に写す |
| レビュー 2-15 migration 0015 の中身 | 直した (v0.4、superset) | `information_schema.tables` から `_mdb_` と `audit_events` を除く、`IF NOT EXISTS`、lock 保持を開示 |
| レビュー 2-16 既定ページ変更の Revision note | 直した (v0.4) | CONTRACT_HISTORY に追記 |
| 起草担当の疑義 1〜4 (v0.4) | 裁定済み (直す 1 = 並走しない・全 WP 直列、採用 3) | `rulings-drafter-v04.md` |
| Q-3 / Q-5 / Q-4 (依頼者裁定 2026-09-24、逐語) | 「Q-3 は見直し 1 点を含めて確定、Q-5 は (a)、Q-4 はその形で。」— 見直し 1 点 = 監督提示の「where 述語の並びに依らない束縛 (正規化 hash、契約は the same where predicates, in any order)」。Q-5 (a) = `Page.cursor` の `maxLength` を外す。Q-4 = main への 1 回の merge 直前に完了ゲート集計行と差分の stat を添えて確認 | 設計 v0.6 §5.1、確定文 `$SP/verbatim-190.md` (scratchpad。次チャットへは `.handover-materials/` で写す) |
| 設計 v0.6 / 作業指示書 v1.2 起草担当の疑義 (a)〜(d) | 採用 2、観察 1 ((b) 述語の重複は多重集合として束縛 → §10 開示)、直す 1 ((d) 従属判断 14 は Q-1/Q-2/Q-3/Q-5 の 4 件) | `rulings-drafter-v06.md` |
| コードレビュー WP-1-1 C-27 MitateDB-http 413 が `-k "not r2db"` の直列実行で再現 (別チャットでも同時刻に再現) | **観察** (暫定。完了ゲートは `-n 5` で緑、利用者は気づかない。部分集合の実行に `-n 5 --dist loadgroup` を付けて再計測し、消えなければ WP-2 以降の実行でも記録する) | 制御面の `control_requests_per_minute` に直列実行の密度で掛かる仮説 (A)。WP-1 の差分は MitateDB 側では同梱 copy のみ |
| コードレビュー WP-1-2 §11 の記録が中間状態の計測 | 直した (再計測) | ピン 2 関数の一時消失中の数値だった |
| コードレビュー WP-1-3 Revision note 4 が r2db の旧拒否を誤記 | 直した | 0 以下は LIMIT_EXCEEDED、1001 は budget/page_size |
| コードレビュー WP-1-4 version_binding ピンが A の末尾文を持たない | 直した (全文 + 隣接の等号、変異 M1-2b) | 非空振り要件 |
| コードレビュー WP-1-5 遡及列挙文の serial comma | 採用 (実装担当の形。既存列挙と `654e23e` に一致) | 設計 D-1 (A) の註は次の設計改版で追随 |
| コードレビュー WP-1-6 Revision note の ID に文書名が無い | 直した | OC §1.8 の 59 |
| コードレビュー WP-1-7 test_contract.py の履歴コメント未更新 | 直した | — |
| コードレビュー WP-1 註 register 3 件は部分実行の性質 / C-28 は別チャットの `test_c28_baseline_turn.py` と衝突見込み | 観察 / 予定どおり merge 直前に振り直す | 作業指示書 WP-1 の道具の引数の行は次の改版で `test_conditions_register.py` を部分集合側へ |
| コードレビュー WP-2-1 I node が続きを page_size=100 で読み、フリップ下の現行 r2db で shape 拒否に止まる | 直した (page_size=2) | 判別 assert に到達させる |
| コードレビュー WP-2-2 R node の個数・型の脚が束縛違いと区別不能 (空振り) | 直した (裁定 (a)) | conformance は改変 token を作れない (opaque)。個数・型検査の証拠は peer 単体テスト (WP-4 / WP-5)、C-28 Status に開示。(b) の drop_entity 経路は r2db 限定なので採らない |
| コードレビュー WP-2-3 S / B の select 脚が page.size も変えていた、§11 の原因記述の取り違え | 直した | A の x は現行 r2db の `field: cursor` による |
| コードレビュー WP-2-4 comment provenance 赤 15 件 (経緯語 WP-n、CH-0210 の言い換え、理由の塊の消失) | 直した | `docs/code-history/` は触らない |
| コードレビュー WP-2-5 報告と周辺記述のずれ | 直した | — |
| WP-2 残: `check_comment_provenance --base` の §4.1 (2) 1 件 (post_query から cell.read_page docstring へ跨ぎ移動した理由の塊。CH-0542 の登録を試すと移動先で別の赤) | **観察** (検査器の穴の候補: `--base` はファイル跨ぎの moved-from を検証できない。§1.12 の 71 の 1 問 = 製品欠陥は通らない → 検査器 docstring の Known gaps 行を後日) | CI も pre-commit も provenance を回さない。塊は逐語で移してある |
| WP-1/2/5 の部分集合実行で C-27 `test_c27_same_digest_executes_once[MitateDB-api-http]` が断続的に赤 (直列で 413 LIMIT_EXCEEDED、`-n 5` でも 3 回中 2 回 AUTH_INVALID。単独では緑。別チャットの直列全体実行でも再現) | **起票候補 (WP-6 の台帳更新で、R-107 の次の番号で起票)**: 利用者は気づかないが完了ゲート (`RM` §0.1 の終了条件) を赤にしうる。原因は MitateDB http adapter の credential repair (reset → rotate) が制御面の rate limit / 認証窓に掛かる仮説。本変更セットでは直さない | 起票の 2 問: (a) 検査器の穴ではない、(b) 終了条件を破りうる → 起票 |
| コードレビュー WP-5-1 `--register` 赤 (CH-0024 orphan、CH-0026 / CH-0135 の無記録の書き換え) | 直した (correction 節。§4.1 (2) の 12 件は code change set として観察) | `gate.py` は tools/tests を回さないので finalize `--tools-tests` で拾う |
| コードレビュー WP-5-2 改変 cursor (巨大整数・lone surrogate) が PostgreSQL cell で 503 | 直した (共有層 `_check_type` の定義域検査。where 側も同時に 2 キー拒否へ) | HEAD から where にもあった欠陥。MitateDB は `encode_value` で既に拒否 → peer 揃え |
| コードレビュー WP-5-3 tie-break の方向を固定するテストが無い (同値群がページ境界をまたがない seed) | 直した (単体テスト 2 本 + C-28 T の同値群変種) | WP-4 の M4-3 の空振りも防ぐ |
| コードレビュー WP-5-4 `encode_page_cursor` に `sort_keys=True` が無い | 直した | 設計 D-6 のとおり。WP-4 が写す前に確定 |
| コードレビュー WP-5-5 SI-08 の誤帰属 docstring | 直した | 束縛は SI-01 |
| コードレビュー WP-5-6 §11 の数え間違い | 直した | — |
| コードレビュー WP-5-7 経緯 comment と旧名コメント (`http.py:466`) | 直した | — |
| コードレビュー WP-5-8 in-memory cell の `result_items` が cursor 前の行も数える (PostgreSQL と割れ) | 直した (検査を絞り込みの後へ) | offset 時代からの割れ。1.9.0 で到達しやすくなる |
| WP-5 実装担当の棚上げ 1: `test_postgres_data_error_from_an_out_of_range_number_value_is_validation_failed` の旧 trigger (backend 層の data error → no-details 拒否) が定義域検査の前置で未到達に | **観察**: backend 層の写像は多層防御として残す。旧完了条件のピンは新しい拒否経路 (request_schema) の assert に改めた | 到達する別 vector があれば後日追加 |
| WP-5 実装担当の棚上げ 2: C-28 を直列・並列指定なしで回すと node 数 84 で httpx client の資源枯渇により無関係な node が赤化 (`-n 2` 以上では非発現) | **観察** (上の C-27 の起票候補と同じ行に「conformance http adapter の密な実行での資源枯渇」として併記) | 完了ゲートは `-n 5`。実装担当は C-28 単独を `-n 2` で回す |
| WP-3 実装担当: migration 0015 の追加で集合 / 行番号ピン 31 件 (4 ファイル) が赤 | 直した (現在の集合のピンの追随。R-45 と同じ扱い) | 設計 §9 の「触るファイル」列は既存のピン付きテストへの波及を書いていない — 次回の manifest は `tests/` のピンを列挙する (教訓) |
| WP-3 実装担当: `tools/public_value_scan.py` は相対パスだと main checkout 基準で worktree の変更を見落とす | **既知の穴 (§1.12 の 71: 製品欠陥は通らないが、公開値の見落としは通りうる → 起票候補と同列に扱い、WP-6 で検査器 docstring の Known gaps に 3 行)** | finalize.py は staged path を絶対で渡すので commit 経路は影響なし |
| WP-3 実装担当: `public_value_scan.py` の `R3_project_id` が `mutate-20260925-NNNNNN` 形式のログ名に偽陽性 (設計 §11 に書いたログパス) | 観察 (メモリの既知事項と同種: pt / mutate のログ名を文書に書かない。ログパスは削除して解消) | 検査器の Known gaps 候補 (WP-6 で同じ docstring に併記) |
| コードレビュー WP-3-1 完了条件 3 の PostgreSQL 側が helper の除外に反応しない (select-all を見ていない) | 直した (select-all の assert、M3-3a/3b) | — |
| コードレビュー WP-3-2 README の lock 開示が 1 transaction の事実に反する | 直した | COMMIT まで保持、Application 全体のデータ量に比例 |
| コードレビュー WP-3-3 経緯語と出所の無い ID | 直した | — |
| コードレビュー WP-3-4 CONTROL_MAPPING の行番号参照 2 箇所がずれた | 直す (WP-6 の 3.2 で) | Class D の経路 |
| コードレビュー WP-3-5 runbook の rollback 互換表に 0015 が無い (設計の抜け) | 直した (WP-3 で行を追加。0015 後の旧 revision は非互換 — 旧コードは `_mdb_row` を宣言 field として扱う) | 設計 §9 の触るファイルに runbook を書いていなかった (教訓) |
| コードレビュー WP-3-6 実装担当が変異を手編集で行った (残留なし) | 観察 (§11 から手動の数値を消す。以後 mutate.py のみ) | OC §1.4 の 29〜31 |
| コードレビュー WP-3-7 主張の文言が実測と合わない 3 箇所 | 直した | — |
| WP-4 実装担当の逸脱 8 件・疑義 3 件 (未レビュー) | **未裁定 — 次チャットの監督がコードレビューの前に裁定する** (暫定見解は `.handover-materials/wp4-report.md` 末尾: 逸脱 2・3・5 は採用見込み、**逸脱 4 (孤立化 fixture の bound 5→100 / 50→150) は差し戻し見込み** — C-28 側が宣言 bound を読むべき) | チャット中断のため |
| 作業指示書 v1.0 起草担当の疑義 1〜7 | 裁定済み (直す 5、採用 2)、設計 v0.5 / 作業指示書 v1.1 で反映 | `rulings-wo-v1.md`: control_plane と 1.8.0 pin テストを WP-6 に、R-107 行を WP-1 に、Revision note 3 本は既存 `## versioning.version_binding` 節に、MitateDB cell の cursor 入口を WP-2 で (WP-4 まで CAPABILITY_UNSUPPORTED)、conformance 全体は前景 1 回に収まらない (606 s) |
| 設計 v0.5 / 作業指示書 v1.1 起草担当の疑義 1〜4 | 裁定済み (直す 3、採用 1) | OC §1.5 の 39 は変えない (実装担当は peer ごとの部分集合を前景で、全体は監督のゲートのみ)、1.8.0 pin 3 箇所を WP-6 に、cursor 入口は `ApplicationRuntime` (実体は `ApplicationCell`)、L1 件数ピンの条件付き追加は可 |
| WP-4 実装担当の逸脱 1 (backend.read の cursor_values kwarg) | 採用 | 実装詳細 |
| 逸脱 2 (read → read_page 委譲、page.size 検査を共有コアに) | 採用。設計 §11 に D-2b の 2 への訂正註 | 単一 choke point |
| 逸脱 3 (cursor 検証を配備 bound より先) | 採用。設計 §11 に訂正註 | 要求の形の検査は資源の検査より先 |
| 逸脱 4 (孤立化 fixture 5→100 / 50→150) | 差し戻し (直した): C-28 側の継続要求 5 箇所を発行時と同じ page_size (2 / 1) に監督が修正、fixture は 5 / 50 | 差し戻し 1・2 の裁定と同じ形。page.size 非束縛の観測は既存の page_size=1 の脚が担う |
| 逸脱 5 (count() を keyset 走査に) | 採用 (直した: 1 行 1 要求 → 既定ページ走査 + ページ数ガード) | 単一 read の黙った切り詰めは adapter の実バグ |
| 逸脱 6 (C-27 MitateDB-http flake 3/3) | fixture 復元後 2 回中 1 回。WP-6 で起票 (R-111) | 完了ゲートを赤にしうる |
| 逸脱 7 (CI の sqlite 版未確認) | 直した: 完了条件 19 を pin テスト `MitateDB-api/tests/test_sqlite_version_floor.py` (>= 3.30) に。CI runner の実測は push 再開後 (未決) | 手元で確認不能 |
| 逸脱 8 | 対象外 | `rulings-wp4.md` |
| 疑義 1 (D-2b の 2 の file:line 陳腐化) / 疑義 2 / 疑義 3 | 疑義 1 → 逸脱 2 の訂正註。疑義 2 → 逸脱 3。疑義 3 → 逸脱 4 (値の調整ではなく C-28 側を直す) | `rulings-wp4.md` |
| レビュー WP-4-1 count() 1 行 1 要求で fixture 復元後 C-23 が rate limit で赤 | 直した (既定ページ走査) | RV-1 で実測 |
| レビュー WP-4-2 desc の NULL 分岐を観測するテストが無い | 直した (C-28 T に `null_valued_field_desc` 変種、7 変種。M4-5b / M4-5c 赤) | 退行が入れば行の欠落として利用者が気づく |
| レビュー WP-4-3 SQLite NULLS 句 comment が未実施の CI 実測を主張 | 直した | OC §1.5 の 34 |
| レビュー WP-4-4 `_mdb_row` の cursor 値を Python 側で型検査していない | 直した (`check_declared_value(value, "integer")` + tamper 脚) | D-2b の 1 |
| レビュー WP-4-5 read → read_page の移動で経緯 comment が落ちた | 直した (逐語で移送) | OC §1.5 の 40c |
| レビュー観察: cursor 付き要求 1 回ごとに catalog を 2 回余分に読む (cell.py の復号検査) | **観察** (WP-7 の性能計測で見る。利用者は気づかない、終了条件を破らない) | 起票の 2 問とも いいえ |
| 再実測で発見: `test_c28_page_size_outside_schema_is_refused_at_page_size[r2db-api-http]` が `-n 5 --dist loadgroup` で closed-client RuntimeError (3/3) | **直した (main の取り込みで)**: 原因は r2db http adapter の孤立化 copy が親の共有 control client を rebuild して閉じる既存バグ。main f522610 (R-29 WP-3) が iso の control send を親に束縛して修正済み | 探索担当の診断 `explore-ps-flake.md` |
| 再実測: comment provenance 検査器は自身の置き場 (root checkout) を REPO_ROOT にするため、root の copy で worktree のパスを渡すと main を検査する | **既知の穴** (§1.12 の 71: 製品欠陥は通らない): WP-6 で `tools/check_comment_provenance.py` の docstring Known gaps に 1 行 (worktree は worktree 側の copy で回す)。`public_value_scan.py` の同種の穴と同列 | 実装担当・レビュー担当の provenance 実測は main を見ていた。監督が worktree の copy で再実測: 履歴語 2 件 (直した)、他は関数跨ぎ移動の (2) (WP-2 と同じ観察) |
| 変異 M4-x を `-k` + `-n 2` で回すと mutate.py の -x と xdist の相互作用で error(2) | 観察 (単一 node id・非並列で回す。memory の mutate -x pitfall と同種) | — |
| main 取り込み 実装担当の判断 (a) 遡及拒否の列挙を main の 1.9.0 末尾文まで機械的に拡張 | **据え置き (直した = 拡張を戻した)** | main の Revision note 3 (旧い遡及行は一字も触らない) が新しい前例。依頼者確定の 1.9.0 段落を変えない。1.10.0 段落は自身の遡及文を持つ |
| 判断 (b) 1.10.0 段落の前版参照を 1.8.0 → 1.9.0 | 採用 | 1.10.0 の前版は 1.9.0。数字のみの置換 (Q-4 で依頼者に見せる) |
| 判断 (c) 1.8.0 entry の検査は main の index 固定形 | 採用 | — |
| 判断 (d) C-29 declared_version が 6 plug で赤 (catalog 1.10.0 vs 宣言 1.9.0) | 期待どおりの中間状態 (WP-6 の版フリップで消える) | 統合 branch |
| 判断 (e) port 文書に v1.18 の節が無い | 直した (版数行 1.18 + §28 v1.18 の節) | main の v1.16 / v1.17 の前例 |
| 判断 (f) 台帳の「30 件全件が executable」 | WP-6 で §0.1.1 を 31 件に | — |
| 判断 (g) `---` 区切りの流儀 | 採用 | — |
| レビュー WP-M-1 test_c30 が未追跡・旧ファイル削除が未 stage | 直した (finalize.py が porcelain から両方を stage、rename として記録) | — |
| レビュー WP-M-2 (a) が note 3 と逆 | 直した (据え置き) | 上 |
| レビュー WP-M-3 Revision note 4 の記述が実測と不一致 | 直した (note 4 を書き直し) | — |
| レビュー WP-M-4 1.10.0 entry の pin が obligations[-1] | 直した (index [8] + version assert) | main の §15 裁定 2 の形 |
| レビュー WP-M-5 CONFORMANCE_ADAPTER_V1 の版数行 | 直した | 上 (e) |
| レビュー WP-M-6 docs/work-orders に引き継ぎ書が 3 通 | 引き継ぎ書の変更セットで main 由来の FABLE7 を archive へ (§1.16 の 78) | 最新 2 通 = FABLE (main、R-29) と FABLE2 (本件) |
| レビュー WP-M-7 (観察) main の 1.9.0 が structured_query を unavailable にすることを禁じるので 1.10.0 の条件付き義務は常に条件成立 | **観察** (確定文どおり。変えるなら依頼者判断) | 利用者は気づかない、終了条件を破らない |
| レビュー担当の過失: `tools/contract_catalog.py --help` が書き込む (sha256 不変) | 観察 → 道具の Known gaps 候補 (後日) | 内容は不変 |
| WP-6 実装担当の逸脱 1: SI-10 Evidence を設計案 (個数・型不一致を含む) から実際の R node の観測 (malformed / foreign / 束縛違い) に合わせ、個数・型は peer 単体テストへ | 採用 | 実測後に書く (OC §1.5 の 34)。WP-2 の裁定 (a) と整合 |
| 逸脱 2: 件数ピン改名で dangling になった SI-08 Evidence 行の追随 | 採用 | — |
| 逸脱 3: `tools/tests` 9 件が赤 (両 peer の `paging.py`・keyset 述語・`MAX_CURSOR_OFFSET` 削除が静的インベントリ pin に未反映) | 直した (本変更セットで pin を追随。規則は緩めない; SQL scan は規則遵守の根拠付きで登録) | root gate は tools/tests を回さない (memory: gate-chain-exit-masking)。教訓: manifest は tools/tests の pin を列挙する |
| 疑義: §0.1.2 の C-30 の段 | 「要求を作る」+「判定を受ける」の 2 段 (作業指示書の「SI の段」は軸の取り違え) | §0.1.2 の軸は周回の段 |
| レビュー WP-6-1 C-30 Status に §10 の 6 の開示が無い (「編集不要」は誤り) | 直した | 完了条件 7 |
| WP-6-2 §0.1.2 が「catalog を読む」段のまま (同文 3 箇所) | 直した | 上 |
| WP-6-3 SI-10 Control の MitateDB 側 path が paging.py (拒否は cell.py) | 直した | 監査者が制御を辿れる |
| WP-6-4 MitateDB の宣言 comment「structured_query stays enabled」(実際は partial) | 直した (code-history も) | 主張 vs 実測 |
| WP-6-5 CONDITIONS_HISTORY「1.9.0 at that point」(a2ba943 時点は 1.8.0) | 直した | — |
| WP-6-6 R-111 の併記 (C-30 直列の資源枯渇) の plug 名なし・断定・node 数 | 実測で決める (直列 1 回。緑なら併記を外し §11 に記録、赤なら plug 名と推定を明記) | main f522610 が同 adapter の closed-client を直した |
| WP-6-7 Known gaps が 3 行形式でない、README 索引の件数 | 直した (tools/dev/README.md を触ってよいパスに追加) | OC §1.12 の 71 |
| WP-6-8 SI-09 の行参照 5 件の付け替え先 | main が指していた `def delete` の現在位置に (内容変更は範囲外) | Class D の claim 内容は変えない |
| WP-6-9 軽微 (R-109 の WP 注記、Version 行の件数、SI-08 Status の文、§11 WP-5 記録のキリル文字) | 直した | — |
| レビュー WP-4 観察の再掲: mutate.py の `-x` と xdist | 観察 | memory mutate-x-flag-pitfall |
| 受け入れ監査 未充足 WP-3 の 4・9・11 (監査照合の逐語記録が設計 §11 に無い) | 直した (§11 WP-3 記録に grep 出力 / README の開示 2 点 / -rxX 実測を追記) | §1.7。中身は満たしていた |
| 監査 未充足 WP-4 の 21 (当時 PS[r2db-api-http] が赤) | 直した (main f522610 の取り込み 285cfe4 で解消。作業指示書 §9 に訂正註) | — |
| 監査 未充足 WP-6 の 10 (部分集合 "not r2db" で C-27 MitateDB-http が赤) | **起票済み R-111** (頻度を追記: 監査の再実測 2/2、完了ゲートの全体実行は緑)。R-111 を抱えたまま merge (Q-4 で依頼者に明示) | 完了ゲートは緑、利用者は気づかない、終了条件を破りうる → 起票 |
| 監査 証拠不足 WP-4 の 19 (CI の sqlite 版) | 直した (作業指示書 §9 に訂正註: pin テストに置換、CI runner の実測は push 再開後) | — |
| 監査 観察 1: SQLite の `_mdb_row` 型検査がテストで固定されていない (AU-4 NG) | 直した (`test_row_order_column.py` に SQLite の改変 cursor テスト、AU-4 赤) | 義務 (5)。先送りしない |
| 監査 観察 2: R-111 の頻度が台帳の記録より高い | 直した (R-111 行に追記) | — |
| 監査 観察 3: MitateDB の cursor 付き要求のコストが未計測 | 直した (§11 WP-7 に MitateDB の深いページ比較と cursor 有無の差を追記) | レビュー WP-4 観察の「WP-7 で見る」を実際に見た |
| 監査 観察 4: 記述と実物のずれ 5 件 | 直した | — |
| 監査 疑義: WP-7 の基準値の選択 (§2.3 vs フェーズ9) | 観察 (どちらでも判定は変わらない。§11 に両論を記録済み) | — |
| 監査 疑義: WP-3 の完了条件 4 (2 本目の field_domains 直接呼び出し) | 直した (§11 に理由を記録) | — |
