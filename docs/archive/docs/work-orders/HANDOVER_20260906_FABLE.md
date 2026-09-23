# 引き継ぎ — 2026-09-06 (第14次。フェーズ7 — 証拠・再現性・公開準備。契約は 1.6.0 のまま無変更)

- **本書は第 14 次のうち「フェーズ7 側」である。** **同じ第 14 次に `docs/work-orders/HANDOVER_20260905_FABLE.md` (Q4 フェーズ側) があり、両者は別冊である** — Q4 とフェーズ7 は別セッションで並行して走り、Q4 が先に main へ入った。**Q4 側の到達状態・裁定 (U-1〜U-3)・台帳 (LQ4-*) は Q4 側の第 14 次が正本であり、本書は複製しない。** 本書が上書きするのは**現在地 (main) とフェーズ7 の状態**である。
- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第13次 `HANDOVER_20260904_FABLE2.md` の約束事は全て継続**する (§2 到達した状態、§3 クライアント連携、§4 の次の一手と運用規律、§5 教訓)。**Q4 側の第 14 次 `HANDOVER_20260905_FABLE.md` の約束事も全て継続**する。そのさらに前の引き継ぎも全て継続。**現在地のみ本書が上書きする**
- 本書は**フェーズ7 (証拠・再現性・公開準備) の WP-1〜WP-8 を完了したセッションの記録**である。**契約 `1.6.0` は 1 バイトも変えていない** (設計 §2 の C1)。**新しい Security Invariant も足していない** (C2)。**実機適用は未実施であり、クライアント一報も送っていない** (方針不変)

## 1. 現在地 (main)

**フェーズ7 は WP-8 (記録整理) をもって 7-A / 7-B を閉じた。残るのは WP-9 公開ゲートだけであり、その着手条件は依頼者の実行合図である。**

| コミット (merge) | WP | 内容 | root suite (単独実行) |
|---|---|---|---|
| `8c982eb` | WP-0(docs) | 設計 v1.2 + 作業指示書 v1.0/v1.1 | 文書のみ |
| `56f100e` | WP-0(裁定) | (α)(β)(γ) の確定記録 + 7-A 前倒し | 文書のみ |
| `dd08594` | WP-3 | **(h) r2db 配備資産** (control unit / nginx `location /control/v1/` / operator script 3 本 / runbook §7) | CI で評価 (7-A) |
| `448c660` | WP-1 | **(g) 公開規律とスキャナ** (`public-repository-policy.md` / `tools/public_value_scan.py` / `.pre-commit-config.yaml`) | 同上 |
| `50c307f` | WP-2 | **(b)(i)(ii) constraints と CI** (`constraints.txt` / `.github/workflows/ci.yml`) | **1868 / 0 / 0 / 4 xfailed** (CI 3.11 job、run 33962523499) |
| `b3bf310` | 7-A 記録 | 設計 §13 + 台帳 L7-14〜L7-17 + 作業指示書 v1.2 + 第13次 §4-2 | 文書のみ |
| `1c31655` | (前提) | **main の CI 緑化** (Q4 由来テスト 2 件の小修正) | **2165 / 0 / 0 / 0** (CI 3.11 job) |
| `a4d5b3a` / `c25b1ed` | (前提) | **LQ4-24 追補** (r2db 配備資産の Q4 追随) | **2165** のまま |
| `9ab4245` | WP-4 | **(a) C-05 の共通化 + (e) 隔離 surface の資源検査**、port v1.11 | **2214 / 0 / 0 / 9 xfailed** |
| `0650855` | WP-5 | **(a) C-00 / C-02 / C-04 / C-07 / C-10 の共通化 + conformance の資源管理** | **2250 / 0 / 0 / 9 xfailed** |
| `a090e80` | WP-6 | **(b)(iii) `DeprecationWarning` の error 化と `httpx2` 採用** | **2252 / 0 / 0 / 9 xfailed** |
| `1656ad3` | 7-B 記録 | 設計 §13 / §11 + 作業指示書 v1.3 | 文書のみ (**2252** のまま) |
| `b2f9224` | WP-7 | **(i) 現行結論と履歴の分離** (companion 2 本 + 現行行化 + 更新規約 + register テスト) | **2265 / 0 / 0 / 9 xfailed** — main CI run 34025563291 緑、3.11 `2265 passed, 9 xfailed` で 4 数一致 |
| `(本記録の merge。ハッシュは次回引き継ぎ §1 に記載)` | WP-8 | 記録整理 (設計 §10 / §11 / §13、作業指示書 v1.4、フェーズ6 §11 L6-20、第13次 §4-2、本書) | 文書のみ (**2265** のまま) |

**集計行の出所**: **7-A は CI の 3.11 job の集計行が正本である** — 3 WP とも root `pyproject.toml` の `testpaths` の外しか触っておらず、収集対象不変を `--collect-only` **1872 件** の一致で確認したうえで正本を CI へ移した (設計 §13.1、L7-17)。**7-B は監督がローカルで単独実行した完了ゲートが正本である** (`{scratchpad}/wp4-gate.log` / `wp5-gate.log` / `wp6-gate.log` / `wp7-gate.log`)。**WP-7 の最終ゲートは `2265 passed, 9 xfailed, 5 warnings in 150.20s (0:02:30)`** である。**CI との突合は WP-4 のマージ後 (`9ab4245`) と WP-5 / WP-6 のマージ後 (`a090e80`) で行い、4 数 (passed / failed / skipped / xfailed) がローカルと一致した。** **WP-7 のマージ後 (`b2f9224`) の CI run は本書の執筆時点では未確認であり、次に main の CI を見たときに 4 数の一致を突き合わせること** (台帳 L7-6)。

**`warnings` の数は一致判定に用いない** — ローカルの `5 warnings` は共有 `.venv` に `httpx2` を入れていないことによる `StarletteDeprecationWarning` 5 件であり、**CI 側は `constraints.txt` 経由で `httpx2` が入るので 0 である**。**`StarletteDeprecationWarning` は `UserWarning` 派生**なので、WP-6 が有効化した `error::DeprecationWarning` の対象外である。

**集計行の推移はすべて新設テストの本数と一致する**: `2165 → 2214` = C-05 の新設 (+49 passed、xfailed 0 → 9)、`2214 → 2250` = 新設 5 ファイルの 9 関数 × 4 plug (+36)、`2250 → 2252` = pytest 設定の同型性テスト 2 本、`2252 → 2265` = register テスト 13 本 (新設 `test_control_mapping_register.py` 7 + `test_conditions_register.py` への追加 6)。**既存テストの挙動は 1 件も動いていない。**

正本の所在 (第13次 / Q4 側第 14 次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md`。**§3 の D-1〜D-7 が確定事項**、**§5 が依頼者裁定 1〜4 の逐語**、**§6 が (α)(β)(γ) の確定裁定の逐語**、**§9 が公開ゲートの手順 0〜7**、**§10 が WP 分割と実施状態**、**§11 が台帳 (L7-1〜L7-23)**、**§13 が実施記録 (13.1 集計行 / 13.2 WP ごとの記録)**
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md` (**v1.4**)。**§4 に訂正註 11 件**を置いた (本文の発注内容は書き換えていない)
- **公開規律の正本** = `docs/security/public-repository-policy.md` (Never publish の 6 分類 + placeholder 規約 + First-public-push gate の 8 項目)。**機械検査は `tools/public_value_scan.py`** (pre-commit の local hook と CI の scanner job の両方から呼ぶ)
- **CI** = `.github/workflows/ci.yml`。**PostgreSQL 16 を `docker run` で起動 (`max_connections=300`)、Python 3.11 / 3.12 の 2 job がともに required、正本は 3.11 job**。別 job `tally-consistency` が両 job の 4 数を突き合わせる。ほかに scanner job と deploy-assets lint job がある
- **依存の pin** = `constraints.txt` (root)。**依存を上げるときは集計行を添える** (D-3)
- **conformance の条件** = `conformance-tests/CONDITIONS.md` (**現行行のみ**) + `conformance-tests/CONDITIONS_HISTORY.md` (**履歴の逐語**)。**対応表** = `security/CONTROL_MAPPING.md` (**現行行のみ**) + `security/CONTROL_MAPPING_HISTORY.md` (**履歴の逐語**)。**port は v1.11** (`docs/design/CONFORMANCE_ADAPTER_V1.md` §21)

## 2. 到達した状態

### 2.1 7-A — 公開の準備が「規律 + 機械検査 + CI + 手順書」として揃った

- **公開規律が 1 箇所に集まった。** `public-repository-policy.md` の Never publish に**本番 hostname / cloud project 識別子 / 実 credential_id / IAM principal・e-mail / 内部トポロジ**を明記し、配備記録テンプレートに「実値は書かず対応表は運用者記録へ」の規約と凡例を置き、`INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md` の 1 行は参照化した。**規律の正本が 2 つある状態を解消した。**
- **実値パターンの機械検査が入った** (`tools/public_value_scan.py`)。**ツリーモード = `git ls-files` の対象を走査、履歴モード = `git log --all -p -m`**。**現行ツリーは 228 ファイル全規則 0 件**。**履歴側は総 flagged 1061 件** (パッチ行単位、重複を含む) であり、**この数は WP-9 の書換で 0 になる** (台帳 L7-15 が書換前の規模として記録している)。**R7 (個人名) は検査していない** — 正規表現で表現できないため、出力末尾で「検査していない」ことを毎回明示し、人手確認を §9 の手順 6.5 に残した (L7-3)。**ツリーモードは未追跡ファイルを見ない** — これは欠陥ではなく契約であり、未追跡側は pre-commit hook が担う (L7-14)。
- **CI (GitHub Actions) が成立した。** **これが本フェーズで最も効いた変化である** — それまで「実行環境が 1 台の作業機だけ」だった証拠が、**PostgreSQL コンテナ + Python 2 版の再現可能な場**を持った。**変異は CI 上で実測した** (constraints 外の import / `max_connections=100` / DSN の loopback 上書き除去 / 合成違反の投入がそれぞれ赤)。
- **r2db の配備資産がリポジトリに入った** — `r2dbsvc-control.service`、nginx の `location /control/v1/`、operator script 3 本、runbook §7 の更新。**lint は `systemd-analyze verify` / `nginx -t` / `bash -n` / `shellcheck` / `ExecStart` 非空虚の 5 検査**であり CI で走る。**合成値から書き起こしたので実機の原本との一致は保証されない** (L7-11)。
- **LQ4-24 追補** — Q4 が先に main へ入ったことで、**WP-3 が作った script が出荷翌日に古くなった**。追随は 7-A の follow-up として実施し、`part1c_declare_surfaces.sh` の新設、part2 の前提宣言による fail-closed 化、F-6 の両方向検査、廃止 env 4 変数の検査、runbook §7 の順序訂正で着地した。**「配備資産は文書と別の速度で古くなる」ことの実例である。**

### 2.2 7-B — 共通 suite が「宣言の正直さ」を測るようになった

- **C-05 (`limit_enforcement` の宣言と実挙動の一致) が共通 suite に載った** (WP-4)。**V1 = 宣言の形式と必須エントリ集合、V2 = 宣言 `enforced` の class を実際に駆動して拒否を確認、V3 = 宣言 `unavailable` の class を `xfail(strict=True)` で先置き**。**MitateDB の欠落 4 class に明示エントリを足し、宣言と検証を同一コミットに載せた** ((β) の確定どおり)。**`operation_depth` は実測で `unavailable` と判明した** — MitateDB 側に深さを計測・拒否する実装コードが 1 つも無いことを直接確認した。**xfail は 9 件**であり、**MitateDB application plane の資源上限が実装された時点で class ごとに XPASS になる**。これが **L7-1 (最優先の次フェーズ候補)** の閉止合図である。
- **他 5 条件が共通 suite に載った** (WP-5) — C-00 / C-02 / C-04 / C-07 / C-10。**あわせて conformance の資源管理が入った**: 既存テストが provision した application の残骸で共有 platform の枠が枯渇していたので、**fixture 層に teardown deprovision を置き、C-14 は隔離 surface + 既存登録数を差し引く headroom で駆動する形へ改めた**。**限度値そのものは上げていない** (制約で回避しない)。
- **`DeprecationWarning` が error になった** (WP-6)。**root と両 peer の 3 つの `pyproject.toml` に同じ 2 行を置いた** — **pytest は最寄りの inifile を採るので、peer 単体実行では root の設定が効かない**からである (設計 D-3 の「一本化 = root のみ」は誤りだった)。**同一性は `test_pytest_config_symmetry.py` が pin する。** **上流由来の 1 件 (`starlette/testclient.py` の `anyio.abc.BlockingPortal` 参照) だけをモジュール限定の狭い ignore で受けており、撤去条件は台帳 L7-19 で追跡している。**
- **現行結論と履歴が分離された** (WP-7)。**現行行 = 担保 + 証拠 + `[history]` リンク、companion = ID だけの見出し配下に原本の逐語**。**機械固定は 4 項目 + ID 重複禁止 + 単一表**であり、**セル長上限はファイル別に `CONDITIONS.md` = 3,000 / `CONTROL_MAPPING.md` = 15,200** (実測の最長は C-09 2,948 と SI-14 15,065、余裕 52 / 135)。**現行 2 ファイルは 101 KB → 51 KB / 157 KB → 88 KB になり、履歴は 1 行も捨てていない。** **SI-14 だけは目安 2,500 を大きく超えたまま監督が受理した** — この 1 行が両 peer の durable audit sink の全形状と GRANT と開示された限界を担い、詰めるには証拠か限界を捨てるしかないためである。

### 2.3 常設規律の効き方 (本フェーズでの実測)

- **「変異先行」と「主張は実測の後」が、発注文書の誤りを 5 件出した** (訂正註 7〜11)。**すべて実装物の欠陥ではない。**
- **「落ちた制約の突合を独立項目に置く」(L7-10) が実際に 8 件を拾った。** **機械的な網羅検査 (現行セル + companion の合算に対する在否) では原理的に見えない欠落**であり、**人手の二重突合 (レビューが 8 件検出 → 監査が 12 行を独立に読んで 0 件確認) が load-bearing だった。**
- **「除外が効いていることは空にする変異でしか示せない」** — WP-1 の対照実験 (placeholder 除外 OFF → 7 件、ellipsis 除外 OFF → 8 件) と WP-5 の監査変異 A (秘密 literal 集合を空にすると誰も赤にならない) が同じ形である。

## 3. クライアント連携状態

**変更なし。一報は送らない** (依頼者判断 2026-09-03 以降不変)。**本フェーズは契約に一切触れておらず、wire に現れる値も形も 1 バイトも変わっていない** — 変わったのは**証拠の置き場と検査の density、および公開の準備**だけである。第10次〜第13次 §3 と Q4 側第 14 次 §3 がそのまま有効。

**公開 (WP-9) を実行した場合にクライアント側へ影響し得る唯一の項目**は、**有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**である (**rotate は id を保持するため不可**)。**再発行までの間、既存 credential は認証を通らない。** これは公開ゲートの手順 6 であり、**依頼者の実行合図の後にしか起きない。**

## 4. 次の一手 (優先順)

### 4-1. WP-9 公開ゲート (フェーズ7 で唯一残っている WP。着手条件 = 依頼者の実行合図)

**正本は設計 §9 の手順表 (0〜7) と作業指示書 §2 WP-9 のチェックリストである。** **着手条件のうち (g)(b) の完了はすべて満たされており、待っているのは依頼者の明示の実行合図だけである。** **§6 (γ) は 2026-09-05 の依頼者裁定で案 1 に確定しているので、着手条件には残っていない。**

手順の骨子 (担当付き。詳細は設計 §9):

- **0 [依頼者]** 着手合図の確認
- **0.5 [運用者]** **すべての linked worktree を畳む** (`git worktree remove` / `git worktree prune`)。**書換後は共有ツリーの `.git/objects` への参照が不整合になるため**。**書換自体は remote から取り直した fresh clone 上で行う** — filter-repo は fresh clone を前提としており、既存作業ツリーで `--force` を使うと gc 前の object 残留を生む
- **1 [運用者] (手順書は [監督])** `git filter-repo --replace-text` による**全履歴の置換**。置換表はリポジトリ外の運用者記録の既存対応表を使う。**`git filter-repo` は作業機に未インストールなので、まず導入する**
- **2 [監督]** commit-map による**文書内 hash 参照の一括更新** (`tools/rewrite_hash_refs.py`)。対象規模は 29 ファイル・262 件の hex 様トークン (誤検出は精査で除く)。**書換後の新 commit として乗る**
- **3 [運用者]** **同名リポジトリを delete し、書換後の履歴だけを push して再作成する** ((γ) 案 1)。**全 branch・全 tag を push する**。**force push では GitHub 側に旧 commit が unreachable object として残り得る**ので、remote の object store 自体を新しくする
- **4 [監督]** **再作成後の remote から新規 clone を取り直し**、そのクローンにスキャナの履歴モードを掛けて**全規則 0 件**であること。**書換前 1061 → 書換後 0 の対比として台帳 L7-15 に引く**
- **5 [運用者]** 全 clone・worktree の作り直し (共有ツリー、`.claude/worktrees/*`、VPS 上の clone)
- **6 [運用者]** **有効 credential 2 件の revoke + 再発行** (rotate 不可)。**手順 5 の後に置いてあるのは、手順 1〜4 が失敗して巻き戻す場合に credential を失わないためである** (L7-12)
- **6.5 [運用者]** **R7 (個人名) の人手確認** — 新規 clone の `git log --all -p` に対して。対象語はリポジトリ外の運用者記録にある
- **7 [依頼者]** visibility の切替

**畳む worktree**: フェーズ7 側だけで **`phase7` / `phase7-wp2` / `phase7-wp3` / `phase7-wp4` / `phase7-wp5` / `phase7-wp6` / `phase7-wp7` の 7 本**があり、**Q4 セッションが作った worktree もあれば同じく対象である**。**実行時に `git worktree list` で実数を確認すること** — この列挙は 2026-09-06 時点の記録であって網羅リストではない。

**監督が担うのは 4 つだけである**: 手順書、commit-map 適用スクリプト、履歴スキャン、文書 hash 更新。**実行の大半は運用者作業である。** **手順 1 の後、リポジトリ外の記録が引く旧 hash はすべて無効になる** — commit-map はリポジトリ外の運用者記録に保存する (内容は文書に書かない)。


- **【追記 2026-09-08】WP-9 完了 — フェーズ7 を閉じた。** 手順 0〜6.5 を実施 (履歴書換 + 同名リポジトリの delete・再作成 + 28 branch push + 新規 clone の履歴走査 0 件 + worktree 作り直し + credential 2 件の revoke・再発行 + 対象語なし)。**手順 7 (visibility) は依頼者判断で保留** — 将来のコード譲渡・ライセンス方針を先に決めるため private を維持する。切替は fresh clone の `--history` 再確認 → Web UI の順でいつでも可能。記録は `PUBLICATION_GATE_20260906.md` §3 と設計 §13.4。
### 4-2. 依頼者判断待ちと台帳

- **(α)(β)(γ) は 3 点とも確定済みである** (依頼者裁定 2026-09-05、逐語は設計 §6)。**実施状況**: **(α)** CI の matrix 3.11 / 3.12 をともに required、正本は 3.11 job の集計行 — **WP-2 で実装済み**。実装は「食い違えば 3.12 job が赤」ではなく**別 job `tally-consistency` が両 job の 4 数を突き合わせる**形になった (監督既決、設計 §13.1 に訂正註として記載)。**(β)** MitateDB の欠落 4 class への明示エントリは WP-4 同梱 — **実施済み**。**(γ)** 手順 3 = delete + 再作成 + push、手順 4 の clone 取得元 = 再作成後の remote — **未実施 (WP-9)**。**(γ) が未確定であることを理由に visibility 切替を止める必要はもう無い** (L7-13 は裁定として閉じ、実行分だけが残っている)。
- **L7-1 【最優先の次フェーズ候補】MitateDB application plane の資源上限実装 + concurrency probe の port primitive** — **開いている**。対象 class は `execution_ms` / `concurrency` / `requests_per_minute` に加え、**WP-4 の実測で `unavailable` と確定した `operation_depth`** の 4 つ。**同時に port へ「N 個の要求を in-flight で保持したまま N+1 個目を出す」primitive を足す** — 現行 port にこれが無いことが `concurrency` を「駆動しない」に分類している唯一の理由であり、**これが入れば r2db 2 plug の差集合も同時に閉じる**。**閉止の合図は C-05 V3 の `xfail(strict=True)` 9 件が class ごとに XPASS になることであり、9 件はまだ 1 つも XPASS していない。** **本項は 3 箇所に起票済みである** (フェーズ7 設計 §11 L7-1、フェーズ6 設計 §11 L6-20 の末尾、第13次引き継ぎ §4-2)。
- **L7-2 (c) 実ソケットを持つ HTTP plug** — **開いている**。**前提だった CI は WP-2 で成立したので着手の障害は無い。** L6-12 / L6-5 の「宣言 URL の実在が load-bearing になる」性質はこの plug が入って初めて閉じる。**公開ゲートの条件ではない。**
- **L7-18 `ops verify-declarations` が両 peer に無い** — **開いている**。`ops show-declarations` は診断表示であり全経路で 0 を返すので、配備 script が起動前に確かめられるのは `upgrade-status` だけである。宣言側 (F-3 / F-3c / F-4 / F-8 相当) は**プロセスを起動して fail-fast を見る**しかない。**手当ては両 peer に `ops verify-declarations` を置き、F-n ごとの終了コードを返すこと** — Q4 の検査関数を再利用できるので小さい。**挙動追加であり別 WP。**
- **L7-21 port v1.12 — V2 の除外判定を peer 名から能力判定へ** — **開いている**。MitateDB の `result_items` / `query_complexity` は `enforced` 宣言だが port に要求側 limit / page 件数・filter 述語数を運ぶ経路が無く、**実装は peer 名を固定で名指しして駆動対象から外している**。**このため偽の `enforced` 宣言でも V2 は永久に緑である。** 手当ては port v1.12 でそれらを optional フィールドとして運び、**除外を「その peer では port 経由でこの検査に到達する要求を構成できない」という能力判定に置き換える**こと。**L7-1 の束に含める。** 現時点では `CONDITIONS.md` C-05 行の開示がこの穴を明文化している。
- **L7-19 上流由来の `DeprecationWarning` 1 件の狭い ignore** — **撤去条件未達**。`constraints.txt` の Starlette を当該参照を直した版へ上げたときに、**同一コミットで ignore を外し集計行を添える**。
- **L7-20 ローカル開発 PG クラスタの role 設定汚染** — **記録**。管理者ロールに `statement_timeout` / `idle_in_transaction_session_timeout` の `ALTER ROLE … SET` が残っていて r2db の 2 テストが偽赤になった (監督が `RESET` で戻した)。**Q4 WP-2 の e2e 残骸ロール 2 本も残っている** (無害、未削除)。
- **L7-22 現行行から落ちた未閉止の台帳 ID 2 件** (WP-7 で起票) — **開いている、重大度は低い**。 **【訂正 2026-09-07 (フェーズ8 WP-2 / WP-6)。上の「開いている」は誤りであり、本行の原文は消さずに残す】** **本項は起票時点で既に充足していた。** 現物を読んで確認したところ、**未閉止の 2 件はどちらも現行行に台帳 ID を持っている** — **`security/CONTROL_MAPPING.md:33`** (SI-00 行) に逐語「a separate, still-open asymmetry (**ledger item L4-13, still open**)」、**`conformance-tests/CONDITIONS.md:38`** (C-09 行) に逐語「Supervisor ruling P4-D18 (**L4-8, still open**) DEFERS rebuilding V4」。**したがって追跡性は失われておらず、手当て (現行行への ID の追記 2 箇所) は不要である。ファイルは 1 バイトも変えていない。** 実装担当と受け入れ監査が別々に読んで一致を確認した (フェーズ8 設計 §10 L8-1 / §11.1)。**本項は閉じた。**`L4-13` (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 で OPEN) と `L4-8` (据え置き) の ID が現行行から消えた。**事実そのものは現行行に残っており、失われているのは追跡性だけである。** 手当ては現行行に ID を戻す 2 箇所の追記。**裁定は監督。**
- **L7-23 register テストは単独実行では緑にならない** (WP-7 で起票) — **開いている**。**原本から引き継いだ既存挙動**であり、当座の扱いは「conformance 全体 run 内で評価する」(訂正註 11)。手当ては当該テストに**収集 0 件ガード**を 1 つ足すこと。**発注範囲外だったので採らなかっただけであり、技術的な障害は無い。** **裁定は監督。**
- **その他の台帳項目 (L7-4〜L7-9 / L7-11 / L7-14〜L7-17)** — **各項に日付付きの状態注記を付した**。設計 §11 が現在形の正本である。**「閉じた」と書いてある項目は L7-9 (セル長上限の確定) と L7-13 (裁定としての確定。実行分は残る) の 2 つだけである。**
- **依頼者判断待ちの新規項目は本フェーズでは増えていない。**
- **【追記 2026-09-06、WP-8 後】フェーズ7 以降の計画は `docs/design/ROADMAP_POST_PHASE7_V1.md` に固定した** — 依頼者の目標 (G-1〜G-4、逐語)、外部提案 2 本の判定、横断の守るべき条件 P-1〜P-9、フェーズ8 (L7-1 + 衛生 + 性能基準値) / フェーズ9 (契約 1.7.0「宣言と検証」) / フェーズ10 (L7-2 + L6-5a) の範囲と着手条件、却下案、台帳 R-1〜R-14。**上記の開いている台帳項目 (L7-18 / L7-19 / L7-21 / L7-22 / L7-23) はフェーズ8 の該当 R 項目に同梱先が書いてある。** 次フェーズの設計起草者は同書 §9 の手順で着手する。
- **【追記 2026-09-07、フェーズ8 完了後】本書の「現在地」は第 15 次引き継ぎ `docs/work-orders/HANDOVER_20260907_FABLE.md` が上書きする。** フェーズ8 (実効 bound と基盤衛生) は WP-1〜WP-6 をもって完了し (main の最新 merge `f4635ed`、完了ゲート `2340 passed, 5 warnings in 349.31s (0:05:49)`、failed 0 / xfailed 0 / skipped 0)、**上記の開いている台帳項目のうち L7-1 / L7-18 / L7-21 / L7-22 / L7-23 は閉じた** (L7-19 は上流待ちで据え置き、L7-2 はフェーズ10)。**契約 1.6.0 は 1 バイトも動いていない。** **本書の §2 到達した状態・§3 クライアント連携・§4-1 WP-9 の手順・§4-3 運用規律・§5 教訓はすべて継続する** — 第 15 次はそれを継承したうえで、フェーズ8 が足した分だけを書いている。

### 4-3. 運用規律 (第13次 §4-3 と Q4 側第 14 次 §6 を継承。本フェーズが足したもの)

- **共有 `.venv` に `httpx2` を入れると完了ゲートの `5 warnings` は消える。** **入れていない現状でも 4 数は CI と一致する** (`StarletteDeprecationWarning` は `UserWarning` 派生で error 化の対象外) ので、**入れるかどうかは任意である** — ただし**入れれば「ローカルと CI で warnings の数が違う」という毎回の説明が不要になる**。
- **`.pre-commit-config.yaml` の local hook が入っている。** **entry はシステム `python3`** (スキャナ本体は標準ライブラリのみ) であり、**`.venv` に `pre-commit` を入れてある**。**hook は staged なファイルに対して走る** ので、**未追跡ファイルの実値はここで捕まる** (スキャナのツリーモードは `git ls-files` の対象しか見ない — L7-14)。
- **作業機に `shellcheck` と `nginx` が Homebrew で入っている** (7-A WP-3 の lint をローカルで動かすため)。**CI 側は runner の apt であり版が違う** — **`nginx -t` の判定は一致しない前提で読むこと** (L7-16。分離形の `http2` ディレクティブは runner の nginx 1.24 では赤、1.25 以降では緑になる)。
- **ローカル PostgreSQL の role 設定は汚れることがある。** 完了ゲートが説明のつかない赤を出したら、**まず `pg_db_role_setting` を疑うこと** (L7-20)。共有クラスタで migration を手で流すときは psql 変数の role 名を確認する。
- **`gh` CLI が使える。** CI の状態確認はこれで行う。**GitHub Actions の job ログは run が完了した後にしか読めない** — 走っている最中は `gh run view` の status しか取れないので、**待つ側の設計を先に決めること** (ログの完了行を待つ形にする)。
- **workflow に concurrency の cancel が入っている。** **同じ branch へ続けて push すると前の run が cancel される** — 「赤になった」と「cancel された」を取り違えないこと。
- **並行 worktree は「触るファイルが重ならないこと」を先に確認してから使う。** 7-A の 3 WP は重なり 0 を §12 で確認してから並列化した。**WP-7 は `CONDITIONS.md` / `CONTROL_MAPPING.md` を全面的に触るので、他の 7-B WP と並行させなかった。**
- **完了ゲートは監督が単独実行する** (`ps` で他の pytest が 0 件であることを確認してから)。**subagent には peer 別 suite と担当ファイルの conformance だけを回させる。** **ローカル PG の `max_connections = 300` が前提である。**
- **変異の復元は scratchpad backup からの `cp` + `sleep 3` 後の sha256 二重照合 + コミット前の変異文字列 grep。** **`git checkout --` は使わない。**
- **push 前に `git log --format='%an <%ae>'` で `r2fish` / noreply のみを確認する。commit → push → main merge は 1 セット。**

## 5. 教訓の追加 (前書全項継承に追加)

- **実装担当への差し戻しは、会話ではなくファイルで渡す。** WP-7 のレビューは指摘 13 件を `wp7-review-instructions.md` として書き下ろし、**各件に「原文」「現行がどう止まっているか」「実測 (`grep -c` の数)」「壊れるシナリオ (消費者が何を誤って結論するか)」を並べた**。**この形にしたから 8 件が漏れなく戻った** — 口頭要約なら「どの文を戻すのか」が曖昧になり、condense の裁量が是正の欠落に化ける。**指摘の重大度を付け、裁定を要する項目は「裁定は監督」と明記して実装担当に判断させない**のも同じ理由である。**差し戻し文面はレビューの成果物であって、レビューログの一部ではない。**
- **`git checkout --` を禁止し続けたことが、Google Drive 同期ツリーで何度も効いた。** 本フェーズは変異を **7 種 × 複数ラウンド**実施したが、復元は毎回 scratchpad backup からの `cp` + `sleep 3` + sha256 二重照合であり、**最終 sha256 が backup と全ファイル一致することを実装担当と監査が別々に確認した**。**`git checkout --` は「作業ツリーの他の変更を巻き込む」形の事故を作る** — 変異と同時に進行中の編集がある状況では、失うのは変異ではなく仕事である。
- **実装担当に下請け Agent を使わせない。** WP-7 の最初の担当は**下請け Agent の応答待ちに入ったまま停止し、作業を引き継ぐことになった**。中間成果は scratchpad に残っていたので捨てずに済んだが、**引き継ぎ地点の状態が「どこまで仕分け済みか」の記録としてしか残っておらず、後続ラウンドは全行の再計測から始めた**。**下請けを挟むと、止まったときに「何が終わっていて何が終わっていないか」を第三者が復元できない** — 発注時に「下請け Agent を使わない」を書くこと。**第11次以来の「subagent は長い待ちに入って止まる」の系である**が、待ちの相手が suite ではなく別の Agent になった分だけ、復元が難しい。
- **残骸の掃除が、それまで空振りしていた vector を顕在化させる。** WP-5 は conformance の fixture 層に application の teardown deprovision を入れた。**すると C-14 の applications vector が「既に上限近くで空振り気味だった」ことが判明し、次いで `requests_per_minute` の枠が 24 件で枯渇した。** 是正は限度値を上げることではなく、**隔離 surface + 既存登録数を差し引く headroom で駆動する形**である。**残骸は「無害な汚れ」ではなく「検査を静かに無効化する状態」であり、掃除して初めてそれが見える。** 制約で回避せず、駆動の形を作り直すのが正しい。
- **(e) の計数は自 application の DB に限る。** 資源検査で「いくつ登録されているか」を数えるとき、**共有 platform の全体を数えると他テストの残骸に汚染される**。WP-5 が採った形は **`n_existing_shared + 3` の導出式**であり、**「今この plug が見ている枠」を基準に headroom を計算する**。**k=0 (margin を 0 にする) 変異が 4 plug すべてで赤になる**ことで、この算術が load-bearing であることを実測した。
- **`StarletteDeprecationWarning` は `UserWarning` 派生である。** 名前に `DeprecationWarning` が入っていても **`error::DeprecationWarning` は捕まえない**。**発注文書の前提「httpx2 を入れないと落ちる」は誤りだった** — **httpx2 の役割は警告の除去と fallback 撤去への備えであって、error 化を通すことではない**。**警告クラスの継承関係は MRO を実測してから書くこと** (レビューが実測して訂正した)。**同種の罠**: pytest は**最寄りの inifile** を採るので、root だけに `filterwarnings` を置いても peer 単体実行には効かない — これも 4 通りの起動で `rootdir` / `inifile` を実測して初めて分かった。
- **GitHub の unreachable object は force push では消えない。** 旧 commit は SHA 直指定で取得できる状態で remote に残り得る。**したがって履歴の実値を消す唯一の確実な形は「同名リポジトリを delete して書換後の履歴だけで再作成する」ことであり、依頼者裁定 (γ) はこれを採った。** **「ローカルの履歴を書き換えた」と「公開される履歴から実値が消えた」は別の主張である** — 後者は**再作成後の remote から取り直した fresh clone に対する走査**でしか示せない (§9 の手順 4 がその形になっている)。
