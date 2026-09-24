# 引き継ぎ — 2026-09-24 (keyset ページング (高速化案 7、フェーズ11) の設計段階。契約は 1.8.0 のまま、未コミット)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `HANDOVER_20260924_FABLE6.md`。本書は依頼者指示 2026-09-24「keyset ページングと R-29 を新しいチャットで開始する」で始まったチャットのもので、**2 つのチャットを経て、依頼者の指示によりチャットを途中で移る** (2 つ目のチャットは設計 v0.3 の起草直後で中断。設計レビュー 2 回目・実装・コミットは未着手)。

## 1. 現在地

- ローカル main は `0fee6e5` (台帳 v1.119)。**本 worktree の branch には WP-1 を `3af11b3`、WP-2 を `a2ba943`、WP-5 を `f3b10ca` として積んだ (main には merge しない。統合 branch、main への merge は WP-7 後の 1 回)。** push 停止中 (課金上限)。
- 本チャットの worktree: `.claude/worktrees/cranky-visvesvaraya-616e67` (branch `claude/cranky-visvesvaraya-616e67`、main と同一 + 未追跡 2 点)。**次のチャットはこの worktree に入って続ける** (新しい worktree を切らない)。
  - 未追跡: `docs/design/PHASE11_KEYSET_PAGING_V1.md` (**設計 v0.5** — 設計レビュー 1 (18 件) と 2 (16 件)、起草担当の疑義への監督裁定を反映済み) と **作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` v1.1** (WP 7 本、直列、統合 branch)。Q-3 / Q-5 / Q-4 は依頼者に提示済み・裁定待ち と本書。設計は単独で commit しない (`check_doc_refs` が C-28 / R-106 / R-107 の dangling で赤。台帳行と `CONDITIONS.md` の C-28 行と同じ変更セットで commit する)。
  - 未追跡・**commit しない**: `.handover-materials/` (前チャットの scratchpad の写し。作業機の絶対パスを含むので公開値スキャンに掛かる。読み終えたら削除してよい): `frame-keyset.md` (枠と裁定 Q-1/Q-2 の逐語)、`rulings-draft-v01.md` (起草者の疑義 9 件への裁定)、`design-review-1.md` (設計レビュー 1 回目、18 件の全文と修正案)、**`rulings-review1.md` (設計レビュー 1 の 18 件への監督裁定。末尾の追記に #9 / #12 の確定形)**、**`rulings-drafter-v03.md` (v0.3 起草担当の疑義 7 件への監督裁定。v0.4 で反映する)**、`verbatim-190-draft.md` (契約 1.9.0 の案文 v0.3 追随済み。依頼者未確定)、探索ノート 4 本 (**`explore-page-defaults.md` は #9 / #12 の実測**)、`mitate-paging-requirements.md` (Mitate 要件の逐語)。
- **逸脱の申告**: `tools/dev/handover_ready.py` は NOT READY (worktree が未コミットで dirty、本書が main に未コミット)。設計文書と本書は `check_doc_refs` の dangling (R-106 / R-107 / C-28) で単独 commit できないため、依頼者指示 (2026-09-24「新しいチャットで再開・継続します」) により **未コミットのまま**移る。次チャットは台帳行と `CONDITIONS.md` の C-28 行を足す変更セットで本書ごと commit する (本書はそのとき §1〜§3 を現在地に合わせて更新し、「裁定」節に設計レビュー 1 の全件を載せる)。
- 並走: R-29 のチャット (worktree `laughing-feistel-31c19a`) が同じ spec / CONDITIONS / 台帳 / CONTROL_MAPPING に触れる。契約版数と C-番号は merge 直前に main を読んで振る (先に merge した側が 1.9.0)。他チャットの worktree に触らない。

## 2. 本チャットで決めたもの

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

## 3. 次の一手 (手順は役割テンプレート 0 のとおり、手順 4 の途中から)

1. **済み**: 設計レビュー 1 の 18 件の裁定 (`rulings-review1.md`)、設計 v0.3 の起草 (drafter)、v0.3 起草担当の疑義 7 件の裁定 (`rulings-drafter-v03.md`)。
2. **設計レビュー 2 回目** (契約変更のため。別起動の reviewer、モード: 設計レビュー、Class D。対象は v0.3 と `verbatim-190-draft.md`。レビュー担当には `rulings-drafter-v03.md` の 7 件が v0.4 で入る旨を渡す)。レビュー 2 の指摘に監督が裁定を付け、`rulings-drafter-v03.md` の 7 件と合わせて drafter に **v0.4** を指示する。
3. 採否: Q-3 (契約 1.9.0 の案文と C-28 の Condition 文の逐語。scratchpad の確定文ファイル `verbatim-190.md` 経由。**義務 (7) 既定ページの文を含む**)、Q-5 (`Page.cursor` の `maxLength` を外す (a) か引き上げる (b) か。案文は (a))、Q-4 (契約版に触れるコミットの事前確認) を両論で提示し確定を待つ。
4. 作業指示書 (Change Set Manifest、設計 §9 の WP-1〜WP-7)、実装ループ、完了ゲート (`tools/dev/gate.py -C <worktree>`)、監査、コミット (`finalize.py --tools-tests`)、引き継ぎ書。

## 4. 依頼者判断待ち・未決

- (裁定済み 2026-09-24) Q-3 / Q-5 / Q-4 — §2 の行を見よ。
- 役割定義の `model:` の変更は不要と分かった (2 つ目のチャットで `opus` 別名が 5.5 に解決)。毎チャットの最初の Opus 起動で実測を報告する。

## 5. 本チャットで足した運用上の教訓

1. **サブエージェントのモデルは transcript の `"model"` 欄で確かめる。** 自己申告 (「Opus 5 (1M)」等) は frontmatter の値に関わらず同じ文を返した。
2. **役割定義の frontmatter はチャット開始後に変えても効かない** (worktree 側・root 側とも)。Agent ツールの `model` 引数は効く (haiku で実測) が別名 4 つのみ。
3. **worktree には `.venv` が無い。** 道具は `./.venv/bin/python tools/dev/<tool>.py -C <worktree>` を root から、または リポジトリ root の `.venv/bin/python` を絶対パスで (文書には相対表記だけ書く)。
4. **Mitate の要件 §3/§12 (f)/D4 は「cursor 走査で完全性を証明したい」であり、順序は Mitate 自身の typed field (`seq`) で指定している。** data-service-api 側に `seq` の実体は無い (探索の取り違えに注意)。
5. **MitateDB は PostgreSQL の collection table に内部 id 列を持たず `ctid` は不安定。** keyset の tie-break には保存形の変更が要る (Q-1)。
6. **`page.size` 省略時の挙動は両 peer で割れていた** (r2db 既定 100 + `next_page`、MitateDB は `effective max_result_rows` で黙って切り詰め `next_page` 常に null)。1.8.0 では `next_page` に意味が無いので違反ではなかったが、1.9.0 で「null = 末尾」を約束すると同じ要求の完全性判定が割れる — 契約に既定を置く (裁定 #9)。
7. **MitateDB は契約 schema の `Page.size` 上限 1000 を検査していない** (`_check_object_shape` は `minimum`/`maximum` を見ない)。`max_result_rows ≥ 1001` の配備では 1001 が無検査で通る (裁定 #12)。
8. **`opus` 別名の解決はチャットごとに違いうる** (同日に `claude-opus-5` と `claude-opus-5-5` の両方を実測)。

## 裁定

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
| 作業指示書 v1.0 起草担当の疑義 1〜7 | 裁定済み (直す 5、採用 2)、設計 v0.5 / 作業指示書 v1.1 で反映 | `rulings-wo-v1.md`: control_plane と 1.8.0 pin テストを WP-6 に、R-107 行を WP-1 に、Revision note 3 本は既存 `## versioning.version_binding` 節に、MitateDB cell の cursor 入口を WP-2 で (WP-4 まで CAPABILITY_UNSUPPORTED)、conformance 全体は前景 1 回に収まらない (606 s) |
| 設計 v0.5 / 作業指示書 v1.1 起草担当の疑義 1〜4 | 裁定済み (直す 3、採用 1) | OC §1.5 の 39 は変えない (実装担当は peer ごとの部分集合を前景で、全体は監督のゲートのみ)、1.8.0 pin 3 箇所を WP-6 に、cursor 入口は `ApplicationRuntime` (実体は `ApplicationCell`)、L1 件数ピンの条件付き追加は可 |
