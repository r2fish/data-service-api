# 引き継ぎ書 — 2026-10-02 R-36 (オブジェクトストレージ・バイナリ API) 設計レビュー 1 回目・依頼者裁定・設計レビュー 2 回目

本書は R-36 設計レビュー 1 回目の cloud session の記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-36 の正本は設計 `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` v0.3 (候補のまま。以下「設計」。【更新 2026-10-02】設計レビュー 2 回目の後は v0.5) である。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`)。前のチャットの記録: `docs/work-orders/HANDOVER_20261001_R108_FABLE.md`。

本書は設計レビュー 1 回目の記録として起草し、同日の依頼者裁定と設計レビュー 2 回目まで更新した (設計の版は本書 §1)。

## 1. 現在地

- session: cloud (claude.ai/code)。branch `claude/sweet-heisenberg-nqoica`。基点 rev は clone した origin/main の先頭 `4241b55` (R-108 の閉止の merge)。
- 変更: 設計を候補 v0.2 → 候補 v0.3 にした。
  - `48470d5`: 設計レビュー 1 回目の反映 (v0.3。213 → 619 行。v0.2 の行は表題以外すべて残存を機械照合)。
  - `dd1bc9a`: 再確認 RC-1〜RC-21 (設計 §12 の「再確認の反映」) の反映 (v0.3 のまま。v0.2 からの通算で 213 → 703 行)。
- push: 本 session は割り当て branch へ push する (指示)。上の 2 commit は push 済み (origin の同名 branch)。main へは merge も送信もしない。workflow を手で起動しない。
- 触っていないもの: `spec/`、`security/`、`conformance-tests/`、両 peer、台帳 `RM`、版数ログ、既存の引き継ぎ書 (archive 移動を含む)。設計の状態は「候補」のまま (未実装・未宣言・非正本)。
- cloud 環境の制約:
  - Mitate の文書は読めない (実需は `RM` §3.2 の記述だけを使った)。
  - provider (Cloudflare R2 / GCS / Cloud Run) と RFC の公式文書は proxy 拒否で読めない (設計では全て「未確認」と明記)。
  - 完了ゲート (`tools/dev/gate.py`) と `tools/dev/finalize.py` (main への merge) は作業機で行う。
  - `.venv` は Python 3.11 で新規に作り、pre-commit を入れて `.venv/bin/pre-commit install` 済み (cloud 環境のみ。作業機の `.venv` とは別)。
- 本書の commit: 本書だけを加える 3 つ目の commit (hash は `git log -1 -- docs/work-orders/HANDOVER_20261002_R36_FABLE.md`)。設計の 2 commit (`48470d5`、`dd1bc9a`) の後に積む
- 【更新 2026-10-02】変更: 設計を候補 v0.3 → v0.4 → v0.5 にした。設計は v0.5 (候補のまま、1026 行)。commit の一覧 (すべて branch `claude/sweet-heisenberg-nqoica`):
  - `48470d5`: 設計レビュー 1 回目の反映 (v0.3)。
  - `dd1bc9a`: 再確認 RC-1〜RC-21 (設計 §12) の反映 (v0.3 のまま)。
  - `4befd27`: 本書の初版 (179 行)。
  - `1b258ec`: 設計 v0.4 (依頼者裁定の記録と帰結 設計 §11 の Q-0〜Q-5、設計 §7.1 の O-24〜O-26)。
  - `3064a77`: 設計 v0.5 (設計レビュー 2 回目の反映 設計 §12 の N-n、設計 §11 の Q-6〜Q-9、設計 §7.1 の O-27・O-28)。
  - `dfd6f26`: 設計 v0.5 に再確認 2 (設計 §12 の RC2-1〜RC2-14) を反映 (v0.2 からの通算で 213 → 1026 行)。
  - 本書の更新の commit (監督が起草後に積む。hash は `git log -1 -- docs/work-orders/HANDOVER_20261002_R36_FABLE.md`)。
- 【更新 2026-10-02】push: `4befd27` までの 3 commit と `1b258ec`、`3064a77`、`dfd6f26` は push 済み (origin の同名 branch)。main への merge・送信はしていない。
- 【更新 2026-10-02】設計の状態は「候補」のまま。契約・conformance・実装は未着手 (作業機の完了ゲートが要る)。`1b258ec`・`3064a77`・`dfd6f26` が触ったのは設計 1 ファイルだけである。
- 【追記 2026-10-02 作業機】取り込み: worktree `.claude/worktrees/r36` を branch `claude/sweet-heisenberg-nqoica` から作った。7 commit (`48470d5`〜`15b0a5e`) の author / committer は r2fish の noreply のみ、触れているのは設計と本書の 2 ファイルだけと確かめた。作業機の local main は `05a60c0` (R-121 の閉止、台帳 v1.150) に進んでいたので、main を branch に merge してから (`137850d`) 完了ゲートと台帳の更新を行った。その commit (`a597857`) を main へ merge する時点で、並行する別のチャットが R-42 の取り込み (main `557cdd2`、台帳 v1.151、`docs/work-orders/HANDOVER_20261002_R42_FABLE.md`) を main へ入れていたので merge は衝突して中止され (main は無傷)、main をもう一度 branch に merge して台帳の版を v1.152 に付け直し、完了ゲートを取り直した。
- 【追記 2026-10-02 作業機】完了ゲート (監督が単独実行、`-C .claude/worktrees/r36`、label r36-design-v05): 1 回目 (main `05a60c0` を merge した木) `gate: 5019 passed, 2 subtests passed in 465.18s (0:07:45)`、judge=PASS。2 回目 (main `557cdd2` を merge した最終の木) `gate: 5019 passed, 2 subtests passed in 470.09s (0:07:50)`、judge=PASS、pg_database/pg_roles diff 0。件数は main の 5019 と同じ (`COLLECTION_FLOOR` 5019 のまま)。main との差分は `.md` だけなので性能は計測していない (`OC` §1.3 の 27)。
- 【追記 2026-10-02 作業機】台帳 v1.152: `RM` R-36 行を「進行中」(着手条件の欄は `-`) にして【追記】、`RM` R-30 行と R-42 行に【追記】、版数ログの v1.147 の行を archive へ回転した。`tools/dev/ledger.py --check` は GREEN (open=26)。
- 【追記 2026-10-02 作業機】main への merge: 本追記を含む commit を `tools/dev/finalize.py` が local main へ `--no-ff` で merge する (merge commit の hash は main の `git log --merges -1`。本追記の時点では未確定)。main の送信は従前どおり (`docs/work-orders/HANDOVER_20261001_R108_FABLE.md` §3 の 4)。
- 【追記 2026-10-02 作業機 (merge の後)】main への merge commit は `3ce48d2` (R-36 の取り込み。親は main `557cdd2` と branch の commit `c06c1dd`)。`tools/dev/fold.py --apply` で統合済みの古い worktree 5 つを畳んだ。残っているもの: (a) worktree `.claude/worktrees/r36` (作成直後で fold の対象外だった。次の fold で畳む)、(b) origin の branch `claude/sweet-heisenberg-nqoica` (削除は GitHub への送信に当たり agent からはできない。main の送信の指示のときに依頼者 / Mitate 側の監督セッションが削除する)、(c) main の送信 (local main が origin/main `05a60c0` より先行)、(d) 本書 §7 の原文確認 (契約改版の作業指示書に載せる件)。

## 2. 本チャットで閉じたもの

- 設計レビュー 1 回目 (`OC` §1.7 の 50 の 2 回のうち 1 回目。規模 L・Class D。1 巡目は reviewer「担当観点: A」「担当観点: B」の並列 2 起動、再確認は「指定なし」1 起動 (`OC` §1.7 の 50a))。
  - 現状との突き合わせ (explorer 3 起動、reader 1 起動): 契約 1.14.0、port v1.21、adapter 6。古くなった前提は設計 §10 の S-1〜S-16。
  - 1 巡目: 観点 A は 14 件 (設計 §12 の表記で A の 1〜14。依頼者決定の A-1 等とは別の番号)、観点 B は 18 件 (F1〜F18)。監督が重なりを設計 §12 の M-1〜M-22 にまとめた (M-17 / M-18 は統合で欠番)。各 M-n の反映 / 依頼者裁定待ちの別は設計 §12 の表。依頼者裁定待ちは設計 §11 の Q-1〜Q-5 と着手条件 (同 Q-0)。
  - 再確認 (指定なし 1 起動): 21 件 (中〜高 2、中 10、中〜低 6、低 3。クラス引き上げなし)。全件を監督が「直した」と裁定し、設計 §12 の RC-1〜RC-21 として v0.3 に反映した (版は v0.3 のまま)。設計 §12 の RC-9 (c) と RC-18 は案・両論として記し、確定は設計レビュー 2 回目。
  - 静的検査: `tools/check_doc_refs.py` 0 dangling、`tools/public_value_scan.py` (ツリーと新規ファイルの明示引数) 検出 0、`tools/dev/ledger.py --check` GREEN、pre-commit hook 緑 (commit 時)。
- 監督が起草後に埋めた箇所 (設計レビュー 2 回目で検証する): 設計 §3.4 の「未定」欄 (監督裁定 2026-10-02 の印)、設計 §11.1 の「監督の見立て」欄。
- 【更新 2026-10-02】依頼者裁定 (2026-10-02、逐語): 「全て監督推奨で進めてください」。設計 §11 の Q-0〜Q-5 の裁定として設計 §11 の冒頭に逐語で記録した (各 Q の裁定行は本書 §4)。Q-0 は監督の読みで (a) (着手条件の充足 = 設計レビュー 2 回目へ進む)。帰結は設計 v0.4 (`1b258ec`)。
- 【更新 2026-10-02】設計レビュー 2 回目 (`OC` §1.7 の 50 の 2 回のうち 2 回目。規模 L・Class D)。
  - 1 巡目: 観点 A は 20 件 (設計 §12 の A2-1〜A2-20)、観点 B は 14 件 (同 B2-1〜B2-14)。監督が設計 §12 の N-1〜N-21 に統合した (N-1・N-2・N-10 と A2-10 は設計 §11 の Q-7・Q-8・Q-6・Q-9 に置いた)。反映は設計 v0.5 (`3064a77`)。
  - 再確認 2 (指定なし 1 起動): 14 件 (高 1、中〜高 1、中 4、中〜低 4、低〜中 1、低 3。クラス引き上げなし。「裁定」節の表では指摘 1 と 3 を 1 行にまとめ、uvicorn の挙動の観察を 1 行足したので 14 行)。全件を監督が「直した」と裁定し、設計 §12 の RC2-1〜RC2-14 として v0.5 に反映した (版は v0.5 のまま。設計 §12 の小節。`dfd6f26`)。
- 【更新 2026-10-02】新たに依頼者裁定級になった設計 §11 の Q-6〜Q-9 は、依頼者指示「全て監督推奨で進めてください」を本件にも及ぶものと読み (監督の読み)、推奨で進めた。両論と推奨は設計 §11 に残し、依頼者が覆せる (【訂正】を足す形)。
  - Q-6 転送時間: 転送専用 class `object_transfer_ms` を 1 つ足す (B-5 の 4 class を超えるが加算的。`RM` R-42 と独立)。
  - Q-7 router: 既存の前段 (reverse proxy) と同格の基盤部品。SI-00 の残余として `security/CONTROL_MAPPING.md` の SI-00 行に記録 + 要件 6 項目。`RM` R-30 は独立に裁定 (「矛盾しない形で」の文は撤回)。
  - Q-8 concurrency: object-capable な配備では `concurrency` を deployment_required と宣言 (正直な宣言)。
  - Q-9 X-Request-Id: header は常にその要求自身の request_id (既存挙動)。B-3 の契約化の範囲は object_storage の 4 操作の全応答。

## 3. 次の一手

作業機で行う。

1. 依頼者裁定 設計 §11 の Q-0〜Q-5 (両論と監督の推奨は本書 §4)。Q-0 (着手条件の充足) が先。
2. worktree の作成: `git fetch origin claude/sweet-heisenberg-nqoica` の後、linked worktree (`.claude/worktrees/r36`) を同 branch から作る (共有ツリーを checkout しない。`OC` §1.2 の 13・14)。
3. 完了ゲート: 文書のみの変更 (本 session の 2 commit はパス上 Class A。設計レビューの発注クラス D は、設計が最終的に触れる `spec/` と `security/` の経路によるもので、§2 の「Class D」はこちら) だが、規模 L の手順として `tools/dev/gate.py --label r36-design-v03` を監督が単独実行し、集計行を記録する (`OC` §1.13 の 74: ゲートは省略しない)。
4. 台帳の版上げと `RM` R-36 行の【追記】: 設計レビュー 1 回目の実施 (2026-10-02、v0.3)、裁定待ち 設計 §11 の Q-0〜Q-5、6 版目の版数ログ行の archive 移動 (`OC` §1.16 の 78)。`tools/dev/ledger.py --check`。
5. 引き継ぎ書の archive 移動: 本書を含めて最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` (`OC` §1.16 の 78)。
6. `tools/dev/finalize.py` で commit と main への `--no-ff` merge (identity r2fish / noreply の確認、`[skip ci]`)。push の入口は従前どおり (`docs/work-orders/HANDOVER_20261001_R108_FABLE.md` §3 の 4: push は Mitate 側の監督セッションが統制)。
7. provider / RFC の未確認事項の確認 (設計 §12.1 の一覧)。網に出られる環境で公式文書を読み、設計 §5 の表の「確認済み / 未確認」列を埋める。
8. 依頼者裁定の反映 (v0.4) の後、設計レビュー 2 回目 (規模 L: 1 巡目は観点 A / B の 2 起動並列、再確認は指定なし 1 起動)。見る箇所: 設計 §2.1 の SI の割り当て、versioning.obligations 案の義務名、設計 §7.1 の変異の候補列、設計 §3.4 の監督裁定の欄、設計 §11.1 の監督の見立ての欄、`{object_id}` の `field` 位置名が `{entity}` の既存の扱いと揃うか。
9. その後に契約 (1.x.0)・conformance (port v1.22 以降)・実装へ進む (CLAUDE.md の開発順序)。本 session では進めていない。

【更新 2026-10-02】上の 1〜9 は設計レビュー 1 回目の時点の一覧であり、記録として残す。依頼者裁定と設計レビュー 2 回目の後の一覧は次のとおり (作業機で行う)。

1. 依頼者の確認: 設計 §11 の Q-0 と Q-6〜Q-9 の「監督の読み」(設計 §11 の【裁定 2026-10-02】行。本書 §4)。覆すときは設計 §11 に【訂正】を足して v0.6。
2. worktree の作成 (上の 2 のとおり)。
3. 完了ゲート (`tools/dev/gate.py --label r36-design-v05`。手順は上の 3 のとおり)。
4. 台帳の版上げと `RM` R-36 行の【追記】(設計レビュー 1・2 回目の実施、依頼者裁定 2026-10-02 の逐語、設計 §11 の Q-0〜Q-9、次の段は契約改版の作業指示書)、`RM` R-30 行への【追記】(`RM` R-36 の設計 §11.1 の (ii) の router の位置づけを `RM` R-30 の裁定時に確認する)、`RM` R-42 行への【追記】(`RM` R-36 は `object_transfer_ms` で独立にした)。6 版目の版数ログ行の archive 移動。
5. 引き継ぎ書の archive 移動 (`docs/work-orders/HANDOVER_20261001_R102_FABLE.md` の 1 通)。
6. `tools/dev/finalize.py` で commit と main への merge。
7. provider / RFC / nginx の未確認事項の確認 (設計 §12.1)。
8. 契約改版の作業指示書 (Class C/D。CLAUDE.md の開発順序: 共通契約 (media_type の操作別例外・version_binding (a)・OperationCatalogEntry の request/response media type と headers・field 定義・violated_declaration 14 語・limits.classes +5・destructive applies_to・Idempotency-Key header・X-Request-Id・{object_id}・authorization_propagation_bound_ms の正の宣言) → conformance (port v1.22 以降、設計 §7.1 の O-n → C-n) → 両 peer の実装 → CONTROL_MAPPING (SI-00 の router 残余、SI-08 の総量残余) → 配備値)。設計レビューの回数は済み (2 回)。実装 WP は規模 L の手順。
9. 設計 §12.1 の観察 (v0.1 の不在、未確認事項) はそのまま。

【追記 2026-10-02 作業機】上の【更新 2026-10-02】の 1〜6 は済み (1 は本書 §4 の【追記】、2〜4・6 は本書 §1 の【追記】)。5 の `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` は R-121 の取り込み (`03ef01c`) で archive へ移動済みだった。依頼者確認 2026-10-02 のとおり `docs/work-orders/HANDOVER_20261001_R108_FABLE.md` を `docs/archive/docs/work-orders/` へ移し (並行する R-42 の取り込み main `9674ab9` も同じ移動をしていた)、R-42 の引き継ぎ書が main に入ったので、最新 2 通 (`docs/work-orders/HANDOVER_20261002_R42_FABLE.md` と本書) から外れる `docs/work-orders/HANDOVER_20261002_R121_FABLE.md` も同じ変更セットで移した (`OC` §1.16 の 78。監督の適用であり、依頼者に確認したのは R108 の 1 通)。7 は本書 §7。残りは 8 (契約改版の作業指示書。別の変更セット) と worktree の畳み込み (`tools/dev/fold.py`)。

## 4. 依頼者判断待ち・未決

- 着手条件の充足そのものが依頼者裁定である (設計 §11 の Q-0)。
- 関連する台帳の未決: `RM` R-30 (設計 §11 の Q-2 と連動)、`RM` R-42 (設計 §11 の Q-3 と連動)。
- 【更新 2026-10-02】設計 §11 の Q-0〜Q-5 は依頼者裁定済み (2026-10-02、逐語「全て監督推奨で進めてください」)。各 Q の【裁定 2026-10-02】行は下の写しの各 Q の末尾に足した。`RM` R-30 は独立に裁定し (設計 §11 の Q-7)、`RM` R-42 とは `object_transfer_ms` で独立にした (設計 §11 の Q-6)。両行は未決のまま。
- 【更新 2026-10-02】依頼者の確認待ち (監督の読みで進めた件。覆すときは設計 §11 に【訂正】を足して v0.6。設計 §11 の Q-6〜Q-9 は契約改版 WP の着手前に確認を得る (設計 §11 の RC2-4 の行)):
  - 設計 §11 の Q-0: 依頼者指示を選択肢 (a)「充足とみなし設計レビュー 2 回目へ進む」と読んだ (監督は Q-0 に推奨を置かなかった)。
  - 設計 §11 の Q-6: 推奨 (c) 転送専用 class `object_transfer_ms` を 1 つ足す (Q-3 (甲) の「class を増やさない」を改める)。
  - 設計 §11 の Q-7: 推奨 (a)+(b) router を前段と同格の基盤部品とし、SI-00 の残余を記録 + 要件を条件にする。
  - 設計 §11 の Q-8: 推奨 (a) object-capable な配備では `concurrency` を `deployment_required` と宣言する。
  - 設計 §11 の Q-9: 推奨 (a) header は常にその要求自身の request_id とする。
- 【追記 2026-10-02 作業機】依頼者の確認 (2026-10-02、作業機の session。選択肢の選択): 設計 §11 の Q-0 は「(a) 充足」、Q-6〜Q-9 は「4 件とも推奨どおり」。覆した件は無く、設計は v0.5 のまま (【訂正】なし)。Q-0 は cloud session の監督が推奨を置かなかった件で、依頼者指示 (逐語)「裁定は推奨を示してください」を受けて作業機の監督が (a) を推奨した (理由: 依頼者指示「全て監督推奨で進めてください」は Q-0 を先頭に置いた提示への返答であり (b) 保留と両立しない。設計レビュー 2 回は済みで、設計は候補のまま何も宣言していない。object_storage は common_baseline の外の加算的な capability)。実需は 2026-10-02 時点も部分的のままである (Mitate `docs/remaining-work-index.md` の「添付ファイル・画像」は「F2とは別工程として保留」。作業機で確認し、確認の提示に添えた)。

以下は設計 v0.3 §11 (Q-0〜Q-5 と §11.1) の逐語の写しである。本小節の中の節番号 (§n)・M-n・RC-n・S-n・O-n・P-n・A-1〜B-12 は設計 v0.3 のもの、R-n・§3.2 等で `RM` を添えたものは台帳のものである。

【更新 2026-10-02】各 Q の末尾の【裁定 2026-10-02】行、下の「依頼者の裁定」の段落、Q-6〜Q-9 (両論・推奨・裁定行とその後の行) は設計 v0.5 §11 の逐語の写しであり、その中の節番号・ID (N-n・RC2-n・O-n を含む) は設計 v0.5 のものである。

【裁定 2026-10-02】依頼者の裁定 (Q-0〜Q-5 に対する裁定。引き継ぎ書 `HANDOVER_20261002_R36_FABLE.md` §4 の提示に対する返答。逐語):

> 全て監督推奨で進めてください

設計レビュー 1 回目で挙がった、依頼者決定 A-1〜B-12 と現状の食い違い、または決定の確定後に挙がった露出である。決定は再審議しない。各件は両論のまま置き、v0.3 では確定しない。「推奨」は監督の推奨であり、裁定ではない。

### Q-0 着手条件の充足

- 決定: 台帳 `RM` R-36 の着手条件は「設計レビュー。充足は依頼者裁定」。
- 【v0.3 2026-10-02 再確認反映 RC-14】決定 (追記): 台帳 `RM` R-36 の着手条件には「運用開始後 (v1.105 の追記: 運用が始まって data と client が存在しても直す費用は上がらない)」もある (`RM`:459)。
- 現状: 実需は台帳 `RM` §3.2 の突合表で「部分的」(Mitate `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像 — F2 とは別工程として保留」、`docs/design/agent-entry-record.md` §6.1。data-service-api への具体的な要件は未確定)。
- 【v0.3 2026-10-02 再確認反映 RC-14】運用開始の現状は本 session では確かめていない (作業機で台帳 `RM` §1 の現状から確認)。
- 食い違い: 設計レビュー 1 回目は 2026-10-02 に行ったが、契約・conformance・実装へ進む着手条件の充足は依頼者裁定である。
- 選択肢 (両論): (a) 充足とみなし、設計レビュー 2 回目へ進む。(b) 実需の記録を待つ (候補のまま保留)。
- 推奨: 監督は判断しない (依頼者事項)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a) 充足とみなし、設計レビュー 2 回目へ進む (監督の読み)。帰結は冒頭の版数表 (v0.4 行)、冒頭の v0.4 の印の行、§1。

### Q-1 download 応答の分類

- 決定: §2「`Content-Type` は保存・返却する」、B-4、B-11 (ブラウザ向け attachment)。
- 現状: 契約 1.14.0 は全成功応答の media type を `application/json` に固定し (`spec/data-service-api.v1.json:8`、`:40` の 1.14.0 (a))、client は media type だけで分類する (`:895`、「HTTP status decides neither」)。§10 の S-2。
- 食い違い: (i) bytes の成功応答は現行文言で契約違反であり、かつ「解釈しない失敗」になる。(ii) 送信者が `Content-Type: application/problem+json` と errors.shape を満たす本文の object を upload すると、同 application の agent が download したとき、200 でも偽の失敗 (例: `AUTH_REVOKED`) として読む。`application/json` なら response schema との照合に回る。
- 選択肢 (両論):
  - (甲) 契約の分類規則に download 操作だけの例外を足す。2xx は bytes の成功 (media type を問わず response schema と照合しない)、2xx 以外で errors.content_type なら失敗、それ以外は解釈しない失敗。upload は request media type を operation 別に許す。
  - (乙) 甲に加えて、upload で media type が errors.content_type に一致するものを `VALIDATION_FAILED` で拒否する (problem+json 文書を保存する能力を失う)。
  - (丙) download は常に `application/octet-stream` で返し、保存値は metadata にだけ載せる (§2 の「返却する」と B-11 の想定を変える)。
  - いずれも契約の `media_type_note` / `response_classification` / `external_standards` の改版 (1.x.0、従属判断 19 の例外) になる。
  - 【v0.3 2026-10-02 再確認反映 RC-19】`spec/data-service-api.v1.json:36` では additive な capability は minor。object_storage は common_baseline の外の新 capability で、既存の要求・応答の意味は変えない。media_type_note / response_classification の改版は新しい操作にだけ掛かる例外の追加であり、既存操作の分類は不変。したがって minor (1.x.0) と読む。semantic change と読む余地があれば major であり、その判断は依頼者。
- 推奨 (監督の推奨): (甲) + (乙)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (甲) + (乙)。帰結は §2、§3.2、§3.3、§3.4、§7.1 の O-24 (§2.1 の対応を含む)。

### Q-2 A-1 の application 専用実行単位への到達経路

- 決定: A-1。
- 現状: object 経路は data surface に属し、client は `surfaces.data.base_url` から URL を組む (`spec/data-service-api.v1.json:35`)。data / control の文書は同じ surfaces を返し、control surface は deployment に 1 つ (`:1410`)。limit_enforcement は base URL 背後の全 process を記述する (`:324`)。base URL を serve する process は 1 host (`MULTI_PROCESS_WORKER_V0_1.md:778`)、concurrency の enforced は 1 host の slot 共有が条件 (同 `:845`)。`conformance-tests/CONDITIONS.md` C-19 は 1 base URL と 1 credential で足りることを要求する。台帳 `RM` R-30 (SI-00 の境界と複数 Application の DSN) は未決。§10 の S-13。
- 食い違い: 1 つの data base URL の背後に application ごとの実行単位を置く経路が設計に無い。v0.2 の §9 の 1 は deployment 設計に回しているが、契約の問題である。
- 選択肢 (両論): §11.1 の表の (i)〜(iii)。
- 推奨 (監督の推奨): (ii) を台帳 `RM` R-30 の裁定と同時に決める。各案の `concurrency` / `object_transfers` の `limit_enforcement` の帰結を表 (§11.1) で併記する。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (ii)。帰結は冒頭の A-1 の註、§3.1、§6.1、§9 (旧 1 と新 4)。下の §11.1 の表は両論の記録として残す。

#### 11.1 到達経路の選択肢

「監督の見立て 2026-10-02」の欄は、v0.3 の材料 (設計レビュー 1 と監督の突合) に無く監督が起草後に埋めたものであり、設計レビュー 2 回目で検証する。裁定は依頼者。

| 案 | 内容 | 改版の要る契約・規則 | `concurrency` の `limit_enforcement` | `object_transfers` の `limit_enforcement` | SI-00 の観点 | O-5 の期待値。【v0.3 2026-10-02 再確認反映 RC-4】他 application の単位 / URL へ誤配されたときの結果 (欠陥の観測。peer-local または deployment evidence の条件であり O-5 ではない) |
| --- | --- | --- | --- | --- | --- | --- |
| (i) | application ごとに別の data base URL (= 別 deployment)。台帳 `RM` R-30 の「serving set を 1 Application に限る」側を全面採用する | control surface と、surfaces 同一の規則 (`spec/data-service-api.v1.json:1410`) | 監督の見立て 2026-10-02: 各 deployment が 1 host なら `enforced` (`MULTI_PROCESS_WORKER_V0_1.md` 裁定 10・27 のまま) | 監督の見立て: 同じく 1 host 内の共有 slot で `enforced` | 監督の見立て: multi-application 部品が無く SI-00 の面では最も単純。費用は application 数に比例する deployment 数 | 監督の見立て: 別 deployment の credential は `AUTH_INVALID` (そもそも base URL が別) |
| (ii) | 1 base URL のまま、前段 router が credential から application を引き、専用単位へ振り分ける。router は bucket 資格情報を持たない。各単位は bearer を自分の 1 application に再認証するので、誤配は `AUTH_INVALID` で閉じる | 監督の見立て 2026-10-02: 契約は変えなくてよい (surfaces は 1 つのまま) | Cloud Run で service が複数 = 複数 host なら `deployment_required` へ後退 (Cloud Run の挙動は未確認)。1 host 内の process 分割なら `enforced` のまま | 監督の見立て: application 単位の枠はその application の単位 (1 host) に閉じるので `enforced`。【v0.3 2026-10-02 再確認反映 RC-15】application の単位が 1 instance (Cloud Run なら最大 instance 1。自動スケールの挙動は未確認) のとき | router は全 application の認証状態と全 bytes を扱う multi-application 部品であり、SI-00 の対象 | `NOT_FOUND` は `AUTH_INVALID` に変わり得る。【v0.3 2026-10-02 再確認反映 RC-4】誤配の結果は `AUTH_INVALID` |
| (iii) | object endpoint を application 専用の path prefix、または新 surface (`surfaces.objects`) に置く | url_composition、`conformance-tests/CONDITIONS.md` C-19 と C-35 | 監督の見立て 2026-10-02: (ii) と同じ (prefix で振り分ける前段が要る) | 監督の見立て: (ii) と同じ | 監督の見立て: 前段は path だけ見るので認証状態を持たないが、application の識別子が URL に出る (非開示の衛生に反する) | 監督の見立て: 他 application の prefix へ送った credential は `AUTH_INVALID` |

### Q-3 転送時間の bound

- 決定: B-5 (4 class)、§2「ストリーム読み書き時間を宣言・強制」。
- 現状: 時間を表す limit class は `execution_ms` だけで、計測開始と待ちの扱いは台帳 `RM` R-42 で未決 (§10 の S-14)。
- 食い違い: §2 の時間の要求を、B-5 の 4 class のどれも表さない。
- 選択肢 (両論):
  - (甲) `execution_ms` を転送全体 (受付から available / 送信完了まで) に掛け、台帳 `RM` R-42 の裁定に従う。class を増やさない。1 byte/秒の upload は宣言時間で `LIMIT_EXCEEDED` になり、枠が解放される。
  - (乙) 転送の全体時間と最低速度 (idle) の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (甲)。宣言しない運用値の timeout は置かない (台帳 `RM` P-3 / P-5)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (甲)。台帳 `RM` R-42 の裁定 (execution_ms の計測開始と待ちの扱い) に従う。帰結は §0 の B-5 の註、§2、§3.4、§4 (M-5)、§6 の 5、§6.1、§7.1 の O-25、§8。

### Q-4 B-7 と両 peer の宣言値 0

- 決定: B-7「authorization propagation bound 以内の周期で再認可し、失効を観測したら転送を中断する」。
- 現状: 両 peer は `authorization_propagation_bound_ms: 0` を宣言する (`r2db-api/src/r2db_api/capabilities_document.py:188`、`MitateDB-api/src/mitatedb_api/capabilities_document.py:452`。schema の最小値は 0)。SI-13 は要求単位の「subsequent authorization」に掛かり、転送途中の再認可を求める文言は無い (`security/SECURITY_INVARIANTS_V1.md:338-351`)。
- 食い違い: 0 を文字どおり守るには chunk ごとの再認可が要る。v0.2 の設計内でも §4 の 4 (転送後 1 回) と §6 の 5 / B-7 (転送中) がずれていた (§4 の 4 は v0.3 の M-11 で「転送の間、周期 P で再認可 + 完了時にも 1 回」に揃えた)。
- 選択肢 (両論):
  - (a) object_storage を提供する deployment は正の bound を宣言し、その値を「失効の伝搬遅延 + 再認可周期 P」を含む値とする (宣言値の変更。台帳 `RM` §9 の 8 でクラス確認)。
  - (b) chunk ごとに再認可し、0 を保つ (認証 DB の負荷)。
  - (c) SI-13 を受付時と available 直前 (commit) に適用し、転送中は再認可しない (B-7 の本文と食い違うため推奨しない。記録のみ)。
- 推奨 (監督の推奨): (a)。どの案でも、再認可で `AUTH_STATE_UNAVAILABLE` なら中断する (fail closed)。download の中断は接続の異常終了で client に伝え、client は「受信長 = `Content-Length` かつ `Content-Digest` 一致」を成功条件とする (§3.3 の M-6 の反映と同じ)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a)。帰結は §0 の B-7 の註、§4 の 4、§6 の 5、§7.1 の O-13、§8。

### Q-5 総保存量・object 数の上限

- 決定: B-5 (rate のみ)。
- 現状: SI-08 (`security/SECURITY_INVARIANTS_V1.md`) は「object creation rate or count」を挙げ、rate (`object_requests_per_minute`) で文言は満たす。台帳 `RM` P-5 は安全上必要な bound だけを置く。provider の課金は application をまたぐ運用者の共通資源である。
- 食い違い: 決定との矛盾ではなく、B-5 の確定後に挙がった露出である。
- 選択肢 (両論):
  - (a) 初版は class を足さず、§8 の運用値に provider 側の quota / 予算 alert を置く。
  - (b) `object_count` / `object_total_bytes` の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (a)。
- 【裁定 2026-10-02】依頼者「全て監督推奨で進めてください」→ (a)。帰結は §0 の B-5 の註、§2、§8。

【v0.5 2026-10-02 設計レビュー 2 反映 Q-6〜Q-9】Q-6〜Q-9 は設計レビュー 2 回目で挙がった、依頼者裁定 Q-0〜Q-5 の帰結と現状の食い違いであり、監督の突合で依頼者裁定級とした。形は Q-0〜Q-5 と同じ。各件の末尾の【裁定 2026-10-02】行は、上の依頼者裁定の逐語を本件にも及ぶものとした監督の読みである。

- 【v0.5 2026-10-02 再確認 2 反映 RC2-4 (監督)】Q-6〜Q-9 は依頼者指示「全て監督推奨で進めてください」を本件にも及ぶものと読んで (監督の読み) 推奨で進めたので、契約改版 WP の着手前に依頼者の確認を得る (Q-6 の裁定行の 1 行は Q-7〜Q-9 にも掛かる)。

### Q-6 転送時間の bound と `execution_ms` の共有 (N-10)

- 決定: Q-3 の裁定 (甲) (`execution_ms` を転送全体に掛ける)。B-5 (4 class)。
- 現状: `execution_ms` は deployment に 1 つの宣言値であり、query / mutation / schema operation と共有する (`spec/data-service-api.v1.json:929-947`)。契約の例 (`execution_ms` 5000 ms。`spec/data-service-api.v1.json:955`) と §3 の例 (`object_bytes` 50 MiB) を組むと、10 MiB/s 未満の client の upload は必ず `LIMIT_EXCEEDED` になる。仮の起点「受付 = 認証成功時点」(§2、§6.1 の Q-3 の段落) は契約に「仮」と書けず、両 peer の現行の起点 (limit gate 通過時。`RM`:462) とも違う。
- 食い違い: Q-3 (甲) のままでは実用にならない。
- 【v0.5 2026-10-02 再確認 2 反映 RC2-4】食い違い (追記): (c) は Q-3 の (乙) のうち全体時間の class に当たり、Q-3 (甲) の「class を増やさない」を改める。
- 選択肢 (両論):
  - (a) 共有を受け入れ、運用値 (§8) で `execution_ms` を上げる (JSON 経路の bound が緩む)。
  - (b) `execution_ms` を操作別に宣言する (契約の limits の形の変更)。
  - (c) 転送専用の class `object_transfer_ms` を 1 つ足す (B-5 の 4 class を超えるが加算的)。起点 = `object_transfers` 枠の獲得時点、終点 = available への遷移 / 送信完了。台帳 `RM` R-42 と独立。
- 推奨 (監督の推奨): (c)。agent が必要な最低速度 = `object_bytes` / `object_transfer_ms` を宣言から導けることを契約文に書く。§6.1 に行を足し、§3.4 の `execution_ms` の行を `object_transfer_ms` に改め (旧文は残す)、O-25 を `object_transfer_ms` に改める。実装側の socket timeout は `object_transfer_ms` 以下の運用値とする。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (c) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §0 の B-5 の註、§2、§3、§3.4 (失敗の表の末尾)、§4 (M-5)、§6 の 5、§6.1 (表と Q-6 の段落)、§7.1 の O-25、§8、§11 の Q-3 の裁定行の後。
- 【v0.5 2026-10-02 再確認 2 反映 RC2-4】契約改版 WP の着手前に依頼者の確認を得る (監督の読みで進めた件の確認。`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51 との関係)。

### Q-7 router の SI-00 上の扱いと要件 (N-1)

- 決定: Q-2 の裁定 (ii)。A-1。
- 現状: router は TLS 終端として全 application の bearer を平文で受ける (既存の前段 nginx も同じ)。
- 食い違い: router の単一欠陥は他 application の bearer に届くので、A-1 の目的 (application-facing の単一欠陥で他 bucket に届かない) は router については成り立たない。§3.1 の Q-2 の段落の「R-30 の一方の答えを先取りしない」と「R-30 の裁定は (ii) と矛盾しない形で別途行う」は自己矛盾である。
- 選択肢 (両論):
  - (a) router を既存の前段 (reverse proxy) と同格の基盤部品と位置づけ、SI-00 (`security/SECURITY_INVARIANTS_V1.md`) の残余として `security/CONTROL_MAPPING.md` の SI-00 行に記録する。
  - (b) router の要件を列挙して条件にする。
- 推奨 (監督の推奨): (a)+(b)。要件: router は契約の応答を一切組まない (lookup に失敗した要求は deployment の JSON process へ回し、そこが `AUTH_INVALID` / `AUTH_REQUIRED` を返して監査する)、application logic・bucket 資格情報・DB 書き込み・本文の保存を持たない、保持する状態は「bearer の hash → application_id」の読み取り専用の射影だけ (secret を再構成できない)、本文は転送するだけ、専用単位は自分の 1 application で bearer を再認証する (誤配は `AUTH_INVALID`、O-26)。専用単位は serving set が 1 application でなければ起動しない (fail closed。test 専用の composition root だけが多 application を許す。RC-10 と同形)。capability document を返す process と専用単位の設定値は同じ出所から導き、起動時に一致を検査する (台帳 `RM` P-3)。台帳 `RM` R-30 との関係: 「矛盾しない形で」の文を撤回し、「R-30 は独立に裁定する。(ii) の router は application-facing 実装ではなく前段であり、R-30 のどちらの答えとも両立する。R-30 の裁定時に router の位置づけを確認する」に改める (旧文は残す)。R-30 行への追記は作業機の台帳更新で行う (次の一手)。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a)+(b) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §3.1 (Q-7 の段落)、§6.1 (Q-7 の段落)、§9 の新 5、§11 の Q-2 (監督の読みの後)。
- 【v0.5 2026-10-02 再確認 2 反映 RC2-1 / RC2-3】上の推奨の要件のうち、lookup に失敗した要求の扱い・router が持たないもの・router が保持する状態は §3.1 の Q-7 の段落の RC2-1 / RC2-3 で改めた (推奨と裁定行の本文は変えない)。

### Q-8 (ii) の `concurrency` の宣言 (N-2)

- 決定: Q-2 の裁定 (ii) と、v0.4 の帰結「1 host なら `enforced` のまま」(§6.1 の Q-2 の段落)。
- 現状: `MULTI_PROCESS_WORKER_V0_1.md` 裁定 27・28 (`MULTI_PROCESS_WORKER_V0_1.md:845-846`) の `enforced` の写像は「自 supervisor の workers ≥ process_ceilings.data」かつ「slot directory が自 user 所有 0700」である。
- 食い違い: router・JSON process・専用単位が別 composition root (A-1 なら別 OS user) で並ぶ (ii) では、そのままでは JSON 経路の `concurrency` も `deployment_required` に後退する。user を揃えると単位間の分離が弱まる (OS 側の塞ぎ方は未確認)。
- 選択肢 (両論):
  - (a) object-capable な配備では `concurrency` を `deployment_required` と宣言する (正直な宣言。`conformance-tests/CONDITIONS.md` C-32 の挙動は変わらない)。
  - (b) slot directory を composition root 間で共有する (裁定 28 を改める。Class D の別裁定)。
  - (c) object の 4 操作は `concurrency` を一切消費せず (metadata / delete も object 側の admission に乗せる)、`concurrency` の意味を「JSON 経路の in-flight」と契約に書く (契約の limits の記述の変更)。
- 推奨 (監督の推奨): (a)。v0.4 の帰結の文を改め (旧文は残す)、§11.1 の (ii) 行と §6.1 を直す。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §6.1 (Q-8 の段落)、§11.1 の (ii) 行。

### Q-9 X-Request-Id の意味 (N-6 の一部)

- 決定: B-3。§3.2 の M-14「`X-Request-Id` は、body に `request_id` がある応答では同じ値」。
- 現状: 両 peer の `x-request-id` は「その要求自身の request_id = その要求の監査行の値」であり、JSON の replay では header (新) と body (元) が異なる (`r2db-api/src/r2db_api/http.py:279`)。
- 食い違い: M-14 を全体に掛けると既存 JSON の replay が非適合になり、upload だけに掛けると replay 要求自身の監査行と header の相関が切れる。
- 選択肢 (両論):
  - (a) header は常にその要求自身の request_id とする (replay の元の値は body の request_id だけ。既存挙動のまま)。
  - (b) header = body とする。
- 推奨 (監督の推奨): (a)。M-14 と §3.2.1 を改め (旧文は残す)、B-3 の契約化の範囲は「object_storage の 4 操作の全応答 (成功・失敗) が `X-Request-Id` にその要求自身の request_id を運ぶ」(object_storage 条件付きの義務。既存操作は変えない) とする。
- 【裁定 2026-10-02】依頼者指示「全て監督推奨で進めてください」(2026-10-02) を本件にも及ぶものと読み (監督の読み)、推奨 (a) で進める。依頼者が覆すときは本行に【訂正】を足す。帰結は §0 の B-3 の註、§2.1 (RC-13 の後)、§3.2、§3.2.1、§7.1 の O-7・O-10。

## 5. 運用上の教訓

- cloud session では Mitate 文書・provider 公式文書・完了ゲートに到達できない。到達できないものは「未確認」と書き、作業機の次の一手 (本書 §3) に回した。
- 設計の起草後に監督が埋めた欄 (「監督裁定」「監督の見立て」) は印を付け、次のレビューの対象と明記した。
- `conformance-tests/CONDITIONS.md` に未定義の共通条件の番号 (現行の最大 C-35 より上) は `tools/check_doc_refs.py` が赤にするので、候補条件は設計内の局所 ID (設計 §7.1 の O-n) で書いた。
- 【更新 2026-10-02】推奨で進める指示の下でも、新たに裁定級になった件 (設計 §11 の Q-6〜Q-9) は両論を残し「監督の読み」と明記して、依頼者の確認を次の一手 (本書 §3 の【更新 2026-10-02】の 1) に置いた。
- 【更新 2026-10-02】設計レビュー 2 回目の再確認で初めて見つかった件 (router の lookup 失敗、C-05 の仕組み。設計 §12 の RC2-1・RC2-2) は、1 巡目の枠に「現行の検査器の仕組み」を読む材料が無かったことによる。次回は conformance の実装 (test_c05 等) を枠に入れる。

## 6. 裁定

`OC` §1.15 の 77。語は 起票 R-N / 既知の穴 / 観察 / 直した に、本書では「裁定待ち」と「推奨で進める」を足す (77 の 4 語の外。依頼者の判断が要る件を起票にも観察にもしないため。「裁定待ち」= 依頼者裁定待ち (設計 v0.3 の独立節 Q-n に両論で置いた。2026-10-02 の依頼者裁定で解けた。本書 §4)、「推奨で進める」= 新たに依頼者裁定級になった件を、依頼者指示を本件にも及ぶとした監督の読みで推奨のまま進めた (設計 v0.5 §11 の Q-6〜Q-9。依頼者の確認待ち))。表の ID は設計のもの (M-n・RC-n・S-n・B-n・P-n・Q-0〜Q-5 は v0.3 以降、O-24 以降は v0.4 以降、N-n・RC2-n・Q-6〜Q-9 は v0.5)。「レビュー A・n」「レビュー B・Fn」は 1 回目の 1 巡目、「設計レビュー 2 A・n / B・n」は 2 回目の 1 巡目 (設計 v0.5 §12 の A2-n / B2-n)、「再確認・n」「再確認 2・n」は各回の再確認の指摘番号である。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー A・1 / B・F1 (download の Content-Type を送信者が決められ、契約の分類で偽の失敗・成功と読む) | 裁定待ち (Q-1) | 契約 1.14.0 の分類規則 (従属判断 19) に操作別の例外を足す決定で、依頼者事項 |
| レビュー A・2 / B・F3 (A-1 の application 専用実行単位へ要求を届ける経路が無く、1 base URL・surfaces 同一・1 host の規律と衝突) | 裁定待ち (Q-2) | 依頼者決定 A-1 と現状 (契約 :35 / :1410 / :324、`MULTI_PROCESS_WORKER` 裁定 10・27) の食い違い。台帳 `RM` R-30 と連動 |
| レビュー A・3 (host 共有の認証前 concurrency slot を長い転送が占有する。object_transfers の範囲と置き場) | 直した (M-3) + 裁定待ち (Q-3) | slot の持ち替え・application 単位・flock 実現は設計で確定。転送時間の class は B-5 の 4 class を超え得るので依頼者 (R-42 と連動) |
| レビュー A・4 (cleanup worker が SI-00 の confused deputy になり得る) | 直した (M-4) | A-1 の制約を worker にも及ぼし、provider key を再計算して照合にだけ使う |
| レビュー A・5 / B・F15 の一部 (process 喪失で pending が回収されず孤児が残る。未完了 multipart / resumable) | 直した (M-5) | pending の期限回収と cleanup の監査を設計に書いた。provider の abort 操作は未確認と明記 |
| レビュー A・6 / B・F4 後半 (download の途中失敗が短い成功に見える。upload の途中拒否が届かない) | 直した (M-6) | Content-Length 必須・異常終了・client の成功条件・100-continue を設計に書いた |
| レビュー A・7 / B・F12 (idempotency の digest 材料・評価時点・header 構文・直列化の地点・削除の idempotency) | 直した (M-7) | 材料と 2 transaction 構成を設計で確定。B-1 の本文は変えない |
| レビュー A・8 / B・F5 の filename (B-11「正規化」と §3.2「拒否」の食い違い、filename*、非 ASCII) | 直した (M-8) | 置換と拒否の表で固定し §3.2 を B-11 に寄せた |
| レビュー A・9 / B・F2 / B・F11 (削除の 204 は 1.14.0 (a) と :895 で解釈しない失敗。dry_run / budget の無視) | 直した (M-9) | 200 の JSON 結果、成功の定義、閉じた schema、unsupported_field の拒否を設計に書いた |
| レビュー A・10 / B・F10 / B・F15 (provider と前段の上限に依る主張。nginx 1100k、Cloud Run 上限、R2 token 粒度、条件付き PUT、no-transform) | 直した (M-10) + 観察 | 設計の主張を bucket 範囲に改め、§6 の 6 (前段の上限) を足した。provider 挙動は全て未確認 (作業機で確認する。次の一手) |
| レビュー A・11 / B・F4 前半 (再認可の位置の矛盾、周期と bound、AUTH_STATE_UNAVAILABLE、両 peer の bound 0) | 直した (M-11 の反映分) + 裁定待ち (Q-4) | 位置と fail closed は設計で確定。B-7 と宣言値 0 の食い違いは依頼者 |
| レビュー A・12 / B・F8 (§7 の 4 が §4 の順序で満たせない) | 直した (M-12) | Content-Length 付きと chunked に条件を分けた |
| レビュー A・13 / B・F13 の容量 (総保存量・object 数の上限が無い) | 裁定待ち (Q-5) | class の追加は B-5 を超える。推奨は足さない (P-5) |
| レビュー A・14 / B・F6 / B・F7 (操作名の不揃い、metadata の宣言漏れ、roles、object_id 構文違反の code、request_id の意味、keep-alive) | 直した (M-14) | 1 組の名前、roles、IDENTIFIER_INVALID、request_id の規則、Connection: close を設計に書いた。`get_object_metadata` は B-12 の列挙への追加 |
| レビュー B・F5 (object 専用 error 語彙の表が無い。header の違反を details で表せない) | 直した (M-15) | 失敗の表と `header/<名>` の位置表記、violated_declaration の拡張案 |
| レビュー B・F9 (conformance の観測点・port・変異・PROVIDED/ABSENT・実クラウド skip) | 直した (M-16) | §7 を条件表 (O-n 仮) に書き直し、port v1.22 以降の拡張と ABSENT 分岐を明記 |
| レビュー B・F13 の計測対象 (object_metadata_bytes 等の定義、requests_per_minute との関係) | 直した (M-3) | class ごとの定義と境界を書いた |
| レビュー B・F14 (Content-Digest の algorithm・Content-Encoding・canonical string・download の照合) | 直した (M-19) | 4 点の規則を §2 に書いた |
| レビュー B・F16 (§9 の順序が CLAUDE.md の開発順序と逆。CONTROL_MAPPING の段が無い) | 直した (M-20) | 並べ替えた |
| レビュー B・F17 (§2 に SI の ID が無い) | 直した (M-21) | SI 列と条件列を足した。invariant は増やさない |
| レビュー B・F18 (版数表・v0.1 の不在・A-2 の陳腐化・ID 参照・「ブラウザ向け」) | 直した (M-22) + 観察 | 版数表と註を足した。v0.1 の推薦案と却下案は repository に無い (復元しない) |
| 監督 S-1〜S-16 (枠。v0.2 以後に古くなった前提) | 直した | v0.3 の「現状との突き合わせ」節に表で写し、決定行に註 |
| 監督 S-16 / 台帳 R-36 (着手条件の充足) | 裁定待ち (Q-0) | 着手条件の充足そのものが依頼者裁定 (台帳 §3.2・§5 フェーズ11) |
| 再確認・1 (削除の再送の結果が設計内で矛盾) | 直した (RC-1) | key なしは NOT_FOUND、同 key は元の 200 の replay に分けた |
| 再確認・2 (`deleting` のまま SIGKILL で bytes が残る) | 直した (RC-2) | 回収対象に `deleting` を足し、条件 O-19b |
| 再確認・3 (audit を tx2 の中と読める) | 直した (RC-3) | pre_commit (決定 1-A) に揃え、delete も同経路 |
| 再確認・4 (O-5 の期待値が AUTH_INVALID を許す) | 直した (RC-4) | O-5 は NOT_FOUND に固定、誤配の観測は別列 |
| 再確認・5 (filename の文字集合・順序・優先・charset・fallback) | 直した (RC-5) | 表に 5 点を足した |
| 再確認・6 (認証後の枠の対象と rate の鍵) | 直した (RC-6) | 持ち替えは upload / download のみ、鍵は credential_id / application |
| 再確認・7 (cleanup と遅い upload の競合) | 直した (RC-7) | 条件付き更新と worker の先行遷移 |
| 再確認・8 (検査順と欠けた失敗行) | 直した (RC-8) | 検査順の表と 4 行を足した |
| 再確認・9 (`unsupported_field` の誤用、`field` 定義、header の手がかり) | 直した (RC-9。(c) は案として記し確定は設計レビュー 2) | spec :921 の語義に合わせ request_schema、`field` 定義の改版を明記 |
| 再確認・10 (port の注入 method と偽 provider の fail closed) | 直した (RC-10) | :417 に足した |
| 再確認・11 (O-20 の変異が殺せない) | 直した (RC-11) | C-33 の形に |
| 再確認・12 (SI-11 の前提 atomicity、SI-03 の根拠) | 直した (RC-12) | atomicity 案と SI-03 の言い換え |
| 再確認・13 (obligations 案が非網羅) | 直した (RC-13) | 非網羅の例示と明記 |
| 再確認・14 (Q-0 に「運用開始後」が無い) | 直した (RC-14) | 台帳行の着手条件を全部写した |
| 再確認・15 (§11.1 (ii) の 1 instance 条件) | 直した (RC-15) | 条件を付けた |
| 再確認・16 (§4 が Q-4 の (c) を先に閉じる) | 直した (RC-16) | (a)(b) に限定 |
| 再確認・17 (O-4a の Evidence が in-process を含む) | 直した (RC-17) | wire に |
| 再確認・18 (O-11 の part 長。不確実) | 直した (RC-18。両論を註に。確定は設計レビュー 2) | SDK の part 長は未確認 |
| 再確認・19 (Q-1 の 1.x.0 の論証。不確実) | 直した (RC-19) | spec :36 に照らした 1 行。major と読む余地は依頼者 |
| 再確認・20 (:277 の「未定」の説明) | 直した (RC-20) | 経緯の記述に |
| 再確認・21 (O-18 の空振り。観察) | 直した (RC-21) | 監査 event の観測を必須に |
| 設計レビュー 2 A・1 / A・3 / B・9 (router が A-1 の目的と SI-00 を迂回。R-30 の文の自己矛盾。router の検査順・監査・rpm) | 推奨で進める (Q-7) + 直した (N-19) | router を前段と同格の基盤部品とし SI-00 の残余として CONTROL_MAPPING に記録 + 要件を列挙。依頼者指示「全て監督推奨で進めてください」を本件にも及ぶと読んだ (監督の読み) |
| 設計レビュー 2 A・2 ((ii) の concurrency の見立てが裁定 27・28 と両立しない) | 推奨で進める (Q-8) | object-capable な配備では `concurrency` を deployment_required と宣言 (正直な宣言) |
| 設計レビュー 2 A・4 / B・6 / A・5 / B・2 の header 部分 (分類文に client 側の成功条件が無い。%2F。1.14.0 (a) が改版対象に無い。response_headers) | 直した (N-3) | 分類文を 1 文に統合、version_binding (a) を改版対象に、raw_path 照合、response_headers |
| 設計レビュー 2 B・2 (操作カタログで bytes を表せない。null schema = 本文なし) | 直した (N-4) | request_media_type / response_media_type / request_headers の形の案。確定は契約改版 WP |
| 設計レビュー 2 B・3 / A・15 / B・4 (object_id の構文が identifier 構文と衝突。MitateDB は IDENTIFIER_INVALID を出さない) | 直した (N-5) | identifier 構文に収まる `o_` + base32 に確定。code は既存の許容集合 |
| 設計レビュー 2 B・5 (violated_declaration の語の使い方) | 直した (N-6) | Idempotency-Key の長さ違反は request_schema、新語 3 つの定義文、基準、pin の更新を契約 WP に |
| 設計レビュー 2 A・10 (replay の X-Request-Id の意味が既存と衝突) | 推奨で進める (Q-9) | header は常にその要求自身の値 (既存挙動)。B-3 の範囲は object_storage の 4 操作の全応答 |
| 設計レビュー 2 A・6 / A・7 / A・8 / B・8 の一部 (未読本文と Connection: close、認証前の読み取り、nginx buffering、到達しない Content-Length 行) | 直した (N-7) | 認証の前後を問わず close、object 経路は認証前に 0 octet、nginx 設定の註、2 行に「契約上の code は無い」 |
| 設計レビュー 2 A・9 / B・13 (idempotency_entries の評価時点、「高々 1 つが実行」、capability idempotency との関係) | 直した (N-8) | tx1 で予約、available への遷移を実行と数える案、requires_capability に idempotency |
| 設計レビュー 2 A・11 (Content-Disposition の header injection) | 直した (N-9) | `"` `\` `;` を置換対象に |
| 設計レビュー 2 A・12 / B・1 (execution_ms 1 つで転送時間を縛れない。仮の起点) | 推奨で進める (Q-6) | 転送専用 class `object_transfer_ms` を 1 つ足す (B-5 を超えるが加算的。R-42 と独立) |
| 設計レビュー 2 A・13 / B・8 (O-13 の空振り・誤判定。upload 側の失効条件が無い) | 直した (N-11) | 陽性対照とサーバ側の終了判定、O-27 |
| 設計レビュー 2 A・14 / B・7 (O-24 の変異が等価) | 直した (N-12) | 変異を差し替え、入力に大小・parameter 付きを足す |
| 設計レビュー 2 A・16 (削除の存在検査と確認の順) | 直した (N-13) | NOT_FOUND を confirmation より先 |
| 設計レビュー 2 A・17 (Cache-Control。不確実) | 直した (N-14) | private, no-store, no-transform。共有 cache は未確認 |
| 設計レビュー 2 A・18 / B・12 (Q-5 の hard quota。不確実) | 直した (N-15) | §8 に hard な bound を必須、CONTROL_MAPPING の SI-08 行に残余 (作業機) |
| 設計レビュー 2 A・19 (O-6 の ABSENT が空振り) | 直した (N-16) | 観測を octet 数 0 と 100 Continue 不送出に、ABSENT の plug 構成を必須 |
| 設計レビュー 2 A・20 / B・10 (obligations と O-n の対応、§2.1 の欠け) | 直した (N-17) | version_binding の文と 1 対 1、peer-local は CONTROL_MAPPING へ |
| 設計レビュー 2 B・8 (検査順の条件、4 class の境界、17 の pin) | 直した (N-18) | O-28、C-05 の条件付き集合、pin を改版対象に |
| 設計レビュー 2 B・11 (bound が deployment に 1 つ。低) | 直した (N-20。両論を註に) | 宣言は上限なので真。操作別 bound は採らない |
| 設計レビュー 2 B・14 (O-26 の参照漏れ) | 直した (N-21) | 反映先に足した |
| 設計レビュー 2 A / B 共通 (RC-18 の見立て) | 直した | 偽 provider を storage adapter の境界に置き O-11 は wire のまま。契約に B の定数は置かない |
| 設計レビュー 2 (uvicorn / starlette の挙動) | 観察 | 本環境のソースで確認、実行は未確認。nginx・provider・RFC は未確認 |
| 再確認 2・1 / 3 (router の lookup 失敗の扱い。bearer の hash と pepper) | 直した (RC2-1 + RC2-3) | credential_id (locator) の射影だけ、pepper・verifier を持たない。lookup 失敗は JSON process の通常認証、専用単位の無い application は CAPABILITY_UNSUPPORTED、本文は 0 octet |
| 再確認 2・2 (C-05 の仕組みの誤記。metadata_bytes / rpm の境界条件が無い) | 直した (RC2-2) | V1 (e) の集合と V2 の driver を分けて書き、O-29・O-30 |
| 再確認 2・4 (Q-6 (c) が Q-3 (甲) を改める。手続き) | 直した (RC2-4) | 食い違いの欄に明記し、契約改版 WP の着手前に依頼者の確認を得る行 |
| 再確認 2・5 (object_id の構文が identifier 構文より狭く peer が分かれる。Crockford の別名) | 直した (RC2-5) | 正規表現と文字列完全一致、identifier_syntax の定義の改版 |
| 再確認 2・6 (予約が未定義) | 直した (RC2-6) | key を持つ pending 行、重複を除いて数える |
| 再確認 2・7 (O-24 の peer 側変異が死なない) | 直した (RC2-7) | Content-Type 一致の観測を O-10 に |
| 再確認 2・8 (O-27 の観測が実行できない) | 直した (RC2-8) | 偽 provider の状態を読む method で観測 |
| 再確認 2・9 (object_transfer_ms の宣言と lock 待ちの limit_class) | 直した (RC2-9) | reference_wall_clock、lock 待ちも object_transfer_ms、§8、下限 |
| 再確認 2・10 (Q-8 の宣言の導き方) | 直した (RC2-10) | process_ceilings.data に専用単位を含め裁定 27 の写像から機械的に |
| 再確認 2・11 (`*/*` が wildcard 拒否とぶつかる) | 直した (RC2-11) | 構造値の形に |
| 再確認 2・12 (X-Request-Id と契約外 400) | 直した (RC2-12) | application が組む全応答に限定 |
| 再確認 2・13 (新語の基準の矛盾) | 直した (RC2-13) | 基準を 3 つの header に限定 |
| 再確認 2・14 (印・§12 の行・N-13 の出所と replay 先行) | 直した (RC2-14) | :716 と replay 先行を足した |
| 再確認 2 (uvicorn の 100 Continue / 400 の挙動) | 観察 | 再確認の環境では未検証。1 巡目 A は本環境のソースで確認、実行は未確認 |

## 7. 作業機の追記 (2026-10-02) — provider / RFC / nginx の公式文書の確認

本書 §3 の【更新 2026-10-02】の 7。設計 v0.5 が「未確認」と書いた 33 行を 35 件にまとめ、調査担当 (general-purpose、Sonnet、読み取り専用) が公式文書で確かめた結果である。次の契約改版の作業指示書の材料であり、設計は改版していない (設計 §5 の表の「確認済み / 未確認」列の更新は v0.6 以降)。

- 限界: 取得は WebFetch (ページを要約して返す方式) で、要旨は取得結果の言い換えであり原文の通読ではない。**監督は原文で再確認していない。** 作業指示書に載せる件は、載せる前に原文で確かめる (特に下の表の 2・19・32・33)。
- 「設計の行」は設計 v0.5 (`docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`、1026 行) の行番号、O-n・N-n は設計の局所 ID である。
- 公開値スキャナ (`tools/public_value_scan.py`) は実 host 名を拒むので、根拠は URL ではなく「文書の置き場: path」の形で書く (置き場 = Cloudflare docs / Google Cloud docs / RFC Editor / IETF datatracker / IETF archive / nginx docs / nginx trac / nginx ML。各 provider・団体の公式文書の site)。
- 判定の凡例: 確認済み = 設計の記述どおり / 食い違い = 設計の記述または前提と公式文書が違う / 見つからず = 読んだ範囲に記述なし / 対象外。
- 裁定 (`OC` §1.15 の 77): 食い違い 3 件 (2・19・32) と見つからず 7 件は観察とし、起票しない (設計は候補で何も宣言しておらず、DB の利用者は気づかない。契約改版の作業指示書の起草時に設計 v0.6 の【訂正】として扱う)。

### 判定の集計

| 判定 | 件数 | 番号 |
| --- | --- | --- |
| 確認済み | 23 | 1, 3, 4, 5, 7, 9, 11, 12, 13, 14, 15, 16, 18, 20, 22, 23, 25, 26, 27, 28, 29, 31, 33 |
| 食い違い | 3 | 2, 19, 32 |
| 見つからず | 7 | 6, 8, 10, 17, 21, 24, 30 |
| 対象外 | 2 | 34, 35 |
| 読めず (主張ではなく URL 単位) | 下の「読めなかった URL」 | |

### 結果の表

| 番号 | 設計の行 | 主張 | 判定 | 根拠 URL | 要旨 |
| --- | --- | --- | --- | --- | --- |
| 1 | 522, 532 | R2: 当該 bucket 以外への操作を provider が拒否する credential を発行できる (bucket 単位の API token) | 確認済み | Cloudflare docs: /r2/api/tokens/ , Cloudflare docs: /r2/api/s3/tokens/ | Object Read & Write / Object Read only を選ぶと token を指定した bucket の集合に絞れる。account 全体の token と bucket 限定の token がある。他 bucket が拒否される挙動そのものの記述は読んだ範囲に無い (絞れることまでが文書の記述)。 |
| 2 | 523, 532, 531 (旧文の「GetObject/PutObject/DeleteObject 以外を拒否」) | R2: token の粒度が操作単位 (get / put / delete) まで絞れる | 食い違い | Cloudflare docs: /r2/api/tokens/ , Cloudflare docs: /r2/api/s3/temporary-credentials/ | 恒久 token の permission は 4 種 (Admin Read & Write / Admin Read only / Object Read & Write / Object Read only) の group 単位で、操作単位の絞りは無い。Object Read & Write は「read, write, list objects」で、list と multipart 系も入る。操作単位 (`actions`) の絞りは temporary credentials にあるが、文書は「local signing のみ、API は coming soon」とする。bucket 単位の主張 (行 1) は成り立つが、3 操作だけに限る主張は恒久 token では成り立たない。 |
| 3 | 533 (§5.1 の親 token の段落) | R2: temporary credential を bucket にしか届かない親 token から発行できる | 確認済み | Cloudflare docs: /r2/api/s3/temporary-credentials/ , Cloudflare docs: /api/resources/r2/subresources/temporary_credentials/methods/create/ | temporary credential は親 token の access key から派生し、1 bucket に束縛され、prefixes / objects でさらに絞れる。permission は admin-read-write / admin-read-only / object-read-write / object-read-only。TTL は最大 604800 秒 (7 日)。 |
| 4 | 524, 537 | R2: 条件付き PUT で既存 key の上書きを防げる | 確認済み | Cloudflare docs: /r2/api/s3/api/ , Cloudflare docs: /r2/platform/release-notes/ , Cloudflare docs: /r2/api/error-codes/ | S3 互換表の PutObject に If-Match / If-None-Match / If-Modified-Since / If-Unmodified-Since が対応済みとある。release notes (2022-05-27) は、UploadObject / CreateMultipartUpload に条件 header を付け条件が満たされないとき 412 を返すと記す。同 (2022-07-30) は If-Match / If-None-Match が ETag の配列・weak ETag・ワイルドカード `*` に対応と記す。error code 10031 は PreconditionFailed (412)。PutObject の表自体には `If-None-Match: *` の create-only の明記は無い (根拠は release notes)。Workers API の put() は条件不成立で null を返す。 |
| 5 | 506, 525, 536 | R2: 未完了 multipart upload を abort できる | 確認済み | Cloudflare docs: /r2/objects/multipart-objects/ , Cloudflare docs: /r2/buckets/object-lifecycles/ , Cloudflare docs: /r2/api/s3/api/ | S3 の AbortMultipartUpload が実装済み (未対応は x-amz-request-payer のみ)。未完了 upload は既定で 7 日後に自動 abort され、lifecycle rule (AbortIncompleteMultipartUpload) で日数を変えられる。 |
| 6 | 536 | R2: cleanup worker が abort に要る権限の粒度 | 見つからず | Cloudflare docs: /r2/api/tokens/ , Cloudflare docs: /r2/api/s3/temporary-credentials/ | 恒久 token の文書に permission と S3 操作の対応表は無い。temporary credentials の文書は操作を Read / Write / Multipart に分けて列挙し、Multipart に AbortMultipartUpload、Read に ListMultipartUploads を置くが、object-read-write がそれらを含むとは明記していない (「read, write, and list objects」とだけある)。推測では埋めない。 |
| 7 | 506, 525, 546 | GCS: resumable session を破棄できる | 確認済み | Google Cloud docs: /storage/docs/performing-resumable-uploads , Google Cloud docs: /storage/docs/resumable-uploads | session URI への DELETE で取り消す (JSON API は 499、XML API は 204 を返す)。session URI は 1 週間で失効する。完了した upload だけが bucket に現れる。 |
| 8 | 546 | GCS: resumable session の破棄に要る IAM 権限 | 見つからず | Google Cloud docs: /storage/docs/resumable-uploads , Google Cloud docs: /storage/docs/access-control/iam-permissions | 破棄に要る IAM 権限の記述は無い。文書は session URI が認証 token として働き、要求に署名が要らないと述べる。XML API の multipart abort には `storage.multipartUploads.abort` が対応表にあるが、設計の resumable 経路ではない。 |
| 9 | 524, 545 | GCS: generation precondition (`ifGenerationMatch=0`) で上書きを防げる | 確認済み | Google Cloud docs: /storage/docs/request-preconditions , Google Cloud docs: /storage/docs/json_api/v1/objects/insert | `ifGenerationMatch=0` は live な版が無いときだけ成功し、不成立は 412。objects.insert は `uploadType=resumable` でも使えるが、resumable では初回の POST で指定し、後続の PUT では無視される。XML API の multipart upload では precondition が使えず 400 NotImplemented。上書きには `storage.objects.create` と `storage.objects.delete` の両方が要る (iam-permissions と insert の文書)。 |
| 10 | 545 | GCS: resumable で precondition が評価される時点 (開始時か、完了時か) | 見つからず | Google Cloud docs: /storage/docs/request-preconditions , Google Cloud docs: /storage/docs/xml-api/post-object-resumable , Google Cloud docs: /storage/docs/json_api/v1/objects/insert | 評価時点を述べる記述は無い。分かるのは「初回 POST で指定でき、後続 PUT では無視される」ことまで。開始から完了までの間に別の書き込みが入る場合の挙動は文書から導けない。 |
| 11 | 522, 543 | GCS: bucket 単位の service account と Uniform bucket-level access | 確認済み | Google Cloud docs: /storage/docs/uniform-bucket-level-access | 有効にすると bucket 内の資源の ACL が無効になり、アクセスは IAM だけで付与される。IAM policy は bucket 資源に直接置ける (bucket に対する IAM conditions も同じ前提)。 |
| 12 | 523 | GCS: IAM で操作単位 (get / put / delete) まで権限を絞れる | 確認済み | Google Cloud docs: /storage/docs/access-control/iam-permissions | 権限は `storage.objects.get` / `create` / `delete` / `list`、`storage.multipartUploads.create` / `abort` / `list` / `listParts` のように操作別で、custom role で組める。上書きは create と delete の両方が要る。 |
| 13 | 526, 545, 569 | Cloud Run の front end の要求本文上限 | 確認済み (値が分かった) | Google Cloud docs: /run/quotas , Google Cloud docs: /run/docs/configuring/http2 | HTTP/1 の要求は 32 MiB まで、HTTP/2 server なら上限なし (文書の注記)。応答は HTTP/1 で 32 MiB (chunked か streaming を使わないとき)。Cloud Run は既定で HTTP/2 を HTTP/1 に落とし、end-to-end HTTP/2 (h2c) を有効にしたときだけ container へ HTTP/2 で渡す。設計への含意: h2c を有効にしない配備では `object_bytes` は 32 MiB 以下が要る。超過時の status code の記述は無い。 |
| 14 | 526, 545 | Cloud Run の要求時間上限 | 確認済み (値が分かった) | Google Cloud docs: /run/docs/configuring/request-timeout , Google Cloud docs: /run/quotas | 既定 5 分、最大 60 分。要求と応答の全体に掛かり、超過すると接続が閉じられ 504。timeout 後も container は終了しない。 |
| 15 | 569 | nginx の `client_max_body_size` (既定、超過時の挙動) | 確認済み | nginx docs: /en/docs/http/ngx_http_core_module.html , nginx trac: /nginx/ticket/1642 | 既定 1m。Content-Length が超えると 413。0 で検査を無効にする。chunked 本文への適用は core module の文書に明記が無い。nginx 開発者は ticket 1642 (wontfix) で、本文を buffer するかどうかに関わらず常に検査すると述べる (project の ticket であって nginx docs の仕様文書ではない)。 |
| 16 | 570 | nginx の `proxy_request_buffering off` / `proxy_buffering off` | 確認済み | nginx docs: /en/docs/http/ngx_http_proxy_module.html | `proxy_request_buffering off` は本文を受け取りながら直ちに upstream へ送る。ただし本文送信を始めた後は次の upstream へ回せない。HTTP/1.1 chunked の要求本文は、proxy に HTTP/1.1 か HTTP/2 を使わない限り directive に関わらず buffer される。`proxy_buffering off` は応答を同期的に client へ流し、nginx は `proxy_buffer_size` 分だけ読む (X-Accel-Buffering で上書き可)。`proxy_http_version` の既定は文書上 1.1 (1.29.7 から、それ以前は 1.0) なので、古い版では明示が要る。 |
| 17 | 264, 345, 570, 652 | nginx が `Expect: 100-continue` をどう扱うか | 見つからず (nginx docs の文書に記述なし) | nginx docs: /en/docs/http/ngx_http_core_module.html , nginx docs: /en/docs/http/ngx_http_proxy_module.html。参考 (仕様文書ではない): nginx ML: /pipermail/nginx/2012-November/036334.html , nginx trac: /nginx/ticket/493 , nginx ML: /pipermail/nginx/2021-May/060643.html | core module と proxy module の文書に Expect / 100-continue の記述は無い。nginx project の ML と ticket では、開発者が (2012-11-17) nginx は 100 Continue を自分で返し、`client_max_body_size` の検査より先に返すので、後で 413 になる場合も 100 を避けられないと述べる。ticket 493 は wontfix (2014 年に close) で、nginx が 100 を upstream に委ねず自分で返すという報告。2021-05-01 の ML では upstream への要求に Expect を使わないと述べる。これらは 5 年から 14 年前の発言で、現行版の挙動を保証しない。設計の「認証後にしか 100 を返さない」(O-15) は nginx 経由では観測できない可能性がある、という点は作業指示書で扱うべき (実測が要る)。 |
| 18 | 336 | RFC 9530: 未対応 algorithm の member の扱い | 確認済み | RFC Editor: /rfc/rfc9530.html , RFC Editor: /rfc/rfc9530.txt (RFC 9530, 2024) | Content-Digest は Dictionary で、key が algorithm、値が byte sequence (§2)。受信側は digest の一部または全部を無視してよい (§2)。送信側は相手の対応を知らずに送ってよい (§2)。実装は検証する algorithm の種類・個数・大きさを制限してよい (§6.7)。登録簿では sha-256 と sha-512 が Active、md5・sha・unixsum・unixcksum・adler・crc32c は Deprecated。不一致時の応答 code は規定されず、アプリケーションの方針に委ねられる。設計の「他の member は無視、sha-256 が無ければ `VALIDATION_FAILED`」は RFC に反しない (後半は設計側の方針)。 |
| 19 | 299 | IETF Idempotency-Key 草案の値の書式 | 食い違い (設計の判断が草案と違う) | IETF datatracker: /doc/draft-ietf-httpapi-idempotency-key-header/ , IETF archive: /archive/id/draft-ietf-httpapi-idempotency-key-header-07.txt | 最新版は draft-ietf-httpapi-idempotency-key-header-07 (2025-10-15。datatracker 上は Expired、RFC 化されていない)。§2.1 で値は RFC 8941 の Item Structured Header の String (sf-string) で、例は引用符付き。§2.2 で key は一意で、別 payload で再利用してはならず、UUID 等の無作為な識別子が推奨される。長さの上限の規定は無い。設計は引用符を外さず値の一部として扱う (最大 128 octet) ので、草案どおりに引用符付きで送る client の key は引用符込みの文字列になる。草案のエラー対応: 欠落 400 / 同 key 別 payload 422 / 処理中の再送 409。 |
| 20 | 313, 322, 330 | RFC 8187 / RFC 6266 の挙動 (`filename*`、UTF-8、優先順位、path 情報) | 確認済み | RFC Editor: /rfc/rfc8187.txt (2017) , RFC Editor: /rfc/rfc6266.txt (2011) | RFC 8187 §3.2: 受信側は UTF-8 に対応しなければならず、ext-value は `charset'language'value` で、attr-char 以外は percent-encode (§3.2.1)。不正な escape や復号できない octet に頑健に対処すべきで、parameter の無視・除去・U+FFFD への置換が許される。RFC 6266 §4.3: `filename*` と `filename` が両方あれば `filename*` を優先する。filename の folder 情報を信用せず、`\` と `/` で区切った最後の segment だけを使う。§4.2: `attachment` は保存を促す意味。設計の表の「両方あれば `filename*` を採る」「パス区切りを置換」はこれと整合する。「`filename*` の charset が UTF-8 以外なら `VALIDATION_FAILED`」は設計側の方針 (RFC 8187 は UTF-8 の対応だけを必須とする)。 |
| 21 | 330 (N-9) | download の `Content-Disposition` の `filename=` を quoted-string にし `"` `\` `;` と制御文字を `_` に置換する | 見つからず | RFC Editor: /rfc/rfc6266.txt | 取得結果に quoted-string の文法 (どの文字をどう escape するか) の記述が出なかった。取得結果は RFC 6266 が RFC 2616 より token 形式も許すこと (Appendix A) までしか示さない。置換方針は安全側の設計判断で、RFC の文法との突き合わせは未了。 |
| 22 | 352 | HTTP/1.1: header 送出後の失敗では宣言長未満で切断し、受信側は不完全と判定する | 確認済み | RFC Editor: /rfc/rfc9112.html (RFC 9112, 2022) | §6.3: Content-Length を持つ message が宣言長未満で閉じられたら、受信側は不完全とみなし接続を閉じなければならない。§8: 受信した本文が Content-Length 未満なら不完全で、client は不完全として記録しなければならない。chunked は終端の 0 長 chunk が無いと完了しない。設計の「chunked の正常終端を送らない」と整合する。 |
| 23 | 352 | HTTP/2: 応答を途中で打ち切るのに RST_STREAM を使う | 確認済み | RFC Editor: /rfc/rfc9113.html , RFC Editor: /rfc/rfc9113.txt (RFC 9113, 2022) | §6.4: RST_STREAM は stream の即時終了を表し、取り消しまたはエラーの通知に使う。error code (INTERNAL_ERROR / CANCEL 等) の使用を禁じる記述は無い。§8.1.1: DATA frame の payload 長の合計と Content-Length が一致しない message は malformed (stream error PROTOCOL_ERROR)。 |
| 24 | 352 | HTTP/2: RST_STREAM で終わった応答を受信側が不完全として扱う | 見つからず | RFC Editor: /rfc/rfc9113.html , RFC Editor: /rfc/rfc9113.txt | 取得した §6.4・§8.1 の要旨に、END_STREAM 前に RST_STREAM で終わった応答を不完全と扱う規範は出なかった。§8.7 (Request Reliability) は取得結果に全文が入らず読めていない。設計の「client は受信長 = Content-Length かつ digest 一致のときだけ成功とする」は RFC に依らず client 側義務として書かれているので、この規範が無くても設計は成り立つ。 |
| 25 | 356 | 共有 cache と `Cache-Control: private, no-store, no-transform` | 確認済み | RFC Editor: /rfc/rfc9111.html (RFC 9111, 2022) | §5.2.2.5 no-store: cache は要求と応答のどの部分も保存してはならない (private / shared の両方)。§5.2.2.7 private: shared cache は保存してはならない。§5.2.2.6 no-transform: cache を持つかどうかに関わらず中継者は内容を変換してはならない。no-store だけで shared cache の保存を防ぐのに足りる。実在の shared cache 製品の挙動は仕様の範囲外で、読んでいない。 |
| 26 | 110, 696 | R2: provider 側の hard quota の有無 | 確認済み (hard quota は無い) | Cloudflare docs: /r2/platform/limits/ | 「Data storage per bucket」「Number of objects per bucket」はともに無制限と表にある。上限の表にあるのは object 1 個 5 TiB、単一 PUT 5 GiB、multipart 最大 4.995 TiB、10,000 part、同一 object への同時書き込み毎秒 1 件、bucket 管理 毎秒 50 件など。総保存量の上限は provider 側に無いので、設計の「実装側の検査を必須にする」は必要な手当てになる。 |
| 27 | 110, 696 | GCS: provider 側の hard quota の有無 | 確認済み (hard quota は無い) | Google Cloud docs: /storage/quotas | bucket あたりの保存量に上限は無い (zonal bucket は project 全体で zone あたり 1 TB 既定という別の制約がある)。同一 object 名への書き込みは毎秒 1 回。object 最大 5 TiB。予算 alert の仕組みは読んでいない。 |
| 28 | 670 | R2 の multipart の part 長 | 確認済み | Cloudflare docs: /r2/objects/multipart-objects/ , Cloudflare docs: /r2/platform/limits/ | 最小 5 MiB (最後の part を除く)、最大 5 GiB、最大 10,000 part。最後を除いて全 part が同じ大きさでなければならない。 |
| 29 | 670 | GCS の chunk 長 | 確認済み | Google Cloud docs: /storage/docs/performing-resumable-uploads , Google Cloud docs: /storage/docs/resumable-uploads , Google Cloud docs: /storage/docs/multipart-uploads | resumable の chunk は 256 KiB の倍数 (最後の chunk を除く)。XML API の multipart の part は 5 MiB から 5 GiB (最後を除く)。 |
| 30 | 670, 518 | SDK が実際に溜める上限 B (SDK の既定の part 長・buffer) | 見つからず | (一次資料の対象 domain 外のため未調査) | 設計が指す SDK (S3 互換 client、GCS client) の既定値は、依頼の一次資料の範囲 (Cloudflare・Google Cloud・IETF・nginx) に無い。provider の下限と上限は行 28・29 のとおり。SDK ごとの既定は実装時に SDK の版を決めて確かめる事項。 |
| 31 | 592, 814 | Cloud Run: service が複数なら複数 host になる | 確認済み | Google Cloud docs: /run/docs/triggering/https-request | service ごとに固有の run.app の URL (host) を持つ。custom domain を別に割り当てることもできる。 |
| 32 | 592, 814 | Cloud Run: 最大 instance 1 で「専用単位は 1 instance」とみなせる (自動 scale の挙動) | 食い違い (一部) | Google Cloud docs: /run/docs/configuring/max-instances , Google Cloud docs: /run/docs/about-instance-autoscaling | 最大 instance は 1 に設定できる (既定は revision あたり 100)。ただし文書は、この上限が traffic の急増などで短時間超えうると述べ、例外的な状況では scale を絞ることもあるとする。deploy や急増時は、上限を超えた instance が最大 15 分、または request timeout の値まで in-flight の要求のために残りうる。traffic splitting では上限が revision に按分される。したがって「最大 1 なら必ず 1 instance」は保証されない。`object_transfers` が `enforced` になる条件 (専用単位が 1 instance) を Cloud Run で満たすかは、この点の扱い次第。 |
| 33 | 264, 345, 652 | RFC 9110 §10.1.1: `Expect: 100-continue` を認証と検査の後まで返さない | 確認済み (設計の行は未確認と書いていない) | IETF datatracker: /doc/html/rfc9110 (RFC 9110, 2022) | §10.1.1: 100-continue の期待を受けた server は 100 の中間応答か最終 status を返す。本文を受け取る前に最終 status を返して接続を閉じてよい。100 を返さなくてよい。proxy は Expect を転送する。取得結果は要約で、全文は読めていない (RFC Editor の html は §5.5 で切れ、datatracker の取得で補った)。 |
| 34 | 882 | OS 側で user を揃えると単位間の分離が弱まる点の塞ぎ方 | 対象外 | — | provider・RFC・nginx の挙動ではなく、設計内の OS user 設計の問い。 |
| 35 | 399, 445, 467, 1026 | uvicorn / starlette の実行時挙動 (最初の receive での 100 Continue、`Content-Length` 不正値への 400) | 対象外 | — | 依頼で対象外とされた。本文書は install 済みのソースを読んで確認し、実行は未確認と書いている。 |

### 読めなかった URL / 経路

- `Google Cloud docs (旧 host): /storage/docs/...` は 301 で `Google Cloud docs: /storage/docs/...` に移る。上の表は移動先で読んだ。
- `Google Cloud docs: /storage/docs/quotas` は 404。`Google Cloud docs: /storage/quotas` で読んだ (行 27)。
- `Google Cloud docs: /storage/docs/xml-api/put-object-resumable` は 404 (読めず)。
- `RFC Editor: /rfc/rfc9110.html` と `rfc9110.txt` は取得結果が長さで切れ、§10.1.1 と §8.6 の本文に届かなかった。§10.1.1 は `IETF datatracker: /doc/html/rfc9110#section-10.1.1` で読んだ (行 33)。§8.6 は読めていない。
- Cloudflare R2: 恒久 token の permission と S3 操作の対応表は、読んだ文書のどこにも無かった (行 6)。

### 作業指示書の材料としての要点 (判断は含めない)

- 設計の前提を変える可能性があるもの: 行 2 (恒久 token は操作単位に絞れない。絞れるのは temporary credentials の `actions` で、文書上は local signing のみ)、行 19 (草案は sf-string)、行 32 (最大 instance 1 は保証でない)。
- 設計の想定が検証を要するもの: 行 17 (nginx 経由で 100 Continue の送出時点が観測できるか。nginx 側の挙動は project の ticket と ML にしか記述が無く、実測が要る)、行 10 (GCS の precondition の評価時点)。
- 値が決まったもの: Cloud Run の本文上限 (HTTP/1 は 32 MiB、HTTP/2 end-to-end は上限なし) と要求時間 (既定 5 分、最大 60 分)、R2 / GCS の part・chunk 長、provider 側に hard quota が無いこと。
