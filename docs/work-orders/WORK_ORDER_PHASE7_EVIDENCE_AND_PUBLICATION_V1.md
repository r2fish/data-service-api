# フェーズ7 作業指示書 — 証拠・再現性・公開準備 (契約 1.6.0 不変)

- 版数: **v1.3 (2026-09-06、7-B の WP-4 / WP-5 / WP-6 完了)**。v1.2 からの変更点: **(1)** **§4 に訂正註 7〜10** を追加した (WP-6 の着手条件は main マージのみを指す / WP-6 の前提 3 点の実測訂正と `StarletteDeprecationWarning` の追記 / WP-5 の (d) は Q4 が先に閉じており代わりに資源管理が入る / WP-5 の変異 4 は r2db の二重ゲートでは成立せず C-00 の早期 return 2 経路は到達 0/4 である)。**いずれも実装物の欠陥ではなく、本書側の誤りか本書の発注後に監督が下した裁定である** (フェーズ6 §11 L6-18 の流儀)。**本文の発注内容は書き換えていない。** **(2)** **§1 の WP-4 / WP-5 / WP-6 の行に実施状態 (完了と main の merge ハッシュ) を、WP-7 の行に「進行中」を付した** — 3 WP はいずれも 2026-09-06 に完了し main へマージ済みである。**(3)** 7-B の実測 (集計行の推移・変異・受理境界・レビュー/監査の経緯) は**正本設計 §13 実施記録**に置き、**台帳の状態注記 (L7-1 / L7-6 / L7-12 / L7-13 / L7-17 / L7-19 / L7-21) は同 §11** に置いた — **本書には重複させない**
- 旧 **v1.2 (2026-09-05、7-A 完了)**。v1.1 からの変更点: **(1)** **§4 に訂正註 6 件**を追加した (WP-3 の lint 本体の置き場所 / control unit の `EnvironmentFile` / operator script の本数 / CI トリガー / WP-1 成果物一覧 / lint の check 4 と `--require-tools`)。**いずれも実装物の欠陥ではなく、本書側の誤りか本書の発注後に監督が下した裁定である** (フェーズ6 §11 L6-18 の流儀)。**本文の発注内容は書き換えていない。** **(2)** **§1 の WP-1 / WP-2 / WP-3 の行に実施状態 (完了と main の merge ハッシュ) を付した** — 3 WP はいずれも 2026-09-05 に完了し main へマージ済みである。**(3)** 7-A の実測 (集計行・変異・受理境界) は**正本設計 §13 実施記録**に置き、**台帳の新規 4 項目 (L7-14〜L7-17) は同 §11** に置いた — **本書には重複させない**
- 旧 **v1.1 (2026-09-05、裁定 (α)(β)(γ) の確定を反映)**。v1.0 からの変更点: **(1)** §0.2 の 6 を「未確定 3 点」から**確定済み**に書き換えた — **(α)** WP-2 は matrix 3.11 + 3.12 をともに required とし、完了ゲートの正本は 3.11 job の集計行、**(β)** WP-4 同梱で確定、**(γ)** 案 1 (WP-9 の手順 3 = delete + 再作成 + push、手順 4 の clone 取得元 = 再作成後の remote) で確定。**(2)** §0.2 の 3 と §1 の WP-9 着手条件から「§6 (γ) の確定」を外した。**(3)** §1 の依存順の根拠に **7-A 前倒し着手の確定** (依頼者裁定 2026-09-05) を書いた。**(4)** WP-2 の完了条件 5・対応表・禁止事項 6 を **required 確定**の形へ改めた。**(5)** WP-4 の成果物 4 と禁止事項 10 を (β) 確定の形へ改めた。**(6)** WP-9 のチェックリスト手順 3・4、完了条件 5、対応表、禁止事項 5 を (γ) 案 1 の形へ改めた。**(7)** WP-8 の引き継ぎ記載事項と禁止事項 2 を「確定内容の記録」へ改めた。**(8)** 正本設計の版数を **v1.2** へ更新した
- 旧 **v1.0 (2026-09-05、起草。監督確認で 4 点訂正: Q4 参照を v1.2 へ、WP-4 に V1 (a) の変異 12 を追加、WP-9 手順 6.5 の担当を運用者 (記録確認は監督) に統一、起草者の指摘 8 件の判定は設計 v1.1 側へ反映)**
- 正本設計: `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` (**v1.2、確定**。**§6 の (α)(β)(γ) は 2026-09-05 の依頼者裁定で確定した**)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・命題の言葉遣いは設計文書が正本であり、本書はそれを重複させない。**設計と本書が食い違ったら設計が正であり、本書の誤りとして監督へ差し戻すこと** (フェーズ6 §11 L6-18 の流儀。訂正註は本書 §4 に置く)
- 依存する並行フェーズ: `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (main の **v1.2**、merge `afcf2f5`。U-1〜U-3 は 2026-09-05 に依頼者裁定で確定)。**7-B の全 WP (WP-4〜WP-8) の着手条件は「Q4 の main マージ後」である** (設計 §2 の C8 / §10)
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260904_FABLE2.md` (第13次)。**本フェーズは第 14 次引き継ぎを起こす** (WP-8)
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/受け入れ監査
- 先行作業指示書: `docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md` (v1.3)。**§0.1 の常設規律 7 項目・完了ゲートの実測規律・禁止事項・コミット規律・「完了条件番号 → 変異」対応表の書式を本書がそのまま引き継ぐ**
- 設計レビュー回数: **本フェーズは契約に一切触れないので、追加の設計レビューは行わない** (設計レビュー 1 回目は設計 v1.1 に反映済み。契約フェーズの 2 回規律は適用しない)
- **確定文言のファイル所在**: **依頼者裁定 1〜4 の逐語は設計 §5**、**(α)(β)(γ) の確定裁定の逐語は設計 §6** にある。**そこから複製し、言い換え・要約・語順の入れ替えを行わない** (常設規律 4)。監督裁定 S-1〜S-6 と設計レビュー 1 回目の判定は**設計 §3 に反映済み**であり、設計本文が正本である

---

## 0. 規律 (全 WP 共通)

1. **設計が正である。** 本書と設計が食い違ったら、**本書の誤り**として監督へ差し戻すこと。実装担当が本書の記述を独断で読み替えて実装しない。訂正は §4 の訂正註として本書に残す (原文は消さない)。
2. **実装担当は commit しない。** git commit / push / merge は監督のみが行う。
3. **完了ゲートの suite は単独実行である。** `ps` で他の pytest プロセスが 0 件であることを確認してから、リポジトリルートで `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` を実行する。**root suite を回すのは監督の完了ゲート 1 回のみ**であり、実装担当は peer 別 suite と担当ファイルの conformance だけを回す。受け入れ監査は監督のゲートログを突合し、suite を再実行しない。コードレビューは実装報告に無い変異 1〜2 種だけを自分で試す。
4. **実値ゼロ。** 本書・設計・コミット・成果物のいずれにも、実ホスト名・FQDN・cloud project 識別子・実 e-mail・実 credential_id・IAM principal・作業機の絶対パス・実 DSN を書かない。合成値は `<UPPER_SNAKE>` 形の placeholder と `*.example.invalid` のみを使う。**本フェーズは公開規律そのものを扱う WP を含むので、この規律の違反は成果物の否定に直結する。**
5. **Python は `./.venv/bin/python` (3.11) である。** システム python を使わない。テストは前景 Bash で直列に実行し、`timeout` を明示する (600000 ms)。
6. **変異の復元は scratchpad backup からのコピーである** (`git checkout` 禁止)。本リポジトリは Google Drive 同期ツリーであり、`sleep 3` の後に sha256 を 2 回照合し、コミット前に変異文字列を全文 grep してゼロを確認する。

---

## 0.1 常設規律 (フェーズ6 §0.1 を逐語継承。全 WP に適用)

1. **空振り禁止**: 新規テストは観測対象が 1 件以上あることを assert する (パラメータ化された全 plug/adapter で)。「このテストは X を固定する」と書くなら、X を壊す変異を全 plug で赤にした実測を報告に添える。
2. **変異先行**: 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない。
3. **主張は実測の後**: docstring / CONDITIONS / runbook の断言 (「load-bearing」「必ず赤」等) は変異結果を得た後に、その数値・テスト名を引用して書く。レビュー・監査は「主張 vs 実測」を独立項目として突合する。
4. **確定文言はファイル経由**: 依頼者確定の契約文・裁定文は scratchpad の確定文ファイルから複製し、言い換えない。契約側には確定文を逐語 assert する文字列ピンのテストを置く。
5. **設計外の拡張は実装前に上げる**: 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する。
6. **同型性テスト**: 両 peer に同名で置くテストヘルパは、peer 名・パッケージ名・パス・空白を正規化して diff する同型性テスト (両 peer 同名 `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`) で一致を固定する。peer 間でコードを共有しない慣行は維持する (依頼者裁定 2026-09-03、案 (a))。
7. **実行規律**: テストは前景 Bash で直列、timeout パラメータ 600000 を明示、`ps` で他の pytest が無いことを確認してから。変異の復元は scratchpad backup からのコピー (`git checkout` 禁止)、`sleep 3` 後に sha256 を 2 回照合、変異文字列を全文 grep。

**対応表の書き方 (規律 2 の運用、フェーズ6 §0.1 を逐語継承)**: 各 WP の末尾に「完了条件番号 → 変異」の対応表を置く。**テストで固定される条件にはそれだけを壊す変異を 1 つ**対応付ける。**文書・記録・設定・無変更の条件には変異を作らず、「監査が何を何と突き合わせるか」を当該条件の本文に「監査照合」として明記する**。各 WP の最後の完了条件は「**対応表に対応の無い行が無いこと**」というメタ条件である。

**本フェーズでの適用について**: 除外は無い — **WP-1 から WP-9 まで全 WP が対応表を持つ**。ただし **WP-9 は運用者作業を含む**ので、対応表に載るのは**監督作業分の完了条件だけ**である (運用者・依頼者の手順は §2 WP-9 のチェックリストで管理する)。

---

## 0.2 本フェーズ固有の規律

1. **7-B の着手条件は「Q4 の main マージ後」である** (WP-4 / WP-5 / WP-6 / WP-7 / WP-8)。Q4 が触るファイル (両 peer の `src` / `migrations` / `ops` / `tests`、conformance adapter 2 本、`CONTROL_MAPPING.md` の 3 行、runbook) と重なるためである。**Q4 のマージ前に 7-B のファイルへ手を入れない。**
2. **WP-4 は加えて「§D-6.5『Q4 確定後の追補』の記入と監督承認」を着手条件とする。** 追補が決めるのは `isolated_application_surface()` の**構成経路**であり、これを未記入のまま実装に入ると、control plane 側の記述を data plane へ写す事故が起きる (設計 D-6.5)。**追補の記入は WP-4 の最初の作業であり、監督承認を得るまでテストコードを書き始めない。**
3. **WP-9 の着手条件は「WP-1・2・3・6 の完了 (= (g)(b) 完了) かつ依頼者の実行合図」である。** **§6 (γ) は 2026-09-05 の依頼者裁定で案 1 に確定した**ので、着手条件には残らない。**手順 3 は「同名リポジトリの delete + 書換後履歴のみ push + 再作成」、手順 4 の clone 取得元は再作成後の remote である** (§2 WP-9)。
4. **変異用の合成リテラルは一時ファイルにのみ置く。** WP-1 の変異が要する「許可リスト外 TLD を持つ裸 FQDN 形 1 件」と「許可リスト外の e-mail 形 1 件」は、**実装担当が WP-1 で生成し、一時ファイルにのみ置く**。**設計・本書・コミットのいずれにも書かない** — 書けば、WP-1 でスキャナと pre-commit hook が入った瞬間に**その文書自身が R1 / R2_fqdn で赤になる**。`*.example.invalid` は R1 / R2 の許可対象なので、それを使うと変異が空振りする (設計 D-2)。
5. **`@pytest.mark.condition(...)` の追加と `CONDITIONS.md` の Status 更新は同一コミットである。** `conformance-tests/test_conditions_register.py:106-137` が逆向きに検査しており、マーカーを付けた瞬間に当該行の `Status` が `executable` で始まっていなければ赤になる (裁定 S-6、設計 §1.6 の 2)。**WP-4 / WP-5 / WP-7 のいずれもこの規律の対象である。**
6. **(α)(β)(γ) は確定済みである** (**依頼者裁定 2026-09-05**、設計 §6)。**確定内容から外れる実装をしない。**
   - **(α) CI の Python matrix** — **WP-2**。**3.11 と 3.12 の 2 job をともに required とする。** **完了ゲートの正本は 3.11 job の集計行** (集計行の記録環境) であり、**3.12 job は同一の集計行であることを required で担保する** (§2 WP-2 の完了条件 5)。
   - **(β) MitateDB の 4 class への明示エントリ追加** — **WP-4 同梱で確定**。**宣言と検証を同一コミットに載せる。** **7-A へ先出ししない。**
   - **(γ) force push 後に GitHub 側へ残る unreachable object への対処** — **WP-9**。**案 1 で確定** — **手順 3 は「同名リポジトリを delete し、書換後の履歴だけを push して再作成する」**、**手順 4 の clone 取得元は再作成後の remote である** (§2 WP-9)。**force push だけで済ませない。**
7. **契約は 1 バイトも変えない** (設計 §2 の C1)。`spec/data-service-api.v1.json` と両 peer のパッケージ内コピーは全 WP を通じて無変更である。**新しい Security Invariant も足さない** (C2)。

---

## 1. WP 一覧

| WP | 内容 | 主に触るファイル | 着手条件 | 担当 | 設計レビュー |
|---|---|---|---|---|---|
| **WP-1** | **(g) 公開規律とスキャナ** | `docs/security/public-repository-policy.md`、`docs/work-orders/INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md`、`docs/work-orders/DEPLOY_PHASE6_20260904.md` (§7 凡例)、`tools/public_value_scan.py` (新設)、`.pre-commit-config.yaml` (新設) | なし (7-A)。**完了 (2026-09-05、main `393b9f1`)** | Sonnet 実装 → Opus レビュー → Opus 受け入れ監査 | 追加なし |
| **WP-2** | **(b)(i)(ii) constraints と CI** | `constraints.txt` (新設)、`.github/workflows/ci.yml` (新設)、`conformance-tests/README.md` | なし (7-A)。**完了 (2026-09-05、main `e1d33c3`)** | 同上 | 追加なし |
| **WP-3** | **(h) r2db 配備資産** | `r2db-api/deploy/systemd/r2dbsvc-control.service` (新設)、`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`、`r2db-api/deploy/scripts/` (新設 3 本)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`、`.github/workflows/ci.yml` (lint job の中身) | なし (7-A)。**`r2db-api/deploy/env/*.example` を触らない**。**完了 (2026-09-05、main `df35451`)** | 同上 | 追加なし |
| **WP-4** | **(a) C-05 + (e) 資源検査** | `conformance-tests/adapter.py` (port v1.11)、`conformance-tests/test_c05_limit_declaration_agreement.py` (新設)、4 plug 実装、`MitateDB-api/src/mitatedb_api/cell.py`、`conformance-tests/test_c14_authority_boundary.py` (注釈訂正)、`conformance-tests/CONDITIONS.md`、`docs/design/CONFORMANCE_ADAPTER_V1.md` | **Q4 の main マージ後、かつ §D-6.5 追補の記入と監督承認の後**。**完了 (2026-09-06、main `2ddee6c`)** | 同上 | 追加なし |
| **WP-5** | **(a) 他 5 条件 + (d)** | `conformance-tests/test_c04_*` / `test_c10_*` / `test_c02_*` / `test_c07_*` / `test_c00_*` (新設 5 本)、`conformance-tests/conftest.py`、`conformance-tests/CONDITIONS.md`、`r2db-api/src/r2db_api/` (surfaces ヘルパの 1 モジュール化)、両 peer の `tests/test_audit_query.py` (同型性対応表) | **Q4 の main マージ後**。**完了 (2026-09-06、main `10df489`)** — **(d) は訂正註 9 により対象消滅、代わりに conformance の資源管理が入った** | 同上 | 追加なし |
| **WP-6** | **(b)(iii) DeprecationWarning の error 化** | `pyproject.toml` (root)、両 peer の `pyproject.toml` (`[test]` extras、httpx2 案の場合)、`r2db-api/tests/` の 12 箇所 (ASGITransport 案の場合)、`constraints.txt` | **Q4 の main マージ後** (**WP-5 の完了後 = main へのマージのみ。訂正註 7**)。**完了 (2026-09-06、main `073afbb`)** | 同上 | 追加なし |
| **WP-7** | **(i) 現行結論と履歴の分離** | `security/CONTROL_MAPPING_HISTORY.md` / `conformance-tests/CONDITIONS_HISTORY.md` (新設)、`security/CONTROL_MAPPING.md`、`conformance-tests/CONDITIONS.md`、`conformance-tests/test_conditions_register.py`、`conformance-tests/test_control_mapping_register.py` (新設) | **Q4 の main マージ後**。**進行中 (2026-09-06)** | 同上 | 追加なし |
| **WP-8** | **記録・引き継ぎ第 14 次** | 設計 §13 / §11、`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11、`docs/work-orders/HANDOVER_20260904_FABLE2.md` §4-2、`docs/work-orders/HANDOVER_2026MMDD_*.md` (第 14 次、新設) | **WP-4〜WP-7 完了後** | Opus 起草 → 監督 → Opus 受け入れ監査 | 追加なし |
| **WP-9** | **公開ゲート** | `tools/rewrite_hash_refs.py` (新設)、`docs/` 配下の hash 参照 (一括更新)、リポジトリ外の運用者記録 (置換表・commit-map) | **WP-1・2・3・6 完了 かつ 依頼者の実行合図** (**§6 (γ) は 2026-09-05 に案 1 で確定したので着手条件には残らない**) | **[監督]** 手順書・適用スクリプト・履歴スキャン・hash 更新 / **[運用者]** worktree 畳み・filter-repo・force push・clone 作り直し・credential revoke+再発行 / **[依頼者]** 実行合図・visibility | 追加なし |

**依存順の根拠**:

- **7-A (WP-1 / WP-2 / WP-3) は Q4 と触るファイルが重ならない** (設計 §12)。唯一の重なり候補 `r2db-api/deploy/env/*.example` は **WP-3 が触らない**ので、重なりは 0 になる。**7-A の前倒し着手は依頼者裁定 2026-09-05 で確定した** — **Q4 の main マージを待たずに着手する**。**7-B (WP-4〜WP-8) の着手条件 (Q4 の main マージ後) は変わらない。**
- **WP-1 → WP-2**: CI の scanner job は WP-1 のスキャナを呼ぶ。
- **WP-2 → WP-3**: deploy-assets lint job の**枠**を WP-2 が置き、**中身**を WP-3 が入れる。
- **WP-4 → WP-5**: port を **v1.11 へ上げるのは WP-4 の 1 回だけ**であり、WP-5 が使う `idempotency_key` の経路も WP-4 で入る。
- **WP-6 は WP-5 の後**に置く — `error::DeprecationWarning` を先に有効化すると、既存 12 箇所が赤のまま他 WP の完了ゲートを塞ぐ。
- **WP-8 は最後**である (WP-4〜WP-7 の実測を記録するため)。
- **WP-9 は独立の最終 WP** であり、**7-B の完了を待たない** — 着手条件は (g)(b) の完了、すなわち WP-1・2・3・6 である。

---

## 2. 各 WP の発注

### WP-1 (g) 公開規律とスキャナ

#### 目的

**公開規律の正本を `docs/security/public-repository-policy.md` 1 つに統一し、その規律を機械検査可能にする。** 規律の断片が 2 文書に割れている状態 (設計 §1.3) を閉じ、pre-commit と CI で再発を止める。

#### 前提として読む箇所 (設計)

**§1.3** (現況)、**§3 D-1 (i)(ii)(iii)(iv)**、**§3 D-2** (規則表・共通除外・配置・変異)、**§11 L7-3 / L7-4**、**付録 A** (プロトタイプ結果)。

#### 成果物

1. `docs/security/public-repository-policy.md` — **(a)** `Never publish` 節 (:17-23) に **D-1 (i) の表が挙げる分類をすべて**追記する、**(b)** placeholder 規約 (D-1 (ii)) を置く、**(c)** 配備記録テンプレートの規約と凡例の形 (D-1 (iii)) を置く、**(d)** First-public-push gate の 8 項目 (D-1 (iv)) を置く。
2. `docs/work-orders/INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md:71` の運用情報行を **policy への参照に置き換える**。
3. `docs/work-orders/DEPLOY_PHASE6_20260904.md` §7 (:1412 以降) の凡例のうち、**`credential_id` を「書いてよいもの」に置いている行を訂正する** (D-1 (i) と衝突する。設計 §1.6 の 7)。**同 :3 の blockquote (実値置換の宣言) は次の DEPLOY 文書のテンプレートの形として policy から参照する。**
4. `tools/public_value_scan.py` — **root 直下に `tools/` を新設**する。**標準ライブラリのみ、外部依存を持たない。** 規則は設計 D-2 の表の **R1 / R2_url / R2_fqdn / R3 / R4 / R5 / R6 / R8**。**R7 (個人名) は実装せず、「検査していない」ことを出力とドキュメントに明記する** (L7-3)。**共通除外は「トークンから placeholder 部分文字列 (`<[A-Z0-9_]+>` と `REPLACE_ME[A-Z0-9_]*`) を除去した残りに各規則を再適用し、残りが規則に当たれば flag する」形である** — 「placeholder を含むトークンを丸ごと除外する」形は採らない (D-2)。**`--history` モード** (`git log --all -p` を走査) を持つ。**違反 1 件以上で非 0 終了する。**
5. `.pre-commit-config.yaml` — **local hook** としてスキャナを呼ぶ (外部リポジトリ依存を持たない)。
6. **再プロトタイプの記録** (常設規律 5) — 現行ツリー全走査で**全規則 flagged 0 件**の出力を設計 §13 に記録する。

#### 完了条件 (検証可能な形)

1. **policy の追記** — **監査照合 (変異を作らない)**: 監査は `git diff -- docs/security/public-repository-policy.md` を読み、**D-1 (i) の表の各行が `Never publish` 節に対応する記述を持つ**こと、**D-1 (ii) の placeholder 規約 (許される伏字は `<UPPER_SNAKE>` と `REPLACE_ME_*` の 2 形、ドメインは `*.example.invalid` のみ)** が置かれていること、**D-1 (iv) の 8 項目が順序どおり**置かれていることを、設計の該当箇所と 1 対 1 で突き合わせる。
2. **正本の一本化** — **監査照合**: `docs/work-orders/INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md:71` が policy への参照になっており、**規律の実体が 2 箇所に残っていない**こと。
3. **配備記録テンプレートの規約と凡例の訂正** — **監査照合**: `DEPLOY_PHASE6_20260904.md` §7 の凡例から **`credential_id` が「書いてよいもの」から外れている**こと、および policy 側にテンプレートの規約が置かれていること。**当該 DEPLOY 文書の実値は 2026-09-05 に置換済みであり、本 WP は凡例だけを触る** — 記録本文の実値を新たに書き足さない。
4. **スキャナが規則 R1〜R6・R8 を実装している** — 各規則が設計 D-2 の表の対象と許可/除外に一致すること。**R7 は実装せず、「検査していない」ことを `--help` と出力に明記している**こと。
5. **現行ツリーの走査で全規則 flagged 0 件である** — **R2_fqdn の TLD 限定集合で 0 件になることを実測して固定する** (L7-4)。**設計文書と本書が含む「作業機の絶対パス形の説明」(D-1 (i) の表と D-2 の規則表が R6 の対象を説明するために書いている、末尾を省略記号で切ったパターン記述) が R6 で flag されない除外を持つ**こと。**0 件の出力を設計 §13 に記録する。**
6. **許可リスト外の裸 FQDN 形を検出する** — 変異 1。
7. **許可リスト外の e-mail 形を検出する** — 変異 2。
8. **共通除外が「部分文字列を除去してから再判定」である** — placeholder を実値の前に置いても隠せないこと。変異 3。
9. **作業機の絶対パス形 (R6) を検出する** — 変異 4。
10. **`--history` モードが動く** — 置換前の版を含む一時ブランチを走査させて**非 0 終了**すること。変異 5。
11. **pre-commit hook が local hook であり、外部リポジトリ依存を持たない** — `pre-commit run --files <一時ファイル>` が**非 0 で終わる**こと。変異 6。**hook の実行は commit を伴わない** (実装担当は commit しない)。
12. **速度** — **監査照合**: 現行ツリー 1 走査の所要が付録 A の実測 (1 秒未満) と同水準であること。完了報告に実測秒を書く。
13. **対応表に対応の無い行が無いこと** (メタ条件、§0.1 の 2)。
14. **完了ゲート** — **スキャナは pytest suite に入れない**ので、root suite の集計行は**着手時点から不変**であること (`passed` / `failed` / `skipped` / `xfailed` の 4 数すべて)。**監査照合**: 監査は監督のゲートログと着手時点の集計行を突き合わせる。

#### 非 vacuity 要件

- **変異 1〜4 は、スキャナが「当たっている」ことを規則ごとに個別に示すこと** — 4 件をまとめて 1 回の走査で観測するのではなく、**規則ごとに flagged 件数が 0 → 1 に動くことを規則名つきで報告する**。
- **除外の検査は必ず対照を伴う** — 「除外したから 0 件」と「そもそも当たっていないから 0 件」を区別するため、**除外を一時的に無効化すると当該箇所が flag されること**を、条件 5 の 2 つの除外 (placeholder / 設計文書と本書の絶対パス形パターン記述) について実測する。

#### 確定文言のファイル所在

- **依頼者裁定 1・2 の逐語は設計 §5 にある。** policy に裁定の趣旨を書く場合は**設計 §5 から複製し、言い換えない** (常設規律 4)。
- **D-1 (i) の分類名と D-1 (ii) の placeholder 規約は設計 §3 D-1 が正本**である。要約・意訳を置かない。

#### 同型性テスト対象

**なし。** 本 WP は両 peer に同名ヘルパを置かない。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 policy の追記 | **監査照合** |
| 2 正本の一本化 | **監査照合** |
| 3 テンプレート規約と凡例訂正 | **監査照合** |
| 4 規則 R1〜R6・R8 の実装 | **変異 1〜4 が包括的に担保する** (規則ごとに 1 件、下記) |
| 5 現行ツリー 0 件 | **対照 A / 対照 B** (除外の無効化。下記) |
| 6 裸 FQDN の検出 | **変異 1** |
| 7 e-mail の検出 | **変異 2** |
| 8 placeholder 前置での隠蔽不能 | **変異 3** |
| 9 絶対パスの検出 | **変異 4** |
| 10 `--history` モード | **変異 5** |
| 11 pre-commit local hook | **変異 6** |
| 12 速度 | **監査照合** |
| 13 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 14 完了ゲート | **監査照合** |

1. **許可リスト外の裸 FQDN 形** — **実装担当が生成し、一時ファイルにのみ置く**。`*.example.invalid` は許可対象なので使わない (§0.2 の 4)。**R2_fqdn が 1 件 flag し、スキャナが非 0 終了する**こと。**具体値を報告・コミット・本書・設計に書かない** (「R2_fqdn が 1 件」とだけ報告する)。
2. **許可リスト外の e-mail 形** — 同上。**R1 が 1 件 flag する**こと。
3. **placeholder 前置による隠蔽** — 変異 1 の一時ファイルで、実値形の直前に `<UPPER_SNAKE>` 形の placeholder を前置する。**それでも flag される**こと (D-2 の共通除外が「部分文字列を除去して再判定」であることの実測)。**丸ごと除外の旧規則ではここが緑になる** — 緑になったら実装が旧規則である。
4. **作業機の絶対パス形** — R6 が対象とする形の 1 件を一時ファイルに置き、**R6 が flag する**こと。
5. **履歴モード** — 置換前の版を含む一時ブランチを作って `--history` を走らせ、**非 0 終了する**こと。**一時ブランチは実測後に削除する** (実装担当は commit しないので、ブランチ作成が必要なら監督へ依頼する)。
6. **pre-commit hook** — 変異 1 の一時ファイルに対して `pre-commit run --files` を実行し、**非 0 で終わる**こと。
- **対照 A** — placeholder 除外を一時的に無効化すると、現行ツリーで **`<UPPER_SNAKE>` 形を含む箇所が flag される**こと (除外が load-bearing であることの実測)。
- **対照 B** — 設計文書と本書の絶対パス形パターン記述に対する除外を一時的に無効化すると、**R6 が当該箇所を flag する**こと。

**変異 1〜4 の一時ファイルは、実測後に削除し、`git status` が clean であることを確認する。** 合成リテラルは**報告に転記しない**。

#### テストコマンド

```
./.venv/bin/python tools/public_value_scan.py                       # 現行ツリー。全規則 0 件
./.venv/bin/python tools/public_value_scan.py --history             # 履歴モード
./.venv/bin/pre-commit run --files <一時ファイル>                    # local hook (非 0 終了を確認)
```

**root suite は回さない** (本 WP は pytest の収集対象を 1 件も変えない)。**完了ゲートは監督が握る。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **既製の secret scanner (gitleaks / trufflehog 等) を導入しない** (設計 §4 の 4)。**外部依存を持たない 1 ファイルで足りる。**
2. **スキャナを pytest suite に入れない** (D-2)。suite は挙動を測るものであり、スキャナは公開規律である。
3. **合成の違反リテラルを一時ファイルの外に出さない** — 報告・コミット・本書・設計のいずれにも書かない (§0.2 の 4)。
4. **R7 (個人名) を「規則を工夫して当てる」試みをしない** — 対象外であることを明記するのが正しい (L7-3)。**「0 件だった」と書かない** — 検査していないことと 0 件は違う (付録 A.4)。
5. **`r2db-api/deploy/env/*.example` を触らない** (Q4 WP-D と衝突する)。
6. **R2_fqdn の TLD 集合を「広めに取って後で絞る」形にしない** — 集合を広げると誤検出が戻る (L7-4)。**0 件を実測してから固定する。**

---

### WP-2 (b)(i)(ii) constraints と CI

#### 目的

**第三者が同じ集計行を再現できる状態にする。** 依存を exact pin で記録し、実 PostgreSQL を持つ CI で完了ゲートのコマンドを回し、集計行を job summary に出す。

#### 前提として読む箇所 (設計)

**§1.2** (現況)、**§3 D-3** (lock 方式・CI・pytest 設定の一本化・変異)、**§7.6**、**§11 L7-5 / L7-6**、**§6 (α)** (**確定済み**: 両方 required、正本は 3.11 job の集計行)。

#### 成果物

1. **`constraints.txt`** (root 1 本、exact pin)。
2. **`.github/workflows/ci.yml`** (新設。`.github/` ディレクトリ自体が新設である)。
3. **`conformance-tests/README.md`** — 実 PG の要件を明文化する。

#### `constraints.txt` の生成手順 (本書が発注する形)

1. **清浄な venv を作る** (既存 `./.venv` を使わない。作業用の別ディレクトリに作る)。
2. `pip install -e ./r2db-api[test] -e ./MitateDB-api[test]` を実行する。
3. `pip freeze` の出力を `constraints.txt` の素とする。
4. **venv 由来の無関係物を手で除く** (`pip` / `setuptools` / `wheel` 等、および editable install で現れる 2 peer 自身の行)。
5. **除いた行と、その判断理由を完了報告に列挙する** — この工程の判断はコミットに残らない (L7-5)。
6. **利用形は `pip install -c constraints.txt -e ./r2db-api[test] -e ./MitateDB-api[test]` である。**
7. **両 peer の `pyproject.toml` は下限 pin のまま**とする。**触らない。**

#### 完了条件 (検証可能な形)

1. **`constraints.txt` が exact pin である** — すべての行が `==` で固定されていること。**生成手順 (上記 1〜5) と、除いた行の一覧が完了報告にある**こと。**監査照合**: 監査は完了報告の除外一覧と `constraints.txt` の内容を突き合わせ、**両 peer 自身の行と venv 由来物が残っていない**ことを確認する。
2. **清浄 venv で `pip install -c constraints.txt -e ./r2db-api[test] -e ./MitateDB-api[test]` が成功する** — 実測を報告する。
3. **CI が PostgreSQL 16 を `docker run` step で起動する** — `postgres:16`、**`-c max_connections=300` をコマンド引数として直接渡す**、**合成パスワード**、loopback への port 公開。**`services:` は使わない** (`command:` に相当するキーが無く、`max_connections` が既定 100 のまま `-n 5` を回して接続枯渇で赤になる。D-3)。
4. **`R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` を loopback TCP の DSN で上書きしている** — **両変数の既定値は unix socket (`host=/tmp`) であり、コンテナで起動した PG には届かない** (D-3)。**DSN に実値を書かない** (CI 内の loopback と合成パスワードのみ)。
5. **Python matrix が 3.11 と 3.12 の 2 job を定義し、どちらも required である** (**(α) 確定、依頼者裁定 2026-09-05**) — **どちらの job も `continue-on-error` を持たず、失敗が workflow の失敗になる**こと。**完了ゲートの正本は 3.11 job の集計行**であり、**3.12 job は同一の集計行であることを required で担保する** — **両 job の集計行が食い違えば赤になる**形にすること (実現手段は実装担当が選び、完了報告で説明する)。**監査照合**: 監査は workflow に **informative / 任意扱いの痕跡が無い**ことと、**「正本は 3.11 job の集計行である」旨が workflow か `conformance-tests/README.md` のいずれかに 1 行ある**ことを確認する。
6. **ゲートコマンドが `python -m pytest -q -n 5 --dist loadgroup` である** — ローカルの完了ゲートと同一であること。
7. **集計行を job summary に出す** — `passed` / `failed` / `skipped` / `xfailed` の 4 数が job summary から読めること。**監査照合**: 監査は CI 実行のログと job summary を突き合わせる。
8. **scanner job がある** — WP-1 のスキャナをツリーモードで実行し、**違反 1 件以上で job が赤になる**こと。
9. **deploy-assets lint job の枠がある** — job 名と依存関係だけを定義する。**ステップ本体は WP-3 が入れる** (本 WP では中身を書かない)。**監査照合**: 監査は job が定義されていることと、WP-3 の発注範囲を侵していないことを確認する。
10. **`conformance-tests/README.md` に実 PG の要件がある** — **superuser 相当の DSN 2 変数**、**`max_connections=300`**、**`-n 5 --dist loadgroup`**、**未接続は fail であり skip しない**こと。**既存 :110-123 の「PostgreSQL が届かないことを silently な被覆欠落にしない」という記述の直後に置く** (設計 §7.6)。
11. **constraints が load-bearing である** — 変異 1。
12. **`max_connections` の要件が load-bearing である** — 変異 2。**赤にならなければ「変異なし」と記録し、要件の根拠をフェーズ6 §10 の実測 (64/100 接続) に置く** (D-3)。
13. **対応表に対応の無い行が無いこと** (メタ条件)。
14. **完了ゲート** — root suite の集計行が着手時点から**不変**であること (`pyproject.toml` の `filterwarnings` は本 WP では**有効化しない** — 有効化は WP-6 である)。

#### 非 vacuity 要件

- **CI が実際に緑になったこと**を、**実行 URL ではなく job summary の集計行**で示す。**「workflow を書いた」だけでは完了条件 6・7 を満たさない。**
- **CI の赤/緑の実測は監督が当該ブランチを push して GitHub Actions 上で行う** — 実装担当は commit しないので、workflow ファイルと変異用の一時テストを用意し、**監督に実行を依頼する**。この往復を完了報告に明記する。

#### 確定文言のファイル所在

**(α) の確定裁定の逐語は設計 §6 (α)** にある。**workflow や README に確定内容を書く場合はそこから複製し、言い換えない** (常設規律 4)。**両論は同節の「経緯」が正本である。**

#### 同型性テスト対象

**なし。**

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 exact pin と生成手順 | **監査照合** |
| 2 清浄 venv でのインストール | **実測** (変異なし。手順の再現そのものが証拠である) |
| 3 `docker run` step | **変異 2 が同時に担保する** (`max_connections` を渡す経路が step にしか無い) |
| 4 DSN の loopback 上書き | **変異 3** |
| 5 matrix 2 job がともに required / 正本 = 3.11 job の集計行 | **監査照合** (informative の痕跡が無いこと + 正本の明記) |
| 6 ゲートコマンド | **監査照合** (ローカルの完了ゲートと文字列一致) |
| 7 job summary の集計行 | **監査照合** |
| 8 scanner job | **変異 4** |
| 9 deploy-assets lint job の枠 | **監査照合** |
| 10 README の実 PG 要件 | **監査照合** |
| 11 constraints が load-bearing | **変異 1** |
| 12 `max_connections` の要件 | **変異 2** |
| 13 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 14 完了ゲート | **監査照合** |

1. **constraints に無いパッケージを import する一時テストを足す** → **CI が赤**になること。**「constraints から 1 行落とす」は install step が変わるだけで緑のままなので変異にならない** (D-3)。
2. **`max_connections` を 100 にして CI を回す** → **conformance が接続枯渇で赤**になること。**赤にならなければ「変異なし」と記録**し、要件の根拠をフェーズ6 §10 の実測に置く。
3. **DSN の loopback 上書きを外す** → 既定の unix socket に落ちて **PG へ届かず赤**になること (`skip` にならないこと。README の「未接続は fail」と一致すること)。
4. **WP-1 の変異 1 の一時ファイルを含めて CI を回す** → **scanner job が赤**になること。

**すべての変異は実測後に復元し、`git status` が clean であることを確認する。**

#### テストコマンド

```
# 清浄 venv での再現 (完了条件 2)
python3.11 -m venv <作業用の一時 venv>
<一時 venv>/bin/pip install -c constraints.txt -e ./r2db-api[test] -e ./MitateDB-api[test]

# CI 上のゲートコマンド (workflow が実行する形)
python -m pytest -q -n 5 --dist loadgroup
```

**ローカルの root suite は監督の完了ゲートのみ**: `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **`uv.lock` / `pip-tools` / `poetry` を導入しない** (設計 §4 の 5)。
2. **両 peer の `pyproject.toml` の下限 pin を exact pin へ変えない** — `constraints.txt` は再現性の記録であり、下限 pin は互換性の主張である。**役割が違う** (D-3)。
3. **root `pyproject.toml` に `filterwarnings` を置いて有効化しない** — 有効化は **WP-6** である。7-A の時点で置くと既存 12 箇所が赤になる (D-3)。
4. **CI に実値・実 secret を書かない。** PG のパスワードは合成値、DSN は loopback、GitHub の secret 機構に実値を登録する形も本 WP では作らない。
5. **deploy-assets lint job の中身を書かない** (WP-3 の範囲)。
6. **(α) の確定内容から外れない** (§0.2 の 6) — **3.12 job を informative・任意扱いにしない**。**正本を 3.11 job の集計行以外に置かない。**

---

### WP-3 (h) r2db 配備資産の再現性

#### 目的

**次回配備・復旧・第三者レビューで再現できる形にする。** 文章指示にしか存在しない第二 unit と `/control/v1/` の proxy、および実機にしか残っていない operator script を、**合成値のテンプレート**としてリポジトリに置き、CI で構文を検査する。

#### 前提として読む箇所 (設計)

**§1.4** (現況)、**§3 D-5** (追加物 5 点・検証・変異)、**§11 L7-11**、**§12** (Q4 との重なり)。

#### 成果物

1. **`r2db-api/deploy/systemd/r2dbsvc-control.service`** — 既存 `r2dbsvc-api.service` と同型の unit。**unit 名・port・`EnvironmentFile` は placeholder** (`REPLACE_ME_CONTROL_PORT` 等)、`ExecStart` は `uvicorn r2db_api.control_main:app` を指す。**既存 unit の hardening 節と `PrivateTmp` の posture B 注意書きを同型で持つ。**
2. **`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example` に `location /control/v1/` ブロックを追加**する — `location /v1/` と**同じ proxy_* 設定**、`REPLACE_ME_CONTROL_PORT`、**`listen 8443 ssl http2;` の nginx 1.24 互換記法** (実配備で `http2 on;` が `nginx -t` に落ちた教訓)。**:86-98 の「このテンプレートにはまだ含まれていない」コメントを、追加と同時に置き換える。**
3. **`r2db-api/deploy/scripts/` に operator script 3 本** — part1 (OS user・ディレクトリ・venv・migration `0005` 適用。**`api_password` 変数が必須である**という教訓を反映)、part1b (control credential reset)、part2 (unit と nginx の有効化)。**runbook §7 と `DEPLOY_PHASE6_20260904.md` §8 の記録から合成値で書き起こす。実機からの回収は前提にしない。**
4. **`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7 (:499-638) の更新** — 「第二 unit を作り `ExecStart=` を向けよ」という文章指示を、上記テンプレートへの参照に置き換える。
5. **同 :105 の stale な「Python 3.11 virtualenv」の訂正** — **実配備の VPS は 3.12 のみである** (裁定 S-5)。**`requires-python` (`>=3.11`) を満たす版という表現に改め、具体の版を書く箇所は CI の matrix (WP-2) と配備記録に一本化する。**
6. **`.github/workflows/ci.yml` の deploy-assets lint job の中身** — `systemd-analyze verify` (ubuntu)、`nginx -t` (**placeholder を合成値に置換した一時 conf に対して**)、`bash -n` (+ shellcheck が利用可能なら追加)。

#### 完了条件 (検証可能な形)

1. **control unit が存在し、既存 unit と同型である** — **監査照合**: 監査は `r2dbsvc-api.service` と新設 unit を並べ、**hardening 節と `PrivateTmp` の posture B 注意書きが同型で存在**し、**差分が unit 名・port・`EnvironmentFile`・`ExecStart` に限られる**ことを確認する。
2. **`ExecStart` が `uvicorn r2db_api.control_main:app` を指す** — 変異 1。
3. **nginx に `location /control/v1/` がある** — `location /v1/` と同じ proxy_* 設定であること。**:86-98 のコメントが置き換わっている**こと。
4. **nginx 記法が 1.24 互換である** — `listen 8443 ssl http2;` の形であり、`http2 on;` を使っていないこと。変異 2 と同じ job で検査される。
5. **`nginx -t` が緑である** — placeholder を合成値へ置換した一時 conf に対して。変異 2。
6. **operator script 3 本がある** — part1 / part1b / part2。**合成値のみ**であり、**`api_password` 変数が必須である**教訓が part1 に反映されていること。**`bash -n` が緑である**こと。変異 3。
7. **runbook §7 がテンプレート参照になっている** — **監査照合**: 監査は §7 の Deployment steps から「第二 unit を作れ」という文章指示が消え、新設テンプレートを指していることを確認する。
8. **runbook :105 の訂正** — **監査照合**: 具体の Python 版を書かない表現になっており、版を書く箇所が CI の matrix と配備記録に一本化されていること。
9. **CI の deploy-assets lint job が動く** — `systemd-analyze verify` / `nginx -t` / `bash -n` の 3 つが実行され、**いずれかが落ちれば job が赤になる**こと。変異 1〜3 がこれを担保する。
10. **新規資産に実値が 0 件である** — **WP-1 のスキャナを新設ファイル群に掛けて全規則 0 件**であること。
11. **`r2db-api/deploy/env/*.example` を触っていない** — **監査照合**: 監査は `git diff --stat` に当該 2 ファイルが**現れない**ことを確認する (Q4 WP-D と衝突する唯一の点。設計 §12)。
12. **対応表に対応の無い行が無いこと** (メタ条件)。
13. **完了ゲート** — root suite の集計行が着手時点から**不変**であること (配備資産は pytest の収集対象ではない)。

#### 非 vacuity 要件

- **lint job が「実際に落ちうる」ことを 3 種すべてで示す** — `systemd-analyze verify` / `nginx -t` / `bash -n` のそれぞれについて 1 つずつ変異を入れ、**job が赤になる**ことを実測する。**1 種だけの実測で「lint が効いている」と書かない** (常設規律 3)。
- **`nginx -t` の実測は placeholder を合成値へ置換した一時 conf に対して行う** — placeholder のままでは構文が通らないため、**置換手順そのものが lint job の一部である**ことを報告に明記する。

#### 確定文言のファイル所在

**なし。** 教訓 (`api_password` 変数の必須性、`http2 on;` が `nginx -t` に落ちたこと) の出所は **`DEPLOY_PHASE6_20260904.md` §8 と runbook §7** であり、**そこから合成値で書き起こす** — 実値を持ち込まない。

#### 同型性テスト対象

**なし** (r2db 単独の配備資産である)。

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 unit の同型性 | **監査照合** |
| 2 `ExecStart` | **変異 1** |
| 3 `location /control/v1/` | **変異 2** |
| 4 nginx 1.24 互換記法 | **変異 2 と同じ job** (記法が非互換なら `nginx -t` が赤) |
| 5 `nginx -t` が緑 | **変異 2** |
| 6 operator script 3 本 | **変異 3** |
| 7 runbook §7 | **監査照合** |
| 8 runbook :105 | **監査照合** |
| 9 lint job | **変異 1〜3** |
| 10 実値 0 件 | **WP-1 のスキャナ実行** (変異は WP-1 で実測済み) |
| 11 env example 無変更 | **監査照合** |
| 12 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 13 完了ゲート | **監査照合** |

1. **`ExecStart` を壊す** (存在しない module path を指すか、行の構文を壊す) → **`systemd-analyze verify` が赤**になること。
2. **nginx の `location /control/v1/` ブロックの `proxy_pass` を壊す** → **`nginx -t` が赤**になること。
3. **operator script の 1 本の構文を壊す** → **`bash -n` が赤**になること。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### テストコマンド

```
systemd-analyze verify r2db-api/deploy/systemd/r2dbsvc-control.service
nginx -t -c <placeholder を合成値へ置換した一時 conf>
bash -n r2db-api/deploy/scripts/<各 script>
./.venv/bin/python tools/public_value_scan.py                       # 新規資産に実値 0 件
```

**CI 上の lint job の赤/緑の実測は監督が push して行う** (WP-2 と同じ往復)。**root suite は監督の完了ゲートのみ。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **実機から資産を回収しない** (設計 §4 の 7)。**実値を持ち込む経路になる。** 運用者が原本と突合するのは任意の検証であり、本 WP の完了条件ではない (L7-11)。
2. **`r2db-api/deploy/env/*.example` を触らない** (Q4 WP-D の範囲)。
3. **実ホスト名・実 port・実 unit 名・実パス・実 DSN・実パスワードを書かない。** placeholder と合成値のみ。
4. **runbook の既存記述を削除しない** — §7 は参照へ置き換え、:105 は訂正する。**それ以外の節に手を入れない。**
5. **配備を実行しない。** 本 WP はテンプレートの作成であり、実機への適用は範囲外である (第13次 §4-1 のまま)。

---

### WP-4 (a) C-05 の共通化 + (e) 隔離 surface の資源検査

**着手条件: Q4 の main マージ後、かつ §D-6.5「Q4 確定後の追補」の記入と監督承認の後。**

#### 目的

**SI-08 の「有限で発見可能な境界」の共通証拠を初めて executable にする。** 宣言の自己整合 (V1)、宣言値と拒否位置の一致 (V2)、未実装の fail-loud (V3) を 4 plug 全数で固定し、**「実装していない」と「宣言し忘れた」の区別がつかない状態**を閉じる。**実装そのもの (MitateDB の資源上限) は本 WP の範囲ではない** — 裁定 3 のとおり L7-1 の次フェーズ候補である。

#### 前提として読む箇所 (設計)

**§1.1**、**§1.6 の 1・5・7**、**§3 D-6.1**〜**D-6.6**、**D-6.11**、**§5 裁定 3**、**§6 (β)** (**確定済み**: WP-4 同梱)、**§7.1 の 1・2**、**§7.3**、**§7.4**、**§7.5**、**§8 の SI-08 段落と V1 (e) 段落**、**§11 L7-1**。

#### 成果物

0. **設計 §D-6.5「Q4 確定後の追補」の記入** (**最初の作業**)。`isolated_application_surface()` の構成経路を、Q4 の確定内容に照らして書く。**control plane の composition root の非対称 (Q4 §6.1 / LQ4-11) と、data plane の隔離 surface の経路 (MitateDB は `cell.py` の `_surfaces_document_fragment(config)` 経由で Q4 D-2 の宣言表由来になる) を区別して書く** — 書かないと control 側の記述を data 側へ写す事故が起きる。**監督承認を得てから実装に入る。**
1. **`conformance-tests/adapter.py` を port v1.11 へ**。追加は 2 項目、削除は無い。
   - **`isolated_application_surface()`** — 使い捨ての data-plane instance を張る context manager。**yield するのは port 準拠の adapter instance** (小さな conformance profile を宣言する新 service に束縛した同型の adapter)。**テストは通常の port 操作でそれを叩く。** **テスト終了時に close する。**
   - **`idempotency_key` の optional フィールド** — **`BatchOperation` / `ScopedBatchOperation` の optional フィールドとして足す** (設計 §7.1 の 2 が挙げる 2 案のうち、**payload 側の optional フィールド**を採る。既存メソッドの任意引数は採らない — 4 plug すべてで同じ経路を通すため)。**追加はこの 1 フィールドだけであり、肯定側の primitive は足さない** (裁定 S-4)。
2. **4 plug への実装** (r2db in-process / r2db HTTP / MitateDB in-process / MitateDB HTTP)。
3. **`conformance-tests/test_c05_limit_declaration_agreement.py`** (新設) — V1 (a)〜(e) / V2 / V3。**構造は C-17 と同じ「宣言で分岐し、非 enabled 側は skip せず宣言の正直さを assert する」形。**
4. **`MitateDB-api/src/mitatedb_api/cell.py` の `limit_enforcement` ブロック (`:1494-1504`) への明示エントリ追加** — 欠落 4 class (`execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth`)。**うち 3 つは `unavailable`**、**`operation_depth` は実測で二枝** (下記)。**((β) は 2026-09-05 の依頼者裁定で「WP-4 同梱」に確定した — 宣言と検証を同一コミットに載せる。7-A へ先出ししない。§0.2 の 6)**
5. **`conformance-tests/test_c14_authority_boundary.py:639-650` の stale 注釈の訂正** (`limit_class` は契約が保証しない、という記述)。**assert 自体を hard へ上げるかは C-14 の射程であり本フェーズでは決めない。**
6. **`conformance-tests/CONDITIONS.md` の C-05 行** — Status を `executable (four adapters) -- …` へ、**開示 5 事項**を書く。**C-19 / C-14 / C-16 行に C-05 との重なりの参照を足す。**
7. **`docs/design/CONFORMANCE_ADAPTER_V1.md` §21 (v1.11) の新設**と**文書情報の版数行の更新** (§20 = v1.10 と同じ構成)。
8. **設計 §13 への実測記録** — D-6.2 の駆動レシピ・検査形の全 plug 実測結果、`operation_depth` の枝、V3 の xfail 確定件数。

#### `operation_depth` の二枝 (実測で決まる)

- **MitateDB が filter / 操作の入れ子深さを実際に有限で拒否している**なら → `enforced` + `limits` 値を宣言し、**V2 の駆動対象に入れる**。
- **していない**なら → `unavailable` と宣言し、**V3 の xfail と L7-1 の対象に 4 番目の class として加える**。

**どちらであるかを実装担当が事実として確かめ、根拠 (`file:line`) を完了報告に書く。** 推測で決めない。

#### 完了条件 (検証可能な形)

1. **§D-6.5 追補が記入され、監督承認を得ている** — **監査照合**: 監査は追補の本文が **control plane の非対称と data plane の経路を区別して書いている**ことと、承認の記録が完了報告にあることを確認する。**着手条件であるから、実装差分より前に確定していること。**
2. **port v1.11 の `isolated_application_surface()` が port 準拠の adapter instance を yield する** — **監査照合**: 監査は 4 plug の実装が**同型の adapter を返す**こと (単一 callable ではない)、**その instance の `capabilities()` が返す宣言と検証対象が同一である**こと、**必要な操作が D-6.2 の駆動レシピから逆算されている**ことを確認する。
3. **port v1.11 の `idempotency_key` optional フィールドが 4 plug で実リクエストに載る** — **adapter の加工なしに載せられる**こと。**肯定側の primitive (key の生成・保管・再送・結果比較) を足していない**こと。**監査照合**: 監査は追加が `BatchOperation` / `ScopedBatchOperation` の optional フィールド 1 つに閉じていることを確認する。**このフィールドを実際に使うのは WP-5 である。**
4. **V1 (a) と (d) が 4 plug 全数で実行される** — (a) は `limit_enforcement` / `limits` のキーが `limits.classes` の部分集合であること、(d) は **`unavailable` / `deployment_required` のエントリに `limits` 側の制約を置かない**こと。**対照 D**: **MitateDB in-process の `request_bytes` を「値あり + `unavailable`」のまま走らせて緑であること**を確認する (撤回した規則が復活していないことの確認。D-6.11)。 **変異 12** ((a) 専用: いずれかの plug の `limit_enforcement` に `limits.classes` 外のキーを一時的に足す → 語彙外として赤。設計 D-6.11、監督追加 2026-09-05)。
5. **V1 (b)** — `limits` に値を持つ class がすべて `limit_enforcement` にエントリを持つこと。変異 1。
6. **V1 (c)** — **`enforced` / `reference_wall_clock`** のエントリが `limits` に**有限値 (integer ≥ 1)** を持つこと。**`deployment_required` は対象外である** (B-7)。変異 2。
7. **V1 (e)** — 必須エントリ集合 (**固定 9 + capability 条件付き 3**) の各 class に明示エントリがあること。**適用面は application plane のみ**であり、**control plane の必須集合は C-14 が駆動する 3 class + `audit_query` 条件付きの `audit_requests_per_minute` の計 4 class** である。変異 3。
8. **MitateDB の欠落 4 class に明示エントリがある** — 3 つは `unavailable`、`operation_depth` は実測の枝。**契約は変わらない** (peer-local の宣言変更である)。**監査照合**: 監査は `git diff -- MitateDB-api/src/mitatedb_api/cell.py` が `limit_enforcement` ブロックの追加に限られることを確認する。
9. **`operation_depth` の枝が実測で決まっている** — **監査照合**: 監査は完了報告の根拠 (`file:line`) と、宣言の値、V2 / V3 のどちらに入ったかの整合を確認する。
10. **V2 の駆動集合が宣言から導出される** — **(その plug が実際に叩く surface の capability 文書で `enforced`) ∩ (D-6.2 で検査形を持つ class)**。**固定リストを書かない。** **plug ごとに差が出るのは正しい挙動である** (in-process の `request_bytes` は駆動せず、HTTP plug でだけ駆動対象になる)。変異 4・5・6。
11. **V2 が `details.limit_class == class` を検査する** — **両側検査・片側検査の両方で必須である** (契約 `errors.details_vocabulary.LIMIT_EXCEEDED.limit_class` は "string, required"、`versioning.version_binding` が 1.2.0 の義務として列挙)。変異 5。
12. **V2 の per-plug 非空性** — **各 plug について、駆動した class が 1 つ以上あることをその plug のテスト内で assert する** (C-17:182-218 と同型)。**session 横断の集約 guard は採らない。** 変異 7。
13. **V2 の上限 assert と headroom 前提** — **(a)** 各駆動 class の `limits` 値が **C-14 の `_MAX_EXERCISABLE_LIMIT` 相当以下**であること (`test_c14_authority_boundary.py:141` / `:476` と同型)、**(b)** **`requests_per_minute` を駆動する前に、他 class の駆動が消費する最悪ケースを検算した headroom 前提を assert する** (同 `:490-511` と同型)。**あるいは class ごとに新しい `isolated_application_surface()` を張る** — **どちらを採ったかを port の docstring に明記する。** 変異 8。
14. **V3 が固定 9 の静的 parametrize である** — **宣言から導出しない**。各 (plug, class) の組について「この class は `unavailable` 以外である」ことを assert し、**現時点で `unavailable` である組にだけ `xfail(strict=True)` を静的に付ける**。**reason に L7-1 を名指しする。** 件数は **7 または 9** (`operation_depth` の枝で決まる)。変異 9・10 と対照 E。
15. **隔離 surface の資源検査 (e)** — `isolated_control_surface()` / `isolated_application_surface()` について、**呼び出しの前後で資源が戻ることを assert する** (PG plug は `pg_stat_activity` の件数、in-memory plug は live pool 数)。変異 11。
16. **D-6.2 の分類が全 plug で実測され、設計 §13 に記録されている** — **両側が成立した class を増やすのは可**、**両側から片側へ、または片側から「駆動しない」へ落とすには理由の開示が要る**。**監査照合**: 監査は §13 の確定分類と C-05 行の開示、およびテストの vector 一覧を三者突合する。
17. **C-14 の stale 注釈が訂正され、L6-19 が閉じている** — **監査照合**: 監査は `test_c14_authority_boundary.py:639-650` の注釈が契約 `details_vocabulary` を根拠に書き換わっていること、`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 の L6-19 が「契約が既に `limit_class` を必須化しているので手当て候補 (i) は済んでいる」として閉じていること、**assert 自体を hard へ上げていない** (C-14 の射程を侵していない) ことを確認する。
18. **`CONDITIONS.md` の C-05 行** — Status が `executable` で始まり、**開示 5 事項** ((1) 駆動しない 3 class と理由、(2) 片側検査へ落とした 3 class と理由および片側検査が「宣言値 N が正しいこと」を測っていないこと、(3) `enforced` と宣言されているが検査形が無く駆動集合から外れる class と理由、(4) `unavailable` の class は V1 の整合検査と V3 だけが掛かること、(5) V1 (e) が契約の義務ではなく共通 suite の追加要件であること) が書かれていること。**Status 更新は `@pytest.mark.condition("C-05")` の追加と同一コミットである** (§0.2 の 5)。**C-19 / C-14 / C-16 行に重なりの参照がある**こと。
19. **`CONFORMANCE_ADAPTER_V1.md` に §21 (v1.11) があり、文書情報の版数行が更新されている** — **監査照合**: §20 と同じ構成 (追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**§9 完了条件には追記しない。**
20. **対応表に対応の無い行が無いこと** (メタ条件)。
21. **完了ゲート** — `failed` 0 / **`skipped` 0** / **`xfailed` = 7 または 9 (+ 着手時点の既存分)**。`passed` の増減内訳を完了報告に書く。**xfailed が想定と違う値なら完了と判定しない。**

#### 非 vacuity 要件

- **V1 / V2 / V3 のいずれも「4 plug 全数で観測対象がある」ことを示す** — V2 は**完了条件 12 の per-plug 非空性 assert が機構として担保する**。V1 / V3 は 4 plug で収集され実行されることを、収集 id の一覧で示す。
- **変異は全 plug で赤にした実測を報告に添える** (常設規律 1)。**plug ごとに駆動集合が異なるので、「1 plug で赤になった」で済ませない** — どの plug のどの class で赤になったかを class 名つきで報告する。
- **`xfail(strict=True)` が「静的 mark である」ことの実測**: **対照 E** (下記) で、`unavailable` の明示宣言を足しただけでは XPASS しないことを示す。

#### 確定文言のファイル所在

- **依頼者裁定 3 の逐語は設計 §5** にある。**L7-1 の reason 文と CONDITIONS の開示文に裁定の趣旨を書く場合は、設計 §5 から複製し言い換えない** (常設規律 4)。
- **V1 (e) の位置づけの開示文は設計 §8 の V1 (e) 段落が正本**である。**C-05 行には同文を書く** (設計 D-6.1 の指示)。
- **C-05 の 5 開示事項の内容は設計 §7.3 と D-6.2 の「開示する事項」が正本**である。

#### 同型性テスト対象

**両 peer に同名ヘルパを置く場合のみ、対応表 `_ISOMORPHIC_TARGETS` に行を足す** (両 peer の `tests/test_audit_query.py`)。**本 WP の成果物のうち、両 peer の `src` に同名で置くものは現時点で想定されていない** — MitateDB の宣言追加は peer 固有であり、r2db は無変更である。**同名ヘルパを置く必要が生じたら、実装前に監督へ上げる** (常設規律 5)。**対応表に行を足す場合は、WP-5 の完了条件 8 と同じ手順 (行数を含む pin テスト名の更新、表内の自己参照行の更新) を踏む。**

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 D-6.5 追補 | **監査照合** |
| 2 `isolated_application_surface()` の形 | **監査照合** (資源検査は完了条件 15 の変異 11 が測る) |
| 3 `idempotency_key` フィールド | **監査照合** (実使用は WP-5) |
| 4 V1 (a)(d) | **変異 12** ((a): 語彙外キー) + **対照 D** ((d)、非変異。緑であることの確認) |
| 5 V1 (b) | **変異 1** |
| 6 V1 (c) | **変異 2** |
| 7 V1 (e) | **変異 3** |
| 8 MitateDB の 4 class | **監査照合** |
| 9 `operation_depth` の枝 | **監査照合** |
| 10 V2 の駆動集合 | **変異 4** + **変異 6** |
| 11 `details.limit_class` | **変異 5** |
| 12 V2 の per-plug 非空性 | **変異 7** |
| 13 上限 assert と headroom | **変異 8** |
| 14 V3 の静的 parametrize と xfail | **変異 9** + **変異 10** + **対照 E** |
| 15 資源検査 (e) | **変異 11** |
| 16 D-6.2 の実測と §13 記録 | **監査照合** |
| 17 C-14 注釈と L6-19 | **監査照合** |
| 18 C-05 行と Status | **監査照合** (同一コミット規律は register テストが機械的に強制する) |
| 19 §21 (v1.11) | **監査照合** |
| 20 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 21 完了ゲート | **監査照合** |

1. **V1 (b)** — `limits` に値だけがあって `limit_enforcement` にエントリが無い class を一時的に作る → **赤**。
2. **V1 (c)** — `enforced` のエントリから対応する `limits` の値を落とす (または 0 にする) → **赤**。
3. **V1 (e)** — MitateDB の `limit_enforcement` から固定 9 のうち 1 class を一時的に落とす → **欠落として赤**。
4. **V2 の位置** — 宣言値 N を +1 して実挙動と食い違わせる → **両側検査の class で位置がずれて赤**。
5. **V2 の `limit_class`** — `details.limit_class` を別名にする → **赤** (両側・片側の両方で効く)。
6. **V2 の交差規則** — in-process 面の `request_bytes` を `enforced` と偽る → **駆動集合に入り、片側検査の「明らかな超過が拒否される」が成立せず赤**になる。
7. **V2 の per-plug 非空性** — ある plug の宣言を全 class `unavailable` に倒す → **駆動 class 0 で赤** (静かに緑にならないことの確認)。
8. **V2 の headroom 前提** — 隔離 profile の `requests_per_minute` を、他 class の駆動が消費する最悪ケースを下回る値に設定する → **headroom の前提 assert が赤**。
9. **V3 の XPASS** — MitateDB の 1 class を `unavailable` から `enforced` へ上げる (= L7-1 の実装が入った状態を模す) → その class の xfail が **XPASS** → `strict=True` で**赤** (**これが撤去の合図である**)。
10. **V3 の strict** — `xfail` の `strict=True` を落とす → 変異 9 の状態で**赤にならなくなる**こと (strict が load-bearing であることの実測)。**実測後に必ず戻す。**
11. **資源検査 (e)** — 隔離 surface の context manager の close を外す → **資源が戻らず赤**。
12. **V1 (a) 語彙外キー** — いずれかの plug の `limit_enforcement` に `limits.classes` に無いキー (合成名) を一時的に足す → **語彙外として赤** (完了条件 4 の (a) 側。監督追加 2026-09-05、設計 D-6.11 と対)。
- **対照 D (非変異)** — MitateDB in-process の `request_bytes` を「値あり + `unavailable`」のまま走らせて **緑であること**。**これは変異ではなく、撤回した規則 (「`unavailable` の class は `limits` に値を持たない」) が復活していないことの確認である** (裁定 S-1)。
- **対照 E** — `unavailable` の明示宣言を足すだけでは **XPASS しない**こと (`unavailable` である限り vector は落ち続ける)。**xfail の先置きと宣言追加が同一 WP に同居できる根拠の実測である。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q conformance-tests/test_c14_authority_boundary.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

**完了ゲート (監督のみ、単独実行)**:

```
./.venv/bin/python -m pytest -q -n 5 --dist loadgroup
```

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **契約を変えない** — `spec/` と両 peer のパッケージ内コピーに 1 バイトも触らない。**`limits.classes` の 16 語も `limit_enforcement` の 4 語も既存のまま使う。**
2. **V2 の駆動集合を固定リストで書かない** — 宣言から導出する。**固定除外リストを書くのは、宣言を偽っても赤にならない形にすることである。**
3. **V3 の parametrize 基底を宣言から導出しない** — 静的な固定 9 である。**宣言由来にすると、宣言が上がった瞬間に組が収集されなくなり、strict の赤 (撤去の合図) が出ない。**
4. **skip を使わない** — 非 enabled 側は skip せず、**宣言の正直さを assert する** (C-17 型)。**`skipped` は 0 のままである。**
5. **`xfail` の `strict=True` を落として緑にしない。** guard を弱めない。**緑にする正しい手段は実装を真にすることだけである** (それは L7-1 の範囲であり本 WP ではない)。
6. **C-14 の assert を hard へ上げない** — 注釈の訂正だけが本 WP の範囲である (C-14 の射程は別項)。
7. **C-16 の既存 vector と同じ assert を二重に書かない** — `batch_entities` の原子性は C-16 が固定している。**参照する。**
8. **肯定側の idempotency primitive を足さない** (裁定 S-4、L7-8)。
9. **MitateDB の資源上限を実装しない** — 裁定 3 のとおり L7-1 の次フェーズ候補である。**「ついでに」実装すると、本 WP が測るはずの fail-loud が空振りする。**
10. **(β) の確定内容から外れない** (§0.2 の 6) — **宣言追加を 7-A へ先出しせず、宣言と検証を同一コミットに載せる。**
11. **制約・制限の追加で問題を回避しない** — 駆動しにくい class を「駆動しない」へ落として済ませるには**理由の開示が要る** (完了条件 16)。**黙って落とさない。**

---

### WP-5 (a) 他 5 条件 + (d) surfaces ヘルパの重複解消

**着手条件: Q4 の main マージ後。**

#### 目的

**port 変更を要さない 5 条件 (C-00 / C-02 / C-04 / C-07 / C-10) を共通 suite に載せ、両 peer の同一性を固定する。** あわせて L6-17 (r2db の `surfaces` 検証ヘルパが同型性の対応表に載らない) を閉じる。

#### 前提として読む箇所 (設計)

**§1.1**、**§1.6 の 5**、**§3 D-6.7** (5 条件の命題・C-10 の走査機構・C-07 の宣言分岐)、**D-6.8**、**D-6.11**、**§7.2**、**§7.3**、**§11 L7-7 / L7-8**、**裁定 S-4**。

#### 成果物

1. **`conformance-tests/test_c04_unsupported_and_safe_errors.py`** — unsupported operation が **`CAPABILITY_UNSUPPORTED` で実行前に**返ること + **誤入力の error body に stack trace / SQL 断片 / DSN 形が無いこと** (負の内容検査)。
2. **`conformance-tests/test_c10_no_bypass_material_on_the_wire.py`** — **adapter 境界水準**: 応答に credential-bearing 文字列・DSN 形・環境変数の値が無いこと。**走査機構は `conformance-tests/conftest.py` 側に置く** (下記)。
3. **`conformance-tests/test_c02_runtime_privilege_negative.py`** — **runtime credential** による schema 操作 / control 操作が拒否されること。
4. **`conformance-tests/test_c07_atomicity_and_retry.py`** — **(i) 原子性** (単一 entity の batch に無効 item を 1 つ混ぜ、**全部ロールバック**。書き込み 0 件を read で確認。4 plug 全数) + **(ii) idempotency の宣言分岐** (下記) + **per-plug 非空性**。
5. **`conformance-tests/test_c00_application_escape.py`** — application credential が **control surface / 他 application** で拒否されること。**C-01 / C-14 が既に固定している部分は参照し、欠けている vector だけ足す。**
6. **`conformance-tests/conftest.py`** — **C-10 の走査 fixture**: **adapter の公開メソッドを generic proxy で包み、戻り値と error payload を JSON 直列化して走査する**。**port は増やさない** (§7.1 の追加項は WP-4 の 2 のままである)。**in-process の 2 plug にも効く形であること。**
7. **`conformance-tests/CONDITIONS.md` の 5 行** — Status を `executable (four adapters) -- …` へ。**射程の限界を各行に開示する。**
8. **(d) r2db の `surfaces` 検証ヘルパの 1 モジュール化** — `r2db-api/src/r2db_api/main.py:208` と `control_main.py:238` の `_validate_surface_base_url` の 2 コピーを **1 モジュールへ寄せる**。**両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` に行を足す** (MitateDB 側の対応物は `src/mitatedb_api/surfaces.py::_validate_surface_base_url`)。

#### C-07 (ii) の宣言分岐 (裁定 S-4)

- **`idempotency` が `unavailable` の plug**: 「**`idempotency_key` 付きの要求が実行前に `CAPABILITY_UNSUPPORTED` で拒否され、副作用が 0 件である**」ことを assert する。**skip しない。** 副作用 0 件は (i) と同じ read で確認する。
- **`unavailable` 以外を宣言する plug**: 「**同一 key の再送が同一結果を返す**」ことを assert する。
- **空振り防止は per-plug の非空性 assert である** — **各 plug について、宣言分岐のどちらか一方の枝が必ず実際に観測されたことを、その plug のテスト内で assert する** (C-17:182-218 と同型)。**session 横断の集約 guard は採らない。** **現時点では 4 plug すべてが `unavailable` 枝で観測される。**

#### 完了条件 (検証可能な形)

1. **C-04 の命題が 4 plug 全数で固定されている** — unsupported operation が `CAPABILITY_UNSUPPORTED` で**実行前に**返ること。変異 1。
2. **C-04 の負の内容検査** — 誤入力の error body に **stack trace / SQL 断片 / DSN 形**が無いこと。変異 2。
3. **C-10 の走査機構が conftest 側にある** — **adapter の公開メソッドを generic proxy で包み、戻り値と error payload を JSON 直列化して走査する**。**port を増やしていない**こと。**監査照合**: 監査は `conformance-tests/adapter.py` の差分が **0 行**であることを確認する (port は WP-4 の v1.11 のままである)。
4. **C-10 の負の内容検査が 4 plug 全数で効く** — 応答に credential-bearing 文字列・DSN 形・環境変数の値が無いこと。変異 3。
5. **C-02 の命題が固定されている** — runtime credential による schema 操作 / control 操作が拒否されること。変異 4。
6. **C-07 (i) 原子性が 4 plug 全数で固定されている** — **書き込み 0 件を read で確認する**こと。変異 5。
7. **C-07 (ii) の宣言分岐が実装されている** — `unavailable` 枝で「実行前拒否 + 副作用 0 件」、`unavailable` 以外の枝で「同一 key 再送が同一結果」。**skip しない。** 変異 6。
8. **C-07 の per-plug 非空性** — 各 plug でどちらか一方の枝が実際に観測されること。**観測されなければその plug で赤**。変異 7。
9. **C-00 が既存の被覆を二重に書いていない** — **C-01 / C-14 が固定している部分は参照し、欠けている vector だけを足す**。変異 8。**監査照合**: 監査は新規 vector と C-01 / C-14 の既存 vector の対応を突き合わせ、重複が無いことを確認する。
10. **`CONDITIONS.md` の 5 行の Status が `executable` で始まり、射程が開示されている** — **C-10 行は「adapter 境界水準」または「plug が返す応答の全内容」と書き、「wire 水準」とは書かない** (L7-7)。**「射程は各 worker が観測した応答の範囲である」ことと「PG 権限の証拠は peer-local 参照のまま」であることを書く。** **C-07 行は「両 peer とも `idempotency: unavailable` であり、共通 suite が測るのは実行前拒否と副作用 0 件であって、再送同一結果の肯定側は現時点で空である」ことを書く。** **Status 更新はマーカー追加と同一コミットである** (§0.2 の 5)。
11. **(d) r2db の `surfaces` 検証ヘルパが 1 モジュールに寄っている** — `main.py` / `control_main.py` の 2 コピーが消え、両者が同一モジュールを参照すること。**変更は重複解消に限り、検証の挙動を変えない** (既存の起動時検査の形・エラーメッセージ・suffix 検査を保つ)。変異 9。
12. **同型性の対応表に行が足されている** — **`_ISOMORPHIC_TARGETS` は現行 18 行であり、本 WP で 19 行になる**。**行数を名前に含む pin テスト (`test_isomorphic_target_table_is_pinned_to_its_current_18_rows`) の名前を新しい行数へ更新し、あわせて表の中にあるそのテスト自身を指す行も更新する** — **表は自分自身の pin テストを行として含んでいるので、名前を変えると表の行も変わる**。**両 peer の同名ファイルで同時に行う。** 変異 10。
13. **L6-17 が閉じている** — **監査照合**: 監査は `PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 の L6-17 に閉止の状態が付き、閉じた根拠 (対応表の行) が書かれていることを確認する (**記録の確定は WP-8**。本 WP は実体を作る)。
14. **対応表に対応の無い行が無いこと** (メタ条件)。
15. **完了ゲート** — `failed` 0 / **`skipped` 0** / `xfailed` は **WP-4 完了時点から不変** (本 WP は xfail を増やさない)。`passed` の増減内訳を完了報告に書く。

#### 非 vacuity 要件

- **5 条件のいずれも「観測対象が 1 件以上ある」ことを 4 plug 全数で assert する** (常設規律 1)。**C-07 は完了条件 8 の per-plug 非空性 assert が機構として担保する。**
- **C-10 の generic proxy が「実際に応答を見ている」ことを示す** — **変異 3 が 4 plug すべてで赤になる**こと。**in-process の 2 plug でも赤になる**ことを明示的に報告する (この形を採った理由がそこにある)。
- **C-00 の新規 vector が load-bearing であることを示す** — 既存 C-01 / C-14 を無効化しても新規 vector が独立に赤になることを、変異 8 で示す。

#### 確定文言のファイル所在

- **C-10 の語法 (「adapter 境界水準」、「wire 水準」と書かない) は設計 D-6.7 と L7-7 が正本**である。
- **C-07 の宣言分岐の形は裁定 S-4 (設計 D-6.7 に反映済み)** が正本である。**言い換えない。**

#### 同型性テスト対象

**`_ISOMORPHIC_TARGETS` に 1 行を追加する** — r2db 側の新モジュール上の `_validate_surface_base_url` と、MitateDB 側の `src/mitatedb_api/surfaces.py::_validate_surface_base_url` の対。**行の形は既存行と同じ (自 peer 相対パス, 兄弟 peer 相対パス, シンボル名) である。** **18 行 → 19 行**であり、**pin テストの名前と、表の中のそのテストを指す行の両方を更新する** (完了条件 12)。**行頭インデントの保存・自己比較の構文的禁止・不在も内容不一致も赤、という既存の性質を落とさない。**

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 C-04 実行前拒否 | **変異 1** |
| 2 C-04 負の内容検査 | **変異 2** |
| 3 C-10 の走査機構が conftest 側 | **監査照合** |
| 4 C-10 負の内容検査 | **変異 3** |
| 5 C-02 | **変異 4** |
| 6 C-07 (i) 原子性 | **変異 5** |
| 7 C-07 (ii) 宣言分岐 | **変異 6** |
| 8 C-07 per-plug 非空性 | **変異 7** |
| 9 C-00 | **変異 8** |
| 10 CONDITIONS 5 行 | **監査照合** |
| 11 surfaces ヘルパの 1 モジュール化 | **変異 9** |
| 12 対応表 19 行と pin テスト | **変異 10** |
| 13 L6-17 閉止 | **監査照合** |
| 14 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 15 完了ゲート | **監査照合** |

1. **C-04 の実行前性** — unsupported operation が実行後に拒否される形へ一時的に変える (または `CAPABILITY_UNSUPPORTED` を別コードにする) → **赤**。
2. **C-04 の負の内容検査** — 誤入力の error body に **stack trace 断片**を 1 つ混ぜる → **赤**。
3. **C-10 の負の内容検査** — 応答に **DSN 形の文字列**を 1 つ混ぜる → **4 plug すべてで赤** (in-process 2 plug を含むことを明記する)。
4. **C-02** — runtime credential に対する拒否分岐を 1 つ外す → **赤**。
5. **C-07 (i)** — batch のロールバックを外して部分適用にする → **書き込みが残り赤**。
6. **C-07 (ii)** — `idempotency_key` 付き要求の実行前拒否を実行後拒否へ変える (または副作用が残る形にする) → **赤**。
7. **C-07 の per-plug 非空性** — ある plug で宣言分岐のどちらの枝にも入らない状態を作る → **その plug で赤**。
8. **C-00** — 他 application への到達拒否を 1 つ外す → **赤**。**あわせて C-01 / C-14 の既存 vector を無効化しても新規 vector が独立に赤になる**ことを示す。
9. **同型性の片側崩し** — 片側 peer の `_validate_surface_base_url` の判定を 1 箇所だけ変える (比較 1 つ) → **同型性テストが赤**。**新しく足した行が実際に突き合わされていることの実測である。**
10. **対応表の縮小** — 対応表から **本 WP で足した 1 行を落とす** → **pin テストが赤**。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_c04_unsupported_and_safe_errors.py \
    conformance-tests/test_c10_no_bypass_material_on_the_wire.py \
    conformance-tests/test_c02_runtime_privilege_negative.py \
    conformance-tests/test_c07_atomicity_and_retry.py \
    conformance-tests/test_c00_application_escape.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q r2db-api/tests MitateDB-api/tests
```

**完了ゲート (監督のみ、単独実行)**: `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **port を増やさない** — C-10 の走査は conftest 側の generic proxy である (B-6)。`adapter.py` の差分は 0 行である。
2. **「wire 水準」と書かない** — in-process の 2 plug には wire が無い (L7-7)。
3. **skip を使わない** — C-07 の `unavailable` 枝も skip せず assert する。
4. **肯定側の idempotency primitive を足さない** (L7-8)。
5. **`surfaces` ヘルパの重複解消で挙動を変えない** — 起動時検査の形・エラーメッセージ・suffix 検査を保つ。**「ついでに」検証を強めない/弱めない。**
6. **peer 間でコードを共有しない** — 同名ヘルパは同型性テストで固定する (常設規律 6)。
7. **C-01 / C-14 / C-16 の既存 vector と同じ assert を二重に書かない。**
8. **PG 権限そのものを共通 suite で検査しようとしない** — 共通 suite は adapter 越しにしか peer を見ない。**peer-local 証拠の参照のままとし、射程を開示する** (L7-7)。

---

### WP-6 (b)(iii) DeprecationWarning の error 化

**着手条件: Q4 の main マージ後 (かつ WP-5 の完了後)。**

#### 目的

**警告を消すのではなく原因を消す。** `error::DeprecationWarning` を有効化しても集計行が変わらない状態にする。

#### 前提として読む箇所 (設計)

**§1.2** (12 箇所の内訳)、**§3 D-3 の「pytest 設定の一本化」**、**§3 D-4**、**§4 の 6**。

#### 成果物

1. **root `pyproject.toml`** の `[tool.pytest.ini_options]` に **`filterwarnings = ["error::DeprecationWarning"]`** を置く。
2. **第一案**: `httpx2` を両 peer の `[test]` extras に足し、`constraints.txt` で pin する。**または代替**: **12 箇所を `httpx.ASGITransport` へ書き換える** (`r2db-api/tests/test_credential_persistence.py` 4 箇所、`test_audit_query.py` 5 箇所、`test_surfaces_env.py` 3 箇所)。

#### 完了条件 (検証可能な形)

1. **`filterwarnings = ["error::DeprecationWarning"]` が root `pyproject.toml` にある** — **監査照合**。
2. **第一案を採る場合、`httpx2` の提供元確認が済んでいる** — **PyPI 上の提供元が Starlette / encode 系の公式配布であることを確認済みである**こと。**確認できなければ第一案は採らず、代替へ切り替える** (B-11)。**監査照合**: 監査は確認の根拠 (何をもって公式配布と判断したか) が完了報告にあることを確認する。**素性を確認していない PyPI 名を test extras に足したまま完了としない。**
3. **代替を採る場合、12 箇所すべてが `httpx.ASGITransport` へ移っている** — `starlette.testclient` を import するモジュールが **0 件**であること。**既存 54 箇所と同型である**こと。
4. **集計行が不変である** — **`error::DeprecationWarning` を有効化したうえで、WP-5 完了時点の `passed` / `failed` / `skipped` / `xfailed` の 4 数がすべて一致する**こと。
5. **`error::DeprecationWarning` が load-bearing である** — 変異 1。
6. **個別 `ignore` を置いていない** — **台帳項目を付けた場合にのみ許す** (D-3)。**監査照合**: 監査は `filterwarnings` に `ignore` 行が無いこと、あるなら対応する台帳項目が設計 §11 にあることを確認する。
7. **`constraints.txt` が更新されている** (第一案の場合) — **依存を上げるときは constraints を更新したコミットに集計行を添える** (D-3 の更新規約)。**監査照合**。
8. **対応表に対応の無い行が無いこと** (メタ条件)。
9. **完了ゲート** — 完了条件 4 と同じ。**skipped 0。**

#### 非 vacuity 要件

- **変異 1 は `filterwarnings` が有効な状態で行う** — 有効化前に試すと当然に緑であり、何も測っていない。
- **「12 箇所を直した」ことを、`starlette.testclient` の import が 0 件であることで示す** (代替の場合)。**箇所数の申告だけで済ませない。**

#### 確定文言のファイル所在

**なし。**

#### 同型性テスト対象

**なし。**

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 `filterwarnings` の設置 | **変異 1 が包括的に担保する** |
| 2 `httpx2` の提供元確認 | **監査照合** |
| 3 12 箇所の移行 | **監査照合** (`starlette.testclient` の import が 0 件) |
| 4 集計行不変 | **監査照合** |
| 5 error 化が load-bearing | **変異 1** |
| 6 個別 ignore 不在 | **監査照合** |
| 7 constraints の更新 | **監査照合** |
| 8 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 9 完了ゲート | **監査照合** |

1. **`DeprecationWarning` を意図的に発する一時テストを足す** → **赤**になること。**復元する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

**完了ゲート (監督のみ、単独実行)**: `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **`ignore::StarletteDeprecationWarning` の一括 ignore を置かない** (設計 §4 の 6)。**ignore は「error 化した」という主張を空にする。**
2. **素性を確認していない PyPI 名を `[test]` extras に足さない** (B-11)。**公開直前のリポジトリである。**
3. **`error::DeprecationWarning` 以外のカテゴリを一緒に error 化しない** — 本 WP の範囲は `DeprecationWarning` である。
4. **集計行を変える変更を混ぜない** — テストの追加・削除を伴う変更は本 WP に含めない。

---

### WP-7 (i) 現行結論と履歴の分離

**着手条件: Q4 の main マージ後。**

#### 目的

**「現在有効な結論」を短時間で抽出できる状態にし、蓄積の再発を機械的に止める。** 想定消費者は AI エージェントであり、抽出しにくい状態は「宣言は確実に読まれる」という前提を直接損なう。

#### 前提として読む箇所 (設計)

**§1.5** (現況の実測値)、**§1.6 の 1・3・4**、**§3 D-7** (元ファイルの行の形・companion・仕分け基準・更新規約・機械固定 4 項目・上限の根拠)、**§4 の 9〜11**、**§11 L7-9 / L7-10**。

#### 成果物

1. **`security/CONTROL_MAPPING_HISTORY.md`** / **`conformance-tests/CONDITIONS_HISTORY.md`** (新設) — **見出しは ID のみ** (`## SI-10` / `## C-19` 型。タイトルを付けない)。**履歴本文は逐語で移す — 書き換えない。**
2. **`security/CONTROL_MAPPING.md`** / **`conformance-tests/CONDITIONS.md`** の現行行化 — 各行は「**現行の担保 (短文) + 証拠 (テスト名・`file:line`) + `[history](CONTROL_MAPPING_HISTORY.md#si-10)` 形のリンク**」。**列構造は維持する** (`CONDITIONS.md` は 5 列、`CONTROL_MAPPING.md` は 4 列)。**セル内に生の `|` を置かず、1 行 1 レコードを保つ。**
3. **更新規約** — 「**訂正は現行行を書き換え、旧文は履歴へ移す**」。**表の外の前文に散文で置く** (C-1)。**`CONDITIONS.md` は `|` 始まりの表を 1 つだけ持つ。**
4. **`conformance-tests/test_conditions_register.py` の拡張**と **`conformance-tests/test_control_mapping_register.py` の新設** — 機械固定 4 項目 (下記)。

#### 機械固定 4 項目 (D-7)

1. 各 ID 行が companion の該当 anchor へのリンクを持つ。
2. **リンク断片と等しい slug の見出しが companion にある** — 「見出しがある」ではなく**アンカーが解決すること**を検査する (**slug 化規則をテスト側に持たせる**)。
3. **`ID` 列に重複が無い** — 現行 parser は `result[cid] = status` で同一 ID の重複行を黙って上書きする。
4. **主表の各セルの長さ上限** — **行全体ではなくセル単位**に掛ける。**確定値は実装 WP が仕分け後の最長セルから決めて設計 §13 に記録する。目安は 2,500 文字である** (`CONDITIONS.md` の Condition 列だけで C-17 が 1,788 文字あり、この列は履歴を含まない。1,500 では仕分けを完璧にやっても割れない)。

#### 仕分け基準 (人手。機械化不能)

- **現行** = 今日の code / tests の状態、および**開示された射程の限界**。
- **履歴** = 置換された主張、訂正の経緯、WP 進捗注記、日付付きの状態注記。
- **日付 / WP マーカーで機械的に切らない** — マーカーは「変更があった」印であって「もう真ではない」印ではない。**C-19 行の Honest limits (a)〜(e) は日付マーカーの後ろにあるが現在も有効な制約である** (反例)。

#### 完了条件 (検証可能な形)

1. **companion 2 本があり、見出しが ID のみである** — `## SI-XX` / `## C-XX` 型。**タイトルを付けていない**こと (付けると slug が変わりリンクが解決しない)。**監査照合 + 変異 1 が anchor 解決を担保する。**
2. **履歴が逐語で移っている** — **監査照合**: 監査は移動元の文言と companion の文言を突き合わせ、**書き換え・要約・省略が無い**ことを確認する (監査履歴としての価値がある)。
3. **元 2 ファイルの各行が「現行の担保 + 証拠 + history リンク」の形である** — 列構造が維持され、**セル内に生の `|` が無く、1 ID = 1 行**であること。
4. **更新規約が表の外の前文に散文で置かれている** — **`CONDITIONS.md` が `|` 始まりの表を 1 つだけ持つ**こと (`test_conditions_register.py:32` の parser 前提)。**監査照合 + register テストが緑であること。**
5. **register テストが anchor の解決を検査する** — slug 化規則をテスト側に持ち、**リンク断片と等しい slug の見出しが companion にある**ことを検査する。変異 1。
6. **全 ID が companion に見出しを持つ** — 元ファイルの全 ID について。変異 1 が同じ機構を担保する。
7. **セル長上限が主表の各セルに掛かっている** — `CONDITIONS.md` の 5 列 / `CONTROL_MAPPING.md` の 4 列のいずれにも。**確定値を設計 §13 に記録する。** 変異 2。
8. **`ID` 列の重複禁止 assert がある** — 変異 3。
9. **`test_control_mapping_register.py` が新設されている** — `CONTROL_MAPPING.md` を機械解析するコードは現行 0 件であり、本 WP が初めて置く。**条件 ID を持たないテストである** (`@pytest.mark.condition` を付けない)。
10. **落ちた制約が無い** — **レビューの独立項目**である (L7-10)。**監査照合**: 監査は**現行行から現行の制約が落ちていないこと**を人手で突合する。**C-19 の Honest limits (a)〜(e) が最も落ちやすい形である。** **機械検査は anchor の有無と長さしか見ない。**
11. **担保の内容が変わっていない** — **形式のみの変更である** (設計 §8)。**監査照合**: 監査は SI / C 行の担保内容が変わっていないことを、移動前後の全文で突き合わせる。
12. **対応表に対応の無い行が無いこと** (メタ条件)。
13. **完了ゲート** — `failed` 0 / `skipped` 0 / `xfailed` は WP-6 完了時点から不変。`passed` は register テストの新設分だけ増える (増分内訳を報告する)。

#### 非 vacuity 要件

- **anchor 検査が「解決」を測っていることを示す** — **見出しの存在ではなく slug の一致**を測っていること。変異 1 で、**見出しは残したまま slug だけを変える** (タイトルを付ける等) 形でも赤になることを実測する。
- **セル長上限が「行ではなくセル」に掛かっていることを示す** — 変異 2 は **1 セルだけ**を上限超過にする。行全体の長さで判定する実装では、この変異が空振りする。

#### 確定文言のファイル所在

- **依頼者裁定 4 の逐語は設計 §5** にある。**更新規約の文言「訂正は現行行を書き換え、旧文は履歴へ移す」は裁定 4 の文言であり、設計 §5 から複製して言い換えない** (常設規律 4)。

#### 同型性テスト対象

**なし。**

#### 変異注入 (必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 companion の見出し形式 | **変異 1** |
| 2 履歴の逐語移動 | **監査照合** |
| 3 現行行の形と列構造 | **監査照合** (parser が壊れれば register テストが赤になる) |
| 4 更新規約の置き場 | **監査照合** |
| 5 anchor の解決検査 | **変異 1** |
| 6 全 ID の見出し | **変異 1** |
| 7 セル長上限 | **変異 2** |
| 8 ID 重複禁止 | **変異 3** |
| 9 `test_control_mapping_register.py` 新設 | **変異 1〜3 が当該ファイルに対しても効くこと** |
| 10 落ちた制約が無い | **監査照合** (レビューの独立項目) |
| 11 担保の内容不変 | **監査照合** |
| 12 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 13 完了ゲート | **監査照合** |

1. **anchor を 1 つ壊す** — companion から見出しを 1 つ落とす (または見出しにタイトルを付けて slug を変える) → **アンカーが解決せず赤**。**両 register テストで実測する。**
2. **上限を超えるセルを 1 つ作る** → **赤**。**セル単位であることを示すため、行全体ではなく 1 セルだけを超過させる。**
3. **同一 ID の行を 2 本置く** → **ID 重複 assert が赤** (現行 parser の silent overwrite を塞いだことの確認)。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py \
    conformance-tests/test_control_mapping_register.py
```

**完了ゲート (監督のみ、単独実行)**: `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、**「落ちた制約」を独立項目として突合する**)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **履歴を捨てない** (裁定 4)。**書き換えない** — 逐語で移す。
2. **履歴を同一ファイルの別セクションへ移さない** (設計 §4 の 9)。**総量が減らず、抽出コストの問題が解けない。**
3. **日付 / WP マーカーで自動仕分けしない** (設計 §4 の 11)。**C-19 が反例である。**
4. **担保の内容を変えない** — 形式のみである。**条件定義文を削って上限に収めない** (D-7)。**収まらないなら上限を上げる** (目安は下限の目安である)。
5. **1 ID を複数行に割らない** — parser が Status を最後の行だけで見る形に壊れる。
6. **`CONDITIONS.md` に 2 つ目の `|` 始まりの表を作らない** — parser の単一表前提を壊す。**更新規約は散文で書く。**
7. **companion の見出しに `### SI-XX — <タイトル>` 形 (`SECURITY_INVARIANTS_V1.md` の前例) を採らない** — slug が変わり、元ファイルから張ったリンクが解決しない (C-2)。

---

### WP-8 記録・引き継ぎ第 14 次

**着手条件: WP-4〜WP-7 の完了後。**

#### 目的

**WP-1〜WP-7 の実測を正本へ落とし、台帳と限界開示を現在形にし、引き継ぎ第 14 次を起こす。** **本 WP は製品コード・テストを変更しない。**

#### 前提として読む箇所 (設計)

**§10**、**§11 (L7-1〜L7-13)**、**§13**、**フェーズ6 設計 §11 (L6-19 / L6-20)**、**第13次引き継ぎ §4-2**。

#### 成果物

1. **設計 §13 実施記録** — **§13.1 集計行** (各 WP の実測値と出所)、**§13.2 WP ごとの記録** (コミット、受理境界、レビュー指摘の内訳、変異注入の結果)。**確定した実測事項をここに置く**: **(a)** D-6.2 の駆動レシピ・検査形の確定分類 (全 plug 実測)、**(b)** `operation_depth` の枝、**(c)** V3 の xfail 確定件数、**(d)** スキャナの現行ツリー全規則 0 件の出力と R2_fqdn の TLD 限定集合、**(e)** `CONDITIONS.md` / `CONTROL_MAPPING.md` のセル長上限の確定値、**(f)** `constraints.txt` の生成で手で除いた行の一覧。
2. **設計 §11 台帳の状態** — **L7-1〜L7-13 のそれぞれに状態を付す**。**新たに見えた項目は L7-14 以降として起票する。**
3. **フェーズ6 設計 §11 の状態更新** — **L6-20 の (a)(b)(g)(h)(i) を本フェーズの実施結果で閉じ、(c) は L7-2 として残っている旨を書く**。**L6-19 を「契約 `details_vocabulary` が既に `limit_class` を必須化しているので手当て候補 (i) は済んでいる」として閉じる** (実体の訂正は WP-4)。**L6-17 の閉止を記録する** (実体は WP-5)。
4. **第13次引き継ぎ §4-2 への閉止注記** — **原文を消さず、日付付きの注記を置く**。**L7-1 を第13次 §4-2 にも起票する** (裁定 3)。
5. **引き継ぎ第 14 次** — 現在地 (main のコミットと集計行)、到達した状態、クライアント連携状態 (**一報は送らない — 方針不変**)、次の一手 (優先順)、依頼者判断待ちと台帳 (**(α)(β)(γ) の確定内容と実施状況** — 依頼者裁定 2026-09-05 で 3 点とも確定済みである、**WP-9 の進捗**)、教訓の追加。
6. **§D-6.5「Q4 確定後の追補」の確定記録** — **追補の記入そのものは WP-4 の着手条件である**。本 WP は**確定記録**だけを持つ。

#### 完了条件 (検証可能な形)

**本 WP は変異を作らない。全行が監査照合である** (§0.1 の対応表の書き方)。

1. **設計 §13 が埋まっている** — **プレースホルダを 1 つも残さない**。**監査照合**: §13 の表 ↔ `git log` の merge コミット ↔ 各 WP 完了報告の集計行。
2. **確定した実測事項 6 種が §13 にある** — (a)〜(f)。**監査照合**: 各項 ↔ 当該 WP の完了報告 (語単位)。
3. **台帳 L7-1〜L7-13 に状態が付いている** — **監査照合**: 各項 ↔ 実施結果。**閉じていない項目を「閉じた」と書いていない**こと。
4. **フェーズ6 §11 の L6-20 / L6-19 / L6-17 が現在形である** — **監査照合**: 各項 ↔ 本フェーズの成果物。**(c) が L7-2 として残っていること**が書かれていること。
5. **第13次 §4-2 に日付付きの閉止注記があり、原文が消えていない** — **監査照合**: `git diff` で削除行が無いこと。
6. **L7-1 が 3 箇所に起票されている** — 本設計 §11、フェーズ6 設計 §11 L6-20 の末尾、第13次引き継ぎ §4-2 (裁定 3)。**監査照合**。
7. **引き継ぎ第 14 次がある** — **最終集計行の出所が明記されている**こと。**(α)(β)(γ) の確定内容 (2026-09-05 の依頼者裁定) とその実施状況、および WP-9 の進捗が書かれている**こと。**取りこぼしが 0 件である**こと。**監査照合**: 判断事項 ↔ 設計 §11 + §6 の残存項目。
8. **正直さの後退が無い** — **監査照合**: 「閉じた」主張 ↔ 実装コミット / 射程の開示 ↔ C-05 行・C-07 行・C-10 行の開示内容 / 範囲外項目 ↔ 本書と設計 §11。
9. **秘密の非混入** — **監査照合**: `git diff` の追加行 ↔ `docs/security/public-repository-policy.md` の禁止事項一覧。**あわせて `tools/public_value_scan.py` を走らせて全規則 0 件**であること。
10. **対応表に対応の無い行が無いこと** (メタ条件)。
11. **完了ゲート** — 文書のみであり、**集計行は WP-7 完了時点から 4 数すべて不変**であること。

#### 非 vacuity 要件

- **§13 に書く数値はすべて「監督が完了ゲートで単独実行して得た実測値」である** — 見積りを置かない。**出所 (ログファイル名またはコミット) を明記する。**
- **「閉じた」と書くすべての項目について、閉じた根拠 (コミット・テスト名・`file:line`) を並記する** (常設規律 3)。

#### 確定文言のファイル所在

- **依頼者裁定 1〜4 の逐語は設計 §5** にある。引き継ぎ・台帳に裁定を引く場合は**設計 §5 から複製し、言い換えない**。

#### 同型性テスト対象

**なし。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py \
    conformance-tests/test_control_mapping_register.py
./.venv/bin/python tools/public_value_scan.py
```

**完了ゲート (監督のみ、単独実行)**: `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`

#### 使用テンプレート

起草 = Opus (テンプレ 3 = 文書起草)。受け入れ監査 = Opus (テンプレ 6)。

#### 禁止事項

1. **製品コード・テストを変更しない。**
2. **(α)(β)(γ) の確定内容を言い換えない** — 逐語は設計 §6 が正本である (常設規律 4)。**確定していない事項 (L7-6 の残余、L7-1 等) を「確定した」と書かない。**
3. **閉じていない台帳項目を閉じたことにしない。**
4. **実値を書かない** — 引き継ぎは公開対象の文書である。

---

### WP-9 公開ゲート (独立の最終 WP)

**着手条件: WP-1・2・3・6 の完了 (= (g)(b) 完了) かつ依頼者の実行合図。** **§6 (γ) は 2026-09-05 の依頼者裁定で案 1 に確定した**ので着手条件には残らない — **手順 3 は「同名リポジトリの delete + 書換後履歴のみ push + 再作成」、手順 4 の clone 取得元は再作成後の remote である。**

#### 目的

**履歴の実値を消し、公開しても安全な状態にしてから visibility を切り替える。** **本 WP の実行の大半は運用者作業であり、監督が担うのは手順書・commit-map 適用スクリプト・履歴スキャン・文書 hash 更新の 4 つである。**

#### 前提として読む箇所 (設計)

**§3 D-1 (iv)** (8 項目と順序・残留への注意・却下した代替案)、**§9** (手順表と担当)、**§6 (γ)** (**確定済み**: 案 1)、**§11 L7-3 / L7-12 / L7-13**、**§12** (前倒し worktree の後始末)、**§5 裁定 2**。

#### 手順チェックリスト (§9 の 0〜7。担当を付す)

| # | 手順 | 担当 | 完了の印 |
|---|---|---|---|
| **0** | **着手合図の確認** — (g)(b) の完了と、依頼者の明示の実行合図 | **[依頼者]** | 合図が記録されている |
| **0.5** | **すべての linked worktree を畳む** (`git worktree remove` / `git worktree prune`)。**前倒しで作った 7-A の worktree もここで畳む** (§12)。**書換は remote から取り直した fresh clone 上で行う** — 既存作業ツリーで `--force` を使うと gc 前の object 残留を生む | **[運用者]** | `git worktree list` が共有ツリーのみ |
| **1** | **`git filter-repo --replace-text` による全履歴の置換**。**置換表はリポジトリ外の運用者記録にある既存の対応表を使う** (本書はその存在だけを書く)。**filter-repo は作業機に未インストールなので、まず導入する** | **[運用者]** (実行) / **[監督]** (手順書) | 書換が完了し、commit-map が出力される |
| **2** | **commit-map による文書内 hash 参照の一括更新** (`tools/rewrite_hash_refs.py`)。**書換後の新 commit として乗る**。対象規模は 29 ファイル・262 件の hex 様トークン (誤検出は精査で除く)。**commit-map はリポジトリ外の運用者記録に保存する** | **[監督]** | 未一致 0 件、非一意 0 件 (完了条件 1・2) |
| **3** | **同名リポジトリを delete し、書換後の履歴だけを push して再作成する** (**(γ) 案 1 で確定**、依頼者裁定 2026-09-05)。**全 branch・全 tag を push する。** **force push だけでは GitHub 側に旧 commit が unreachable object として残り得る**ので、**remote の object store 自体を新しくする**。これを行わない限り、履歴の実値が消えるのはローカルだけである | **[運用者]** | 再作成した remote の履歴が書換後の内容だけである |
| **4** | **remote から新規 clone を取り直し、スキャナの履歴モード (`--history`) を掛けて全規則 0 件**であること。**取得元は手順 3 で再作成した remote である** ((γ) 案 1)。**ローカルの書換済みツリーではなく、remote が実際に保持している履歴を検査する** | **[監督]** | 全規則 0 件 (完了条件 3) |
| **5** | **全 clone・worktree の作り直し** — 共有ツリー、`.claude/worktrees/*`、VPS 上の clone | **[運用者]** | 旧 clone が残っていない |
| **6** | **有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**。**rotate は id を保持するため不可である** (裁定 2)。**手順 5 の後に置くのは、手順 1〜4 が失敗して巻き戻す場合に credential を失わないためである** (L7-12) | **[運用者]** | 旧 id が失効し、新 id が発行されている |
| **6.5** | **R7 (個人名) の人手確認** — スキャナは個人名を一切検査しない (L7-3)。**「0 件だった」と「検査していない」は違う**。対象語はリポジトリ外の運用者記録にある | **[運用者]** (記録の確認は **[監督]**) | 人手確認の記録がある |
| **7** | **visibility の切替** — **手順 3・4 が (γ) 案 1 の形で完了していること** ((γ) は確定済み) | **[依頼者]** | — |

**順序は (0) → (0.5) → (1) → (2) → (3) → (4) → (5) → (6) → (6.5) → (7) である。** **手順 4 を手順 5 の前に置くのは、検査対象を「remote が実際に保持している履歴」にするためである。**

**記録する帰結**: 手順 1 の後、**リポジトリ外の記録 (運用者の私的記録、引き継ぎ以前のメモ) が引く旧 hash は無効になる**。

#### 成果物 (監督作業分)

1. **`tools/rewrite_hash_refs.py`** (新設) — filter-repo の commit-map を読み、**文書内の 7〜40 桁 hex 様トークンを一意前方一致で置換する**。**未一致は一覧に出す。非一意 (前方一致が 2 件以上) のトークンは置換せず一覧に出す。** **違反 1 件以上で非 0 終了する。**
2. **公開ゲートの手順書** — 上記チェックリストを運用者が単独で実行できる形に落としたもの。**置換表・commit-map の内容は書かない** (存在だけを書く)。

#### 完了条件 (監督作業分のみ。運用者・依頼者の手順はチェックリストで管理する)

1. **`tools/rewrite_hash_refs.py` が一意前方一致でのみ置換する** — **commit-map に前方一致が 2 件以上ある短縮 hash は置換せず、一覧に出して非 0 終了する**。変異 1。
2. **未更新の旧 hash が残っていれば照合が非 0 終了する** — 変異 2 (設計 D-1 (iv) の変異)。
3. **remote から取り直した新規 clone に対する `--history` スキャンが全規則 0 件である** — 変異 3。
4. **置換表と commit-map がリポジトリに入っていない** — **監査照合**: 監査は `git log --all --name-only` に当該ファイルが現れないこと、および `.gitignore` に頼っていない (そもそも作業ディレクトリ外にある) ことを確認する。**`.gitignore` は security boundary ではない** (CLAUDE.md)。
5. **手順 3・4 が (γ) 案 1 の形で実施されている** — **監査照合**: 監査は、**手順 3 が同名リポジトリの delete + 再作成 + push であったこと**と、**手順 4 の clone 取得元が再作成後の remote であったこと**を実施記録で確認する。**force push で済ませた記録があれば不合格である。**
6. **R7 の人手確認が記録されている** — **監査照合** (L7-3)。**「スキャナが 0 件」を人手確認の代わりにしていない**こと。
7. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 非 vacuity 要件

- **手順 4 のスキャンは「remote から取り直した clone」に対して行う** — ローカルの書換済みツリーに掛けても、公開されるのは remote 側の内容である。**どのクローンに掛けたかを報告に明記する。**
- **`rewrite_hash_refs.py` の一意性 assert が load-bearing であることを示す** — 変異 1 で、**非一意な短縮 hash を与えると置換されずに一覧へ出る**ことを実測する。**「たまたま全件一意だった」で済ませない。**

#### 確定文言のファイル所在

- **依頼者裁定 2 の逐語は設計 §5** にある。手順書に裁定を引く場合は**設計 §5 から複製し、言い換えない**。**とくに「rotate は id を保持するため不可」は裁定の文言である。**

#### 同型性テスト対象

**なし。**

#### 変異注入 (監督作業分。必須)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 |
|---|---|
| 1 一意前方一致 | **変異 1** |
| 2 未更新の旧 hash の検出 | **変異 2** |
| 3 履歴スキャン 0 件 | **変異 3** |
| 4 置換表・commit-map の非混入 | **監査照合** |
| 5 手順 3・4 が (γ) 案 1 の形 | **監査照合** |
| 6 R7 の人手確認 | **監査照合** |
| 7 対応表が全行埋まる | 本表そのもの (メタ条件) |

1. **非一意な短縮 hash** — commit-map に前方一致が 2 件以上ある短縮 hash を含む合成入力を与える → **置換されず、一覧に出て非 0 終了する**こと。
2. **未更新の旧 hash を 1 件残す** — 置換後の照合を走らせる → **非 0 終了する**こと。
3. **履歴スキャン** — 置換前の版を含む一時ブランチを走査させる → **非 0 終了する**こと (WP-1 の変異 5 と同じ機構であり、**対象が remote 由来の clone である点だけが違う**)。

#### テストコマンド

```
./.venv/bin/python tools/rewrite_hash_refs.py --check <commit-map>   # 未一致・非一意の一覧と終了コード
./.venv/bin/python tools/public_value_scan.py --history              # 新規 clone 上で。全規則 0 件
```

**本 WP は pytest の収集対象を変えない。** 完了ゲートの集計行は WP-8 完了時点から不変である。

#### 使用テンプレート

スクリプト実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5)。手順書起草 = Opus (テンプレ 3)。受け入れ監査 = Opus (テンプレ 6)。**運用者手順の実行は監督・運用者・依頼者が行い、subagent に委任しない。**

#### 禁止事項

1. **置換表・commit-map の内容をリポジトリ内の文書 (本書・設計・手順書・コミットメッセージ) に書かない** (裁定 2)。**存在だけを書く。**
2. **BFG Repo-Cleaner を使わない** (設計 §4 の 2) — hash 一括更新が filter-repo の commit-map 形式を前提にしている。
3. **実値を含む 6 commit だけを squash しない** (設計 §4 の 3) — 履歴の連続性と他文書の hash 参照をより多く壊す。
4. **既存作業ツリーで `git filter-repo --force` を使わない** — gc 前の object 残留を生む。**fresh clone 上で行う** (手順 0.5)。
5. **手順 3 を force push で済ませない** ((γ) 案 1 で確定。§0.2 の 6、L7-13) — **同名リポジトリを delete し、書換後の履歴だけを push して再作成する**。**手順 4 の clone 取得元も再作成後の remote である。** **「残留を許容して公開する」形式上の選択肢を監督が採らない。**
6. **credential を rotate で済ませない** — **id を保持するため不可**である (裁定 2)。**revoke + 再発行である。**
7. **手順 6 を手順 5 より前に置かない** — **credential の再発行は取り消せない唯一の手順である** (L7-12)。
8. **R7 (個人名) の人手確認を省かない** (L7-3)。

---

## 3. 完了ゲートの集計行の予告

**完了ゲートのコマンドは `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` の単独実行である** (§0 の 3)。**集計行は監督が自分で握る。**

| WP | `failed` | `skipped` | `xfailed` | `passed` |
|---|---|---|---|---|
| **WP-1** | 0 | **0** | **着手時点から不変** | **不変** (スキャナは suite に入れない) |
| **WP-2** | 0 | **0** | **不変** | **不変** (`filterwarnings` は有効化しない) |
| **WP-3** | 0 | **0** | **不変** | **不変** (配備資産は収集対象ではない) |
| **WP-4** | 0 | **0** | **7 または 9** (+ 着手時点の既存分) | `{実装者が報告し監督が記録}` |
| **WP-5** | 0 | **0** | **WP-4 完了時点から不変** | `{報告}` |
| **WP-6** | 0 | **0** | **WP-5 完了時点から不変** | **WP-5 完了時点から不変** |
| **WP-7** | 0 | **0** | **不変** | `{報告}` (register テストの新設分) |
| **WP-8** | 0 | **0** | **不変** | **不変** (文書のみ) |
| **WP-9** | 0 | **0** | **不変** | **不変** (収集対象を変えない) |

- **`skipped` は全 WP を通じて 0 である。** 非 enabled 側は skip せず、**宣言の正直さを assert する** (C-05 / C-07 の宣言分岐)。**skip が出ていたら環境の問題として解決してから完了と判定する。**
- **本フェーズが増やす `xfailed` は WP-4 の C-05 V3 だけである。** **7 または 9** — `MitateDB-api` (in-process) 4 または 5 本 + `MitateDB-api-http` 3 または 4 本。**件数は `operation_depth` の実測で決まる** (D-6.1 の二枝)。**WP-4 より前の WP は xfailed を 1 件も増やさない。**
- **撤去条件**: **L7-1 の実装が入ったコミットと同一コミットで、当該 class の分を撤去する。** `strict=True` なので、宣言が `unavailable` 以外へ上がれば XPASS → 赤になり、撤去を強制する。**class ごとに分かれているので 1 class ずつ閉じられる。**
- **本数は「テスト関数数」ではなく「収集された test id 数」で数える。** **`passed` 欄には見積りを置かない** — 実装者が増減内訳を報告し、監督が記録する。**`xfailed` の期待値だけは上表が正であり、想定と違う値なら完了と判定しない。**
- **基準値**: 7-A (WP-1〜WP-3) は**着手時点の main の集計行**である (フェーズ6 完了時点は **1800 passed / 0 failed / 0 skipped / 0 xfailed**。以後 docs のみの commit が乗っている)。**7-B (WP-4 以降) の基準値は Q4 マージ後の集計行であり、Q4 の完了報告が正本である。** **着手時に監督が実測して確定する。**

---

## 4. 訂正註 (2026-09-05 追記、7-A 実装中。2026-09-06 に 7-B 分を追記)

**訂正註は 6 件であり、いずれも実装物の欠陥ではなく、本書側の誤りか、本書の発注後に監督が下した裁定である** (フェーズ6 §11 **L6-18** の流儀 —「実装 / レビュー / 監査が実測で見つけた発注文書側の誤り。設計が正」)。**本文の発注内容は書き換えていない。** **版数行は v1.1 のまま据え置く** (監督裁定。7-A の実装中であり、7-A 完了時にまとめて版数を上げる)。

1. **WP-3 成果物 6 / 完了条件 9 — CI の deploy-assets lint job の中身の置き場所。**
   - **発注文書の記述**: 成果物 6 は「**`.github/workflows/ci.yml` の deploy-assets lint job の中身**」を WP-3 の成果物とし、`systemd-analyze verify` / `nginx -t` / `bash -n` を **WP-3 が workflow ファイルに直接書く**形で発注していた (WP-2 の完了条件 9 と禁止事項 5 が「枠だけを WP-2、中身は WP-3」と対になっていた)。
   - **実際**: **7-A 前倒し着手の確定により WP-1〜WP-3 を並列で走らせた**ため、**WP-3 の着手時点で `.github/workflows/ci.yml` (WP-2 の成果物 2) がまだ着地しておらず**、WP-3 が中身を書き込む先のファイルが存在しなかった。
   - **裁定**: **監督裁定により構成を変更する。** lint 本体を **`r2db-api/deploy/scripts/lint_deploy_assets.sh`** (**`--require-tools` モード付き**) に置き、**WP-2 の job はそれを呼ぶだけ**とする。**検査の実体と変異 1〜3 の宛先は当該 script** であり、workflow 側は呼び出しのみを持つ。**WP-2 = job の枠、WP-3 = 検査の中身という境界そのものは保たれている** — 変わったのは中身の置き場所だけである。並列化の帰結であり、実装物の欠陥ではない。

2. **WP-3 成果物 1 — control unit の `EnvironmentFile` を placeholder にするという指定。**
   - **発注文書の記述**: 「**unit 名・port・`EnvironmentFile` は placeholder** (`REPLACE_ME_CONTROL_PORT` 等)」。
   - **実際**: `EnvironmentFile` まで placeholder 化すると、**完了条件 1 の同型性照合と衝突する** — 既存 `r2dbsvc-api.service` は `EnvironmentFile` を literal パスで書いており、新設 unit だけを伏字にすると同型でなくなる。加えて **control 面の env ファイル名は既存 `deploy/env/control.env.example` が literal パスとして既に確立している** (当該ファイルは WP-3 の禁止事項 2 により触れない)。
   - **裁定**: **既存 unit との同型性を優先する。** `EnvironmentFile` は**既存 `control.env.example` が確立した literal パスのまま**置き、**placeholder 化の対象は unit 名と port の側に限る**。**完了条件 1 の「差分が限られる」の実測結果は Description / `EnvironmentFile` / `ExecStart` の 3 行のみ**である。

3. **WP-3 成果物 3 / 完了条件 6 — 新設 operator script の本数。**
   - **発注文書の記述**: 「`r2db-api/deploy/scripts/` に **operator script 3 本**」(part1 / part1b / part2)。完了条件 6 も「**operator script 3 本がある**」。
   - **実際**: **訂正註 1 の帰結として `lint_deploy_assets.sh` が同ディレクトリに加わり、新設は 4 本**である (part1 / part1b / part2 + `lint_deploy_assets.sh`)。
   - **裁定**: **4 本が正。** 完了条件 6 の `bash -n` は**新設 4 本すべて**に掛ける。

4. **WP-2 の CI トリガー — レビュー提案「`push` を main に限定し pull_request に任せる」の不採用。**
   - **発注文書の記述**: 本書は WP-2 の完了条件・禁止事項で**トリガーを規定していない** (実現手段は実装担当が選ぶ形になっていた)。これに対しレビューが、**`push` を main に限定し branch は `pull_request` に任せる** (同一 commit での二重起動を避ける) 形を提案した。
   - **実際**: 本リポジトリは**単独作業者であり PR 運用が無い**。また **CI の赤/緑の実測は監督が当該ブランチを push して行う** (WP-2 の非 vacuity 要件)。**`pull_request` を持たない構成では二重起動そのものが生じない。**
   - **裁定**: **監督裁定により提案は不採用。** トリガーは **`push` (全 branch) + `workflow_dispatch` のみ**とし、**`pull_request` は置かない**。

5. **WP-1 成果物一覧 — 一覧に無いファイルへの注記 1 語の追記。**
   - **発注文書の記述**: WP-1 の成果物は **6 点**であり、**`MitateDB-api/docs/cloud-run-cloud-sql.md` を含まない**。
   - **実際**: **R4 の synthetic 許可を「同一行 / 直前行の注記」の粒度に狭めた**帰結として (許可を文書単位・広域に取ると誤検出の抑止が効きすぎるため)、同文書の該当箇所が flag されるようになり、**`# synthetic` の注記 1 語**の追記が必要になった。
   - **裁定**: **監督採用。** 規則を狭めたことの帰結であり、**WP-1 の範囲内**として扱う。**追記は注記 1 語のみ**であり、当該文書の内容・記述には触れない。

6. **WP-3 の lint — check 4 (`ExecStart` 非空検査) と `--require-tools` は設計 D-5 に無い拡張である。**
   - **発注文書の記述**: 成果物 6 / 完了条件 9 が挙げる検査は **`systemd-analyze verify` / `nginx -t` / `bash -n` の 3 つ**であり、**設計 D-5 にも `ExecStart` の非空検査と、検査ツール不在時に失敗させるモードは無い**。
   - **実際**: **(i)** `ExecStart` を壊す**変異 1 を本機で赤にできない** — 当該検査は `systemd-analyze verify` に依存しており、本機ではそれが動かない。**(ii)** ツール不在を黙って通す形にすると、**CI 側でツールが欠けたときに lint が緑のまま通り得る** (非 vacuity 要件「lint が実際に落ちうることを 3 種すべてで示す」が空振りになる)。
   - **裁定**: **監督が事後承認。** **check 4 (`ExecStart` 非空検査)** と **`--require-tools`** は D-5 に無い拡張だが、**変異 1 の実測可能性と lint の非 vacuity を成立させるために必要**である。**設計 D-5 が挙げる 3 検査は撤去せず、その上に足す**形とする。
7. **WP-6 の着手条件「WP-5 の完了後」— 実装は branch で並行、main マージのみ WP-5 の後 (監督裁定 2026-09-06)。** 発注文書の記述 → 実装担当が字句どおり「WP-5 未完了のため着手不可」と差し戻した (正しい読み)。実際 → この条件の趣旨は §1 依存順の根拠に書いたとおり「`error::DeprecationWarning` を main に先に載せて他 WP の完了ゲートを塞がない」ことにあり、branch `phase7-wp6` 上の実装は誰のゲートも塞がない。裁定 → 実装は Q4 マージ後ただちに branch で行ってよい。**main へのマージは WP-5 のマージの後**に置き、完了条件 4 (4 数一致) は**マージ時点の main の集計行**に対して監督が評価する。実装報告では着手時点の main (`a6de3e3`) と有効化後の両 peer suite の集計行一致を示す。
8. **WP-6 の前提 3 点が現物と違う (実装担当の実測 2026-09-06、監督裁定)。** 発注文書の記述 → `TestClient(` は 3 ファイル 12 箇所 / root `pyproject.toml` の `filterwarnings` で全体に効く / httpx2 を入れれば警告は消える。実際 → (i) `TestClient(` は **4 ファイル 21 箇所** (`test_application_audit.py` 7 箇所と `test_surfaces_env.py` 6 呼び出しが漏れていた)、(ii) pytest は最寄りの inifile を採るため **peer 単体実行では root の `filterwarnings` は効かない** (`r2db-api/pyproject.toml` が configfile になる)、(iii) httpx2 (提供元確認: Starlette 1.6.0 の `testclient.py` 自身が `import httpx2` を第一経路にし、著者は httpx / Starlette の原作者) を入れても `starlette/testclient.py:53` の `anyio.abc.BlockingPortal` (anyio 4.15 で deprecated) が**上流由来の第 2 の DeprecationWarning** を出し、error 化すると 5 ファイルが収集エラーになる。裁定 → httpx2 を採用し TestClient は維持 (ASGITransport への置換は lifespan 駆動の有無が変わり空振りの危険がある — 実装担当の指摘 5)。`filterwarnings = ["error::DeprecationWarning", "ignore:.*BlockingPortal.*:DeprecationWarning:starlette.testclient"]` の形で **root と両 peer の pyproject に同じ設定を置く** (ignore は上流 1 件に限定し、台帳 L7-19 で追跡。Starlette が直せば撤去)。完了条件 4 の「12 箇所」は 21 に読み替える。 **追記 (レビュー指摘 1、同日)**: (iii) の「httpx2 を入れても第 2 の警告で落ちる」は正しいが、「httpx2 が無いと落ちる」は誤り — `StarletteDeprecationWarning` は `UserWarning` 派生で `error::DeprecationWarning` の対象外。httpx2 の役割は設計 D-4 の監督訂正のとおり (警告の除去と fallback 撤去への備え)。
9. **WP-5 の (d) L6-17 (r2db の `surfaces` 検証ヘルパの重複解消) は Q4 フェーズが先に閉じていた (実装担当の実測 2026-09-06、監督裁定)。** 発注文書の記述 → WP-5 で r2db `main.py` / `control_main.py` の重複コピーを 1 モジュールへ寄せ同型性対応表に行を足す。実際 → Q4 WP-1 が `platform_declarations.py::validate_surfaces_value` へ統合済み (Q4 設計 §12 LQ4-23)、同型性対応表にも既に行がある。裁定 → WP-5 の (d) はコード変更なし。PHASE6 設計 §11 L6-17 に日付付き閉止注記を追記するのみ (WP-5 の成果物 11〜13 と変異 9/10 は対象消滅として N/A)。**あわせて WP-5 に資源管理を追加** (監督裁定 2026-09-06): 共有 platform の `applications` 枠が既存テストの provision 累積で枯渇し (`LIMIT_EXCEEDED applications limit=115`)、新規テストファイルを 2 つ足すだけで C-15 の r2db 2 plug が赤になった。限度値を上げず、conformance の fixture 層でテストが provision した application を teardown で deprovision する (外部評価 指摘 1 の本体)。
10. **WP-5 の変異 4 (C-02 の拒否分岐を 1 つ外す → 赤) は r2db では成立しない (実装担当・監査の実測 2026-09-06、監督裁定)。** 発注文書の記述 → 拒否分岐 1 つの除去で赤。実際 → r2db の developer 検査は `service.py` と `structured.py` の二重ゲートで、片方だけ外しても緑 (defence in depth)。裁定 → 変異 4 は「両ゲートを同時に除去 → 赤」と読み替え、片方除去で緑であることは対照として記録する。あわせて C-00 の catalog vector の早期 return 2 経路は現在 4 plug すべてが `application_catalog: enabled` を宣言するため到達 0/4 であり (宣言の正直さ assert を置いたうえで CONDITIONS に開示)、その分岐の変異は赤の実証不能として受理境界に置く。C-14 の applications vector は隔離 surface (`isolated_control_surface(limits_override)`、port v1.11 追補 §21.4) + 既存登録数を差し引く headroom で駆動し、conformance の fixture 層に application 残骸の teardown deprovision を置いた (残数は有界: session 末 2〜3 件 = c06 のモジュールキャッシュ等)。

**実装担当が本書の誤りを見つけたら、本書の記述を独断で読み替えず監督へ差し戻し、監督が本節に訂正註を追加する** (フェーズ6 §11 L6-18 の流儀)。**本文の発注内容は書き換えず、誤りと判明した箇所に【訂正註 YYYY-MM-DD】を置き、本節に理由を書く** — 発注時の記述と実測の差を消さないためである。**訂正註を追加したときは本書の版数を上げる。**
