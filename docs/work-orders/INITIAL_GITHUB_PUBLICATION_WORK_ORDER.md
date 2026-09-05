# data-service-api 初回GitHub公開監査・初回公開 作業指示書

## 文書情報

- 版数: 1.1
- 発行日: 2026-08-27
- 発行者: 依頼者
- 改訂履歴:
  - 1.0 (2026-08-27) 初版
  - 1.1 (2026-08-27) Git実状との整合(監査開始時点でroot commit済みの状態を反映)、報告先・visibility未指定時の扱い・運用注意を追記

## 作業体制

- 実装・監査: Luna
- 独立レビュー: Terra
- 監督・最終判定: Sol

## 依頼者

依頼者

## 目的

`data-service-api` を初めてGitHubへ公開する。

この初回公開だけは通常のcommit/push作業として扱わず、**公開監査 → 必要修正 → 独立レビュー → 最終公開判定 → 初回push**を一つの独立作業として完了させる。

現在のローカルRepositoryは `git init` 済みであり、監査開始時点でroot commitが既に存在する。commit作成前に基本的な秘密情報パターンスキャンは実施済みだが、それは簡易確認であり、本作業指示書の公開監査を代替しない。GitHub remote設定と初回pushはまだ行っていない前提で開始すること。

公開後に秘密情報・本番データ・内部運用情報の混入が判明する事態を避けると同時に、Securityを理由としてRepositoryの有用な設計・仕様・Capability documentationを不必要に削除しないこと。

## 正本・対象

対象Repository:

```text
<repository-root>
```

以下を優先して読むこと。

```text
AGENTS.md
CLAUDE.md
SECURITY.md
docs/security/public-repository-policy.md
security/SECURITY_INVARIANTS_V1.md
security/THREAT_MODEL_V1.md
security/CONTROL_MAPPING.md
```

特に `docs/security/public-repository-policy.md` を初回公開Gateの正本とする。

初回公開監査はRepository全体を対象とする。`r2db-api`、`MitateDB-api`、`spec/`、`security/`、`conformance-tests/`、`docs/`、root filesを含む。

## 作業

### Luna — 公開監査と必要修正

現在のGit状態、tracked/untracked対象、ignore設定、Repository全体の内容を事実ベースで確認する。

最低限、以下を監査すること。

- Runtime / Developer / Admin API Key
- password、token、cookie、pepper、secret
- SSH/private key、service-account key、証明書private key
- PostgreSQL / Cloud SQL credential、credential-bearing URL
- production `.env`
- backup、database dump、production log
- 実Application/User data、個人情報
- 公開不要な運用情報の分類 -- 正本は `docs/security/public-repository-policy.md` の `Never publish` / placeholder convention 節である
- credentialやsecretの実値を含むexample、test fixture、documentation
- editor/OS/build/cache等の公開不要ファイル
- Git管理対象として不適切な生成物・一時物

Git履歴には既に初回commitが存在する。現在のworking tree・tracked対象だけでなく、既存の全commit(履歴内のblobを含む)を公開監査対象とすること。

秘密情報を単純な文字列検索だけで判定しないこと。設定ファイル、documentation、test fixture、URL、connection string、sample response等の意味も確認する。

問題を発見した場合は、初回公開に必要な修正を同じ作業内で行う。

修正では次を優先する。

- 実値を削除し、environment variable名・secret manager reference・synthetic fixtureへ置換
- 公開不要な生成物・local stateは `.gitignore` 等で除外
- Public Repository Security Gateを満たすために必要なdocument修正
- 誤って含まれた秘密情報が既存Git履歴に存在する場合は、公開前なので履歴を安全に作り直す

ただし、Security Invariants、Threat Model、API contract、architecture、Capability documentation等を「情報が詳しい」という理由だけで削除・抽象化しないこと。Securityはsource secrecyではなく、認証・認可・分離・least privilege等で成立させる。

### Terra — 独立レビュー

Lunaの監査結果・修正差分を独立して確認する。

少なくとも次を確認する。

- 公開禁止情報の見落としがないか
- `.gitignore` だけに依存した判断になっていないか
- tracked対象そのものが安全か
- 既存Git履歴がある場合に履歴まで確認されているか
- Securityを理由に必要な設計情報やCapabilityが不必要に削られていないか
- `docs/security/public-repository-policy.md` のGate条件を満たすか
- 初回公開後に通常の開発運用へ移行できるRepository状態になっているか

Critical / High の問題がある場合はPASSを出さないこと。

修正が必要な場合は、Lunaが同じ作業内で修正し、Terraが再確認する。

### Sol — 監督・最終公開判定

Lunaの監査・修正とTerraの独立レビューを確認し、初回公開の可否を最終判定する。

Solは実装方法を細かく指定する役ではなく、次を確認する。

- 公開監査が形式的チェックで終わっていないこと
- Public Repository Security Gateを満たすこと
- RepositoryのCapabilityや将来拡張性をSecurity名目で不必要に狭めていないこと
- 初回commit/pushを実施してよい根拠が揃っていること

Solが **PUBLICATION APPROVED** と判定するまでは、GitHubへのpushを行わないこと。

## 初回commit・GitHub公開

Solの **PUBLICATION APPROVED** 後にのみ実施する。

1. 初回公開対象を最終確認する。
2. 監査による修正がある場合はcommitする。既存履歴に公開不可情報が確認された場合に限り、公開前であることを条件として履歴を安全に作り直す。
3. GitHub上に `data-service-api` Repositoryを作成する。
4. GitHub側でREADME、`.gitignore`、License等による別系譜を作らない。
5. `origin` を設定する。
6. `main` を初回pushする。
7. GitHub上で公開された内容をread-backし、localの意図したcommitと一致することを確認する。

GitHub Repositoryのvisibilityは、依頼者の指定を優先すること。指定がない場合は勝手に決定せず、依頼者へ確認し、回答があるまでRepository作成以降の手順を停止すること。Publicを指定された場合は、`docs/security/public-repository-policy.md` のGate完了が前提となる。

GitHub認証方式、Repository owner、remote URL等の実環境依存値は現在状態から確認し、推測で設定しないこと。

## 運用上の注意

本Repositoryはファイル同期対象フォルダ配下にある。次を前提とする。

- push成功後は、GitHub remoteを履歴保全の正とする。ファイル同期を `.git` の保全手段として扱わない。
- 複数マシンから同一の同期フォルダ上でgit操作を同時に行わない。
- `.git` 破損時はremoteからの再cloneで復旧する(未pushの作業のみが失われる)。

## 変更しないこと

- `project/r2-vps/apps/r2db-api` を変更しない。
- 現在利用中の本番サービスを変更しない。
- 本番credentialをrotate/revokeしない。ただし、既存Git履歴に実secretが存在する事実が確認された場合は、公開作業を停止し、その事実を報告すること。
- Security Invariantsを「公開しやすくするため」に弱めない。
- APIやCapabilityを初回公開監査の都合で変更しない。
- GitHub公開のためだけに不要な大規模refactorを行わない。
- `git push --force`、履歴破壊、remote削除等を理由なく行わない。

## 完了条件

以下をすべて満たしたとき完了とする。

- LunaによるRepository全体の公開監査が完了している。
- 発見された公開上の問題が解消されている、または公開停止理由として明示されている。
- Terraの独立レビューでCritical 0 / High 0である。
- `docs/security/public-repository-policy.md` の公開Gateを満たしている。
- Solが `PUBLICATION APPROVED` を明示している。
- 公開対象のcommit履歴が監査済みであり、修正がある場合はcommitに反映されている。
- GitHub Repositoryが正しいowner/visibilityで作成されている。
- `origin` が正しく設定されている。
- `main` の初回pushが成功している。
- GitHub上のHEADとlocalの初回公開commitが一致している。
- 公開後のGit状態がclean、または残差がある場合は理由が明示されている。

## 完了報告

最終報告は依頼者へ提出する。Terraのレビュー結果とSolの判定は最終報告に含めて提出し、別経路での報告は要しない。

最終報告では最低限、次を簡潔に示すこと。

```text
Publication decision:
GitHub repository:
Visibility:
Initial commit:
Remote origin:
Luna audit:
Terra review:
Sol decision:
Critical / High findings:
Corrections made:
Git history audit:
Public repository policy gate:
Push result:
Post-push verification:
Remaining issues:
```

公開不可の場合はpushせず、blocking issueだけを重要度順に報告すること。
