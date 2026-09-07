# 公開ゲート手順書 (フェーズ7 WP-9、2026-09-06)

> **本書は公開リポジトリの文書である。**`docs/security/public-repository-policy.md`
> の Never publish / Placeholder convention と CLAUDE.md の Public Repository
> Security Gate に従い、**実値は 1 つも書かない** — 実ホスト名・cloud project
> 識別子・実 `credential_id`・IAM principal / e-mail・内部トポロジ・作業機の
> 絶対パス・運用者アカウント名は、すべて `<UPPER_SNAKE>` 形の placeholder で
> 書く。**置換表 (実値 ↔ placeholder の対応表) と filter-repo の commit-map は
> リポジトリ外の運用者記録にあり、本書はその存在だけを書く** (依頼者裁定 2)。
> **本書に現れる `R2DB_*` は環境変数の名前であって値ではない。**

本書は、設計 `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md`
**§9 の手順表 (0〜7)** と作業指示書 `WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md`
**§2 WP-9 のチェックリスト**を、**運用者が単独で実行できる形**に落としたもので
ある (WP-9 成果物 2)。

**正本は設計 §9 と作業指示書 §2 WP-9 である。**本書と正本が食い違って見えたら、
**正本が正しい**。本書は順序・コマンドの形・完了の印・失敗時の巻き戻しを足す
だけであり、**新しい判断を足さない**。

---

## 0. 前提と着手合図

### 0.1 着手合図

- **依頼者の実行合図: 2026-09-06 に受領した。**これが手順 0 (§9 の手順表の
  「着手合図の確認」) の充足である。
- **もう一方の着手条件 ((g)(b) の完了 = WP-1・2・3・6 の完了) は充足済みである。**
  **根拠は第 14 次引き継ぎ `docs/work-orders/HANDOVER_20260906_FABLE.md`** (§1 の
  現在地の表と §4-1) — フェーズ7 は WP-8 をもって 7-A / 7-B を閉じており、残って
  いるのは本 WP だけである。
- **§6 (γ) は 2026-09-05 の依頼者裁定で案 1 に確定している**ので、着手条件には
  残らない (**手順 3 = 同名リポジトリの delete + 再作成 + push、手順 4 の clone
  取得元 = 再作成後の remote**)。

### 0.2 依頼者裁定 2 (逐語。設計 §5 から複製した。言い換えない)

>   裁定 2 (g) 単一リポジトリを維持し、git filter-repo --replace-text で全履歴の実値を placeholder へ置換する (置換表は
>         リポジトリ外の運用者記録にある既存の対応表を使う。設計文書にはその存在だけを書き、内容は書かない)。
>         書換で変わる commit hash は設計文書・引き継ぎ・台帳が多数引用しているので、filter-repo の commit-map で
>         文書内の hash 参照を一括更新する手順を作業指示書の WP に含める。全 clone・worktree の作り直し、
>         有効 credential 2 件 (r2db control / runtime) の revoke + 再発行 (rotate は id を保持するため不可) を同じゲートに置く。

### 0.3 リポジトリ外の運用者記録 (存在だけを書く)

本手順は、**リポジトリの外にある運用者の私的記録**を 3 つ参照する。**内容は
本書にも他のリポジトリ内文書にも書かない** (裁定 2、作業指示書 §2 WP-9 の禁止
事項 1)。

| 記録 | 使う手順 | 本書での呼び方 |
|---|---|---|
| **置換表** (実値 → placeholder の既存の対応表。filter-repo の `--replace-text` 入力形式) | 手順 1 | `<REPLACEMENT_MAP_PATH>` |
| **commit-map** (手順 1 が出力する。手順 2 の入力。書換後にリポジトリ外へ保存する) | 手順 1・2 | `<COMMIT_MAP_PATH>` |
| **R7 (個人名) の対象語**と **commit identity** (author / committer に使う名前と e-mail) | 手順 2・6.5 | 本文で都度指す |

### 0.4 本書が使う placeholder

| placeholder | 指すもの |
|---|---|
| `<GITHUB_OWNER>` / `<REPO_NAME>` | GitHub の owner とリポジトリ名 |
| `<REMOTE_URL>` | 再作成後の remote の URL |
| `<FRESH_CLONE_PATH>` | 手順 1 のために remote から取り直す作業用 clone |
| `<VERIFY_CLONE_PATH>` | 手順 4 のために取り直す検査用 clone (手順 1 の clone とは別物) |
| `<SHARED_CHECKOUT_PATH>` | 既存の共有ツリー (作業機) |
| `<WORKTREE_PATH>` | `git worktree list` が挙げる linked worktree の 1 本 |
| `<SCRATCH_DIR>` | 作業機の一時ディレクトリ (リポジトリ外) |
| `<OPERATOR_RECORD_DIR>` | 運用者の私的記録の置き場 (リポジトリ外) |
| `<FILTER_REPO>` | `git-filter-repo` の実行形の絶対パス、または `git filter-repo` |
| `<COMMIT_IDENTITY_NAME>` / `<COMMIT_IDENTITY_EMAIL>` | commit identity (運用者記録) |
| `<CONTROL_CREDENTIAL_ID>` / `<RUNTIME_CREDENTIAL_ID>` | r2db の有効 credential 2 件の id |
| `<APP_SLUG>` | r2db の application slug |
| `<VPS_USER>` / `<VPS_HOST>` / `<VPS_CODE_DIR>` | 配備ホストの OS ユーザー / ホスト / コード配置先 |
| `<NAME>` | 手順 6.5 の対象語 (運用者記録) |

### 0.5 本書が commit hash を引かない理由

**手順 1 で全 commit hash が変わる**ので、本書に書いた hash は実行後に無効に
なる。**したがって本書は commit hash を 1 つも引かない。**着手時点と書換後の
HEAD は **§3 の実施記録に控える** (これは実行時に記入する記録であり、参照では
ない)。

**記録する帰結 (設計 §9)**: 手順 1 の後、**リポジトリ外の記録 (運用者の私的
記録、引き継ぎ以前のメモ) が引く旧 hash は無効になる。**

### 0.6 実行主体の凡例

**[監督]** = 秘密を扱わない検査・スクリプト適用。**[運用者]** = 作業機・配備
ホスト・GitHub アカウント・秘密を扱う操作。**[依頼者]** = 着手合図と visibility。

**手順の実行は監督・運用者・依頼者が行い、subagent に委任しない** (作業指示書
§2 WP-9)。

---

## 1. 事前準備 [監督] — 手順 0.5 に入る前に済ませておくもの

**この節は不可逆な操作を 1 つも含まない。**すべて手順 0.5 より前に、何度でも
やり直せる。

### 1.1 `git-filter-repo` の導入

**作業機には未インストールである** (設計 §9 の手順 1)。**導入方法は運用者の
判断で 2 つある。どちらでもよい。**

```sh
# (a) システムに入れない — scratch の venv へ入れる (本手順の推奨形)
python3 -m venv <SCRATCH_DIR>/filter-repo-venv
<SCRATCH_DIR>/filter-repo-venv/bin/pip install git-filter-repo
# 以後 <FILTER_REPO> = <SCRATCH_DIR>/filter-repo-venv/bin/git-filter-repo

# (b) システムに入れる — Homebrew (運用者判断)
brew install git-filter-repo
# 以後 <FILTER_REPO> = git filter-repo
```

**動作確認** (どちらの形でも):

```sh
<FILTER_REPO> --version
```

**(a) を採った場合、作業終了後は `<SCRATCH_DIR>/filter-repo-venv` を消せば
作業機に何も残らない。**

### 1.2 fresh clone の取得先

**書換は「remote から取り直した fresh clone」の上で行う** (作業指示書 §2 WP-9
の禁止事項 4 — 既存作業ツリーで `--force` を使うと gc 前の object 残留を生む)。

**リポジトリは private だが、`gh` CLI は認証済みなので clone できる。**

```sh
gh auth status                                   # 認証と scope を確認する
gh repo clone <GITHUB_OWNER>/<REPO_NAME> <FRESH_CLONE_PATH>
```

**`<FRESH_CLONE_PATH>` は共有ツリーの外に取る** — 共有ツリーの下に置くと、
手順 0.5 の worktree 畳みや手順 5 の作り直しと混ざる。

### 1.3 remote の branch / tag の一覧を控える (手順 3 の突合材料)

**手順 3 は「全 branch・全 tag を push する」ことが完了条件である。**押し漏れ
を検出できるように、**delete する前の remote の ref 一覧を控える。**

```sh
git ls-remote --heads --tags <REMOTE_URL> > <OPERATOR_RECORD_DIR>/refs-before.txt
wc -l < <OPERATOR_RECORD_DIR>/refs-before.txt
```

**この一覧は hash を含むので、リポジトリ外に置く** (手順 1 の後、hash 側は無効に
なるが、**ref 名の一覧としては有効なまま**である)。

### 1.4 ローカル限定 branch が無いことを確認する

**fresh clone には remote にある ref しか入らない。**共有ツリーに remote へ
push していないローカル branch があると、**手順 3 の再作成で失われる。**

```sh
git -C <SHARED_CHECKOUT_PATH> for-each-ref --format='%(refname:short) %(upstream)' refs/heads
```

**upstream 欄が空の branch が 1 本でもあれば、push するか、失われることを承知で
捨てるかを決めてから手順 0.5 に入る。**判断が要るなら監督に上げる。

### 1.5 hash 参照の規模を精査する

**対象規模は 29 ファイル・262 件の 7〜40 桁 hex 様トークン**である (設計 D-1
(iv) の 3。母数の 43 は `docs/` + `security/` 配下の `.md` と
`conformance-tests/CONDITIONS.md` の合計本数。**誤検出は精査で除く**)。

**手順 2 の適用スクリプトの `--check` で、着手時点の実数を出す** (この時点では
まだ commit-map が無いので、**規模の把握と誤検出の精査が目的**である):

```sh
python3 tools/rewrite_hash_refs.py <COMMIT_MAP_PATH> --check
```

**`tools/rewrite_hash_refs.py` は `tools/public_value_scan.py` と同じく標準
ライブラリだけで動くので、fresh clone に venv を作る必要は無い** (`python3` で
直接実行する)。**共有ツリーで先に試す場合は `./.venv/bin/python` でもよい** —
どちらで走らせても結果は同じである。

**非一意 (commit-map に前方一致が 2 件以上) のトークンは置換されず一覧に出て、
スクリプトは非 0 終了する** (WP-9 完了条件 1)。**この一覧が出たら、手順 2 を
進める前に監督が精査する。**

### 1.6 worktree 一覧の取得

```sh
git -C <SHARED_CHECKOUT_PATH> worktree list
```

**この出力が手順 0.5 の網羅リストである。**設計 §11 L7-13 は 2026-09-06 時点で
7 本と記録しているが、**その列挙は記録であって実行時の網羅リストではない** —
**Q4 セッションが作った worktree も、subagent が作った一時 worktree も、
`.claude/worktrees/*` はすべて共有ツリーの `.git/objects` を参照するので対象で
ある。実数は必ず実行時の `git worktree list` で確認する。**

---

## 2. 手順 0.5 〜 7

**順序は (0) → (0.5) → (1) → (2) → (3) → (4) → (5) → (6) → (6.5) → (7) で
ある。**この順序を入れ替えない — とくに:

- **手順 4 を手順 5 の前に置く**のは、検査対象を「remote が実際に保持している
  履歴」にするためである (設計 §9)。
- **手順 6 を手順 5 の後に置く**のは、手順 1〜4 が失敗して巻き戻す場合に
  credential を失わないためである (台帳 L7-12)。**credential の再発行は取り消せ
  ない唯一の手順である。**

### 手順 0.5 すべての linked worktree を畳む

- **実行主体**: **[運用者]**
- **不可逆性**: 可逆 (worktree は作り直せる。手順 5 でどのみち作り直す)

**コマンドの形**:

```sh
# 1) 網羅リストを取る (§1.6)
git -C <SHARED_CHECKOUT_PATH> worktree list

# 2) 各 worktree に未コミットの変更・未マージの branch が無いことを確認する
git -C <WORKTREE_PATH> status --short
git -C <WORKTREE_PATH> log --oneline main..HEAD

# 3) 1 本ずつ畳む (未コミットの変更があると remove は拒否される。
#    --force を付ける前に必ず中身を確認する)
git -C <SHARED_CHECKOUT_PATH> worktree remove <WORKTREE_PATH>

# 4) 登録の掃除
git -C <SHARED_CHECKOUT_PATH> worktree prune
```

- **完了の印**: `git -C <SHARED_CHECKOUT_PATH> worktree list` の出力が**共有
  ツリーの 1 行だけ**になる。
- **失敗時の巻き戻し**: 不要。畳めない worktree があれば、その中身を退避してから
  畳む。**畳めないまま手順 1 に進まない。**

### 手順 1 `git filter-repo --replace-text` による全履歴の置換

- **実行主体**: **[運用者]** (実行) / **[監督]** (手順書)
- **不可逆性**: **remote に対しては可逆** (この手順は fresh clone のローカル
  だけを書き換える。remote は無傷である)

**コマンドの形**:

```sh
# 1) fresh clone を取る (§1.2。既に取ってあるなら、取り直す方が安全である)
rm -rf <FRESH_CLONE_PATH>
gh repo clone <GITHUB_OWNER>/<REPO_NAME> <FRESH_CLONE_PATH>

# 2) 置換を掛ける。fresh clone なので --force は不要である
<FILTER_REPO> --replace-text <REPLACEMENT_MAP_PATH>
#    ↑ <FRESH_CLONE_PATH> をカレントにして実行する
#      (git filter-repo は clone の外から --source/--target で回さない)

# 3) commit-map をリポジトリ外へ保存する (内容は文書に書かない)
cp <FRESH_CLONE_PATH>/.git/filter-repo/commit-map <COMMIT_MAP_PATH>

# 4) ref の生存確認 — filter-repo は origin remote を外す。
#    branch / tag が local ref として揃っていることを §1.3 の一覧と突き合わせる
git -C <FRESH_CLONE_PATH> branch -a
git -C <FRESH_CLONE_PATH> tag
git -C <FRESH_CLONE_PATH> remote -v          # origin が消えていることの確認

# 5) 補助の先行検査 — 置換の取りこぼしをこの時点で捕まえる
python3 <FRESH_CLONE_PATH>/tools/public_value_scan.py --history
```

- **完了の印**:
  1. filter-repo が 0 で終わり、**`.git/filter-repo/commit-map` が出力されている**
     (行数 > 0)。
  2. **§1.3 で控えた ref 名がすべて local ref として存在する。**
  3. **(5) の補助検査が全規則 0 件である。**
- **(5) が 0 件でなかったら、手順 3 へ進まない。**置換表が実際の履歴を覆えて
  いないということなので、**fresh clone を捨てて監督に上げる** (置換表の更新は
  運用者記録側の作業であり、本手順書は対処を決めない)。
- **失敗時の巻き戻し**: **`rm -rf <FRESH_CLONE_PATH>` で丸ごと捨て、`gh repo
  clone` から取り直す。remote は 1 バイトも変わっていない。**

**注記**: この手順の後、**リポジトリ外の記録が引く旧 hash は無効になる** (設計
§9)。**`<COMMIT_MAP_PATH>` は旧 hash → 新 hash の対応そのもの**なので、手順 2
の後も**捨てずに運用者記録として保存し続ける**。

### 手順 2 commit-map による文書内 hash 参照の一括更新

- **実行主体**: **[監督]**
- **不可逆性**: 可逆 (fresh clone 上の新しい commit を 1 本足すだけである)

**コマンドの形** (すべて `<FRESH_CLONE_PATH>` をカレントにして実行する):

```sh
# 0) commit identity を fresh clone に設定する。
#    値は運用者記録の commit identity に従う (本書には書かない)
git config user.name  <COMMIT_IDENTITY_NAME>
git config user.email <COMMIT_IDENTITY_EMAIL>

# 1) 未一致・非一意の一覧を見る (置換はしない)
python3 tools/rewrite_hash_refs.py <COMMIT_MAP_PATH> --check

# 2) 適用する
python3 tools/rewrite_hash_refs.py <COMMIT_MAP_PATH> --apply

# 3) 照合する (未更新の旧 hash が 1 件でも残っていれば非 0 終了する)
python3 tools/rewrite_hash_refs.py <COMMIT_MAP_PATH> --verify

# 4) 差分を目で見てから、書換後の新 commit として乗せる
git diff --stat
git add -A
git commit -m "Publication gate: rewrite in-repository commit-hash references after history rewrite"
```

- **完了の印**: **(3) の `--verify` が 0 で終わる** — **未一致 0 件、非一意 0 件**
  (WP-9 完了条件 1・2)。**(1) の `--check` で非一意のトークンが挙がっていたら、
  監督の精査が済むまで (2) へ進まない。**
- **対象 branch**: **`main` の作業ツリーに 1 commit として乗せる。**完了条件
  1・2 の判定も `main` のツリーで行う。**他 branch にも同じ文書の旧版があるが、
  正本は `main` である** — 他 branch の扱いが要ると判明したら**監督に上げる**
  (本手順書は決めない)。
- **失敗時の巻き戻し**: `git reset --hard <直前の commit>` で commit を外す。
  それでも直らなければ**手順 1 の巻き戻し** (fresh clone を捨てて取り直し、
  filter-repo から再実行する) に落とす。**remote はまだ無傷である。**

### 手順 3 同名リポジトリを delete し、書換後の履歴だけを push して再作成する

- **実行主体**: **[運用者]**
- **不可逆性**: **ここから先は不可逆である。** **旧履歴は作業機の clone にしか
  残らない** (§4 を読むこと)。**手順 2 までの完了の印がすべて揃うまで、この手順
  に入らない。**

**なぜ force push で済ませないか** (依頼者裁定 2026-09-05、§6 (γ) 案 1):
**force push では GitHub 側に旧 commit が unreachable object として残り得る**
(SHA を直接指定すれば取得できる)。**remote の object store 自体を新しくする**
ために delete + 再作成する。**force push で済ませた記録があれば、WP-9 は不合格
である** (完了条件 5)。

**コマンドの形**:

```sh
# 0) 直前の最終確認 — 手順 1 の (5) と手順 2 の (3) が緑であることを確かめ直す
python3 <FRESH_CLONE_PATH>/tools/public_value_scan.py --history
python3 <FRESH_CLONE_PATH>/tools/rewrite_hash_refs.py <COMMIT_MAP_PATH> --verify

# 1) delete に要る scope を取る (gh のデフォルト scope には delete_repo が無い)
gh auth refresh -h github.com -s delete_repo

# 2) delete する。gh はリポジトリ名の再入力を求める確認付きである
gh repo delete <GITHUB_OWNER>/<REPO_NAME>

# 3) 同名で作り直す。private のまま作る (visibility 切替は手順 7、依頼者)
gh repo create <GITHUB_OWNER>/<REPO_NAME> --private

# 4) remote を張り直して (filter-repo が origin を外している)、全 branch・全 tag を push する
git -C <FRESH_CLONE_PATH> remote add origin <REMOTE_URL>
git -C <FRESH_CLONE_PATH> push --all origin
git -C <FRESH_CLONE_PATH> push --tags origin

# 5) 突合 — §1.3 で控えた ref 名がすべて新 remote にあることを確かめる
git ls-remote --heads --tags <REMOTE_URL>
```

- **完了の印**:
  1. **再作成した remote の履歴が書換後の内容だけである。**
  2. **(5) の ref 名の集合が §1.3 の `refs-before.txt` の ref 名の集合と一致する**
     (hash は当然違う。**比べるのは名前である**)。
  3. **default branch が `main` になっている** (`gh repo view
     <GITHUB_OWNER>/<REPO_NAME> --json defaultBranchRef` で確認する。違えば
     `gh repo edit <GITHUB_OWNER>/<REPO_NAME> --default-branch main`)。
- **失敗時の巻き戻し**: **再作成前の状態には戻せない** (§4)。push に失敗した
  場合は、**作業機の `<FRESH_CLONE_PATH>` が唯一の完全な履歴である**ので、
  **`<FRESH_CLONE_PATH>` を消さずに** push をやり直す。**この時点で
  `<FRESH_CLONE_PATH>` を消してはならない** — 消してよいのは手順 4 が緑になった
  後である。

### 手順 4 再作成後の remote から新規 clone を取り、履歴スキャンを掛ける

- **実行主体**: **[監督]**
- **不可逆性**: 可逆 (読むだけである)

**取得元は手順 3 で再作成した remote である** (§6 (γ) 案 1)。**ローカルの書換済み
ツリー (`<FRESH_CLONE_PATH>`) に掛けても意味が無い** — **公開されるのは remote
側の内容である。**

**コマンドの形**:

```sh
rm -rf <VERIFY_CLONE_PATH>
gh repo clone <GITHUB_OWNER>/<REPO_NAME> <VERIFY_CLONE_PATH>
python3 <VERIFY_CLONE_PATH>/tools/public_value_scan.py --history
```

- **完了の印**: **全規則 0 件** (WP-9 完了条件 3)。出力末尾の
  `total_flagged=0` を実施記録に写す。**どのクローンに掛けたかを報告に明記する**
  (WP-9 の非 vacuity 要件) — **`<VERIFY_CLONE_PATH>`、取得元は再作成後の remote**
  である。
- **R7 は 0 件に含まれない。**スキャナは**出力末尾で「R7 (個人名) は検査して
  いない」ことを毎回明示する** — **「0 件だった」と「検査していない」は違う**
  (台帳 L7-3)。R7 は**手順 6.5** で人手確認する。
- **失敗時の巻き戻し**: **0 件でなかったら、手順 5 以降に進まない。**残っている
  実値は remote に載っているので、**置換表を直したうえで手順 1 からやり直す**
  (fresh clone → filter-repo → hash 更新 → **delete + 再作成 + push** →
  再検査)。**この再実行は remote の delete + 再作成をもう一度行うということで
  ある。**手順 6 (credential) にはまだ入っていないので、**credential は失われない**
  (これが L7-12 の順序の目的である)。

### 手順 5 全 clone・worktree の作り直し

- **実行主体**: **[運用者]**
- **不可逆性**: 可逆 (作り直すだけである)

**対象は、書換前の履歴を指しているすべての作業コピーである** — 共有ツリー、
`.claude/worktrees/*`、配備ホスト上のコード。

**コマンドの形**:

```sh
# 1) 共有ツリー — 旧履歴を持つので、退避してから取り直す
mv <SHARED_CHECKOUT_PATH> <SCRATCH_DIR>/shared-checkout-prerewrite
gh repo clone <GITHUB_OWNER>/<REPO_NAME> <SHARED_CHECKOUT_PATH>

# 2) linked worktree — 手順 0.5 で畳んであるので、必要になった時点で
#    新しい共有ツリーから作り直す
git -C <SHARED_CHECKOUT_PATH> worktree add <WORKTREE_PATH> <BRANCH>

# 3) 配備ホスト — 現況を確かめる。
#    ここは git clone ではなく `git archive` の展開である可能性がある
ssh <VPS_USER>@<VPS_HOST> 'ls -d <VPS_CODE_DIR>/.git 2>/dev/null || echo "no .git"'

# 3a) .git がある (clone である) 場合: 旧履歴を持つので作り直す
# 3b) .git が無い (archive の展開である) 場合: 履歴は持たないが、
#     書換前の内容を持つ。既存手順どおり `git archive` で配り直す
git -C <SHARED_CHECKOUT_PATH> archive main | ssh <VPS_USER>@<VPS_HOST> \
  'rm -rf <VPS_CODE_DIR> && mkdir -p <VPS_CODE_DIR> && tar -x -C <VPS_CODE_DIR>'
```

- **完了の印**: **旧 clone が残っていない** — 作業機・配備ホストのどちらにも、
  書換前の履歴を持つ作業コピーが無い。**`<SCRATCH_DIR>/shared-checkout-prerewrite`
  と `<FRESH_CLONE_PATH>` は意図的に残す退避物である** (§4 を読むこと)。**残す
  なら残すと実施記録に書き、置き場を運用者記録に控える。**
- **注意**: **新しい共有ツリーの commit identity を設定し直す** (`git config
  user.name` / `user.email`。値は運用者記録)。
- **失敗時の巻き戻し**: 退避した `<SCRATCH_DIR>/shared-checkout-prerewrite` を
  戻せば作業は続けられるが、**それは旧履歴を持つツリーである** — 恒久的に戻す
  対象ではない。**戻したなら、公開前にもう一度この手順を実行する。**

### 手順 6 有効 credential 2 件 (r2db control / runtime) の revoke + 再発行

- **実行主体**: **[運用者]**
- **不可逆性**: **取り消せない** (台帳 L7-12)。**この手順に入ってよいのは、
  手順 4 が緑で、手順 5 が済んでからである。**

**`rotate` は id を保持するため不可である** (裁定 2、§0.2 の逐語)。**revoke +
再発行である** — **`rotate-credential` / `rotate-control-credential` は
`credential_id` を保持するので、公開時に id を変えるという目的 (SI-10、設計
D-1 (iv) の SI への影響) を満たさない。**

**コマンドの形** (`python -m r2db_api.ops`。CLI の正本は
`r2db-api/src/r2db_api/ops.py`、運用手順の正本は
`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §12a / §13):

```sh
# 0) 現況の確認 — 有効な credential の id を控える
R2DB_CONTROL_DSN=... python -m r2db_api.ops list-credentials
R2DB_CONTROL_DSN=... python -m r2db_api.ops list-apps

# 1) runtime (application) credential — revoke してから新規発行する。
#    新しい行になるので credential_id が変わる。secret は 1 回だけ表示される
R2DB_CONTROL_DSN=... R2DB_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops revoke-credential <RUNTIME_CREDENTIAL_ID>
R2DB_CONTROL_DSN=... R2DB_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops issue-credential <APP_SLUG> runtime

# 2) control credential — `reset` が「既存の control credential を全部 revoke
#    して 1 本だけ新規発行する」を atomically に行う正規の経路である。
#    --confirm を付けないと宣言を stderr に出して 2 で終わり、DB は触らない
R2DB_CONTROL_DSN=... R2DB_CONTROL_CREDENTIAL_PEPPER=... \
  python -m r2db_api.ops reset --confirm RESET_CONTROL_CREDENTIALS

# 3) 確認 — 旧 id が revoked、新 id が有効であること
R2DB_CONTROL_DSN=... python -m r2db_api.ops list-credentials
```

- **秘密値の扱い**: **`R2DB_CONTROL_DSN` / `R2DB_CREDENTIAL_PEPPER` /
  `R2DB_CONTROL_CREDENTIAL_PEPPER` の値と、印字された `secret:` は、本書にも
  実施記録にも書かない。**配置先は `/etc/r2dbsvc/*.env` (root:root 0600) だけで
  ある。**印字される `secret:` は locator 形の完全な bearer であり、丸ごと写す**
  (分割しない。既知の `credential_id` と古い secret から組み立て直さない —
  runbook §12a)。
- **完了の印**: **旧 id 2 件が失効し、新 id 2 件が発行されている** (`(3)` の
  一覧で確認する)。**新 id は実施記録に書かない** — 実 `credential_id` は
  Never publish の対象である (policy)。**発行された事実だけを記録する。**
- **配布**: 新しい bearer を保持者へ配る。**再発行までの間、既存 credential は
  認証を通らない** (第 14 次引き継ぎ §3)。**Stage 1 に production traffic は
  無い**ので調整窓は要らないが、**本番トラフィックが載っている配備では、これは
  breaking な credential rollover である** (runbook §12a)。
- **失敗時の巻き戻し**: **無い。**revoke した credential は戻せない。**発行を
  やり直す** (もう一度 `issue-credential` / `reset` を実行する) 以外の回復手段は
  無い。**lockout に陥った場合の回復経路は runbook §13 である。**

### 手順 6.5 R7 (個人名) の人手確認

- **実行主体**: **[運用者]** (**記録の確認は [監督]**)
- **不可逆性**: 可逆 (読むだけである)

**スキャナは個人名を一切検査しない** — 正規表現で表現できないためであり、
**出力末尾で毎回そう明示する** (台帳 L7-3)。**「スキャナが 0 件」を人手確認の
代わりにしない** (WP-9 完了条件 6)。

**対象語はリポジトリ外の運用者記録にある。本書には書かない。**

**コマンドの形** (**手順 4 で取った `<VERIFY_CLONE_PATH>` に対して行う** —
検査対象は再作成後の remote が保持している履歴である):

```sh
cd <VERIFY_CLONE_PATH>
git log --all -p | grep -i -n <NAME>          # 対象語ごとに 1 回。ヒット 0 が合格
git log --all -p | grep -i -n <NAME> | wc -l  # 件数だけを実施記録に書く
```

- **完了の印**: **対象語ごとにヒット 0 件であること**と、**「どの語を、いつ、
  誰が確認したか」が実施記録に残っていること。**対象語そのものは実施記録にも
  書かず、**運用者記録の何番目の語かで指す。**
- **注記**: `git log --all -p` の出力には **commit の author / committer 行も
  含まれる。**手順 1 の `--replace-text` は **blob の内容と commit message を
  置換するものであり、author / committer の識別情報は変えない。**author 行に
  ヒットが出た場合は、**手順 7 に進まず監督に上げる** — **本手順書は対処を
  決めない。**
- **失敗時の巻き戻し**: **ヒットがあれば手順 7 に進まない。**対処 (置換表への
  追加や mailmap の要否) は監督の判断であり、**決まったら手順 1 からやり直す。**

### 手順 7 visibility の切替

- **実行主体**: **[依頼者]** — **visibility の切替は依頼者本人が行う**
  (policy の First-public-push gate 16)。
- **不可逆性**: **実質不可逆** (public にした瞬間から、誰が取得したかを制御でき
  ない)。

**前提**: **手順 3・4 が (γ) 案 1 の形で完了していること** (delete + 再作成 +
push であり、手順 4 の clone 取得元が再作成後の remote であること)、**手順 6 の
revoke + 再発行が済んでいること**、**手順 6.5 の人手確認の記録があること。**
**§3 の実施記録が手順 0.5〜6.5 まで埋まっていることが、切替の前提である。**

```sh
gh repo edit <GITHUB_OWNER>/<REPO_NAME> --visibility public
gh repo view <GITHUB_OWNER>/<REPO_NAME> --json visibility
```

- **完了の印**: `visibility` が `PUBLIC` である。
- **失敗時の巻き戻し**: `gh repo edit <GITHUB_OWNER>/<REPO_NAME> --visibility
  private` で private へ戻せるが、**戻しても、public だった間に取得された内容は
  回収できない。**

---

## 3. 実施記録 (実行時に記入する)

**実値を書かない。**新 `credential_id`・対象語・秘密値・実ホスト名は書かず、
**「実施した」という事実と、機械が出した数だけを書く。**

### 3.1 着手時点の記録

| 項目 | 値 |
|---|---|
| 実行合図の受領 | 2026-09-06 (依頼者) |
| (g)(b) 完了の根拠 | `docs/work-orders/HANDOVER_20260906_FABLE.md` §1 / §4-1 |
| 書換前の `main` の HEAD | |
| 書換前の履歴スキャン (`--history`) の `commits_scanned` / `total_flagged` | |
| §1.3 で控えた remote の ref 数 | |
| §1.5 の `--check` の未一致 / 非一意の件数 | |

### 3.2 手順ごとの実施記録

| 手順 | 実施者 | 日時 (JST) | 結果 | 備考 |
|---|---|---|---|---|
| 0 着手合図の確認 | 依頼者 | 2026-09-06 (「WP-9 に着手してください」) / 2026-09-08 (「作業中のものはない」) | 合図あり | 全 remote branch が main にマージ済み、main (書換後 `39e1a81`) の CI 緑を確認 (旧 hash は本書に残さない — 手順 2 の規律) |
| 0.5 worktree 畳み | 監督 | 2026-09-08 | 書換は fresh clone 上 (共有 objects を参照しない) | 畳んだ本数 = 0 (手順 5 で全 worktree を作り直すため、この時点では畳まない。全 worktree はクリーン、共有ツリーの未追跡は Drive の `.gdoc` 1 件のみ) |
| 1 filter-repo | 監督 | 2026-09-08 | 成功 (`git filter-repo --replace-text` 23 規則 + `--mailmap` 1 行、リポジトリ外) | commit-map の行数 = 423 (422 commit) / 補助検査 `total_flagged` = 0 (481 commit、書換前 662) / identity は r2fish noreply 1 種 |
| 2 hash 参照の一括更新 | 監督 | 2026-09-08 | 成功 (`tools/rewrite_hash_refs.py --check / --apply / --verify`、44 ファイル 718 件) | `--verify` の未一致 = 0 / 非一意 = 0 (allowed 19 = UUID 断片・sha256 digest・合成 id) |
| 3 delete + 再作成 + push | 依頼者 (delete + 再作成、r2fish、Web UI、sudo mode 経由) / 監督 (push) | 2026-09-08 | 成功: 同名リポジトリを delete → private・初期化なしで再作成 (`isEmpty=true` を確認) → gate clone から `git push --all` (28 branch、tag 0) | ref 名の集合が一致 (はい) — 削除前の 28 ref と一致、default branch = main |
| 4 再作成後の remote からの履歴スキャン | 監督 | 2026-09-08 | 成功 | 掛けたクローン = 再作成後の remote からの新規 clone (`gh repo clone`、HEAD `a15f03a`) / `total_flagged` = 0 (482 commit、ツリー 0、identity 1 種、`rewrite_hash_refs.py --verify` 残存 0) |
| 5 clone・worktree の作り直し | 監督 (作業機) / 運用者 (VPS) | 2026-09-08 (作業機) | 作業機: linked worktree 17 本を `git worktree remove --force` + `prune` で除去、共有 checkout を再作成後の `origin/main` に `reset --hard`、旧 local branch を削除して 27 本を再追跡、`reflog expire` + `gc --prune=now` で旧 object を除去 (旧 hash は到達不能・object 不在を確認、ローカル履歴走査 0 件)。scratch の書換前後 clone・置換規則・mailmap は削除、commit-map と ref 一覧は運用者記録へ保存 | 作り直した対象 = 共有 checkout 1 + worktree 17 (VPS 側は `git archive` 配布のため `.git` 無し — 次回配布時に新履歴から取り直す) |
| 6 credential の revoke + 再発行 | 運用者 (VPS、`python -m r2db_api.ops` を `r2dbsvc_control` ロールの DSN で。unix socket は peer 認証のため loopback TCP を使用) | 2026-09-08 | 成功: runtime credential (application 1 件) を `revoke-credential` → `issue-credential … runtime` で再発行 (旧 id は revoked、新 id が有効であることを `list-credentials` で確認)、control credential を `reset --confirm RESET_CONTROL_CREDENTIALS` で全件 revoke + 1 本再発行 | 2 件とも revoke + 再発行 (rotate ではない)。新 id・secret は本書に書かない (policy)。新 bearer の配布先 = runtime: application 側 / control: 運用者記録 |
| 6.5 R7 の人手確認 | | | | 確認した語数 = / ヒット総数 = |
| 7 visibility の切替 | | | | |

### 3.3 書換後の記録

| 項目 | 値 |
|---|---|
| 書換後の `main` の HEAD | |
| `<COMMIT_MAP_PATH>` を運用者記録へ保存した (はい / いいえ) | |
| 退避した書換前ツリーの有無と置き場 (置き場は運用者記録に控える) | |
| 手順 4 のスキャン結果 (**全規則 0 件**であること) | |

---

## 4. 巻き戻し

### 4.1 手順 3 より前 — 捨てるだけで戻る

**手順 0.5・1・2 は remote を 1 バイトも変えない。**

- **`rm -rf <FRESH_CLONE_PATH>` で fresh clone を丸ごと捨て、`gh repo clone` から
  取り直せば、着手前と同じ状態に戻る。**
- **畳んだ worktree は、共有ツリーから `git worktree add` で作り直せる。**
- **失われるのは、fresh clone 上で行った作業だけである** (filter-repo の書換と
  手順 2 の commit)。

### 4.2 手順 3 より後 — 再作成前の状態には戻せない

**手順 3 で GitHub 上のリポジトリを delete した時点で、remote の旧 object store
は失われる。**

- **旧履歴は作業機の clone にしか無い。**具体的には、**手順 5 で退避した
  `<SCRATCH_DIR>/shared-checkout-prerewrite`** と、**手順 0.5 の時点で残っていた
  作業コピー**だけである。**これらを消すと、書換前の履歴はどこにも残らない。**
- **したがって、手順 3 の直前に退避物の所在を確認し、手順 4 が緑になるまで消さ
  ない。**
- **issue / PR / star / watch / fork 関係などの付帯物は、delete で失われる。**
  **これは (γ) 案 1 が承知のうえで払う代償である** (設計 §6 (γ)。本リポジトリは
  単独作業者であり、付帯物はほぼ無い)。
- **手順 4 が 0 件でなかった場合の「やり直し」は、巻き戻しではない** — もう一度
  **手順 1 → 2 → 3 (delete + 再作成 + push) → 4** を通すことである。

### 4.3 手順 6 より後 — credential は戻らない

**revoke した credential は戻せない** (§2 手順 6)。**回復は「もう一度発行する」
ことだけである。**これが**手順 6 を手順 5 の後に置いている唯一の理由**であり
(台帳 L7-12)、**手順 1〜4 が失敗して巻き戻す場合に credential を失わないため
である。**

### 4.4 手順 7 より後

**private へ戻すことはできるが、public だった間に取得された内容は回収できない。**
**手順 7 は §3 の実施記録が手順 6.5 まで埋まってから行う。**
