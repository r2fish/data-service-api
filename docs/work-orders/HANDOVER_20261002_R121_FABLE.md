# 引き継ぎ書 — 2026-10-02 R-121 (socket 経路の redirect 先に宣言の port が無い) 実装済み・閉止前

本書は cloud session (claude.ai の Claude Code、root のコンテナ) で行った R-121 の実施の記録であり、閉止に要る実測・変異・完了ゲートを作業機 (Mac、`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §2 の開発機) の監督チャットへ引き継ぐ。規律の正本は `OC`、R-121 の正本は台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §8.1 の R-121 の行 (規模 S なので台帳行が作業指示書。`OC` §1.13 の 74)。

## 1. 現在地

- 変更は branch `claude/blissful-gauss-dk9gfk` (origin に push 済み) の 3 commit にある: `619e285` (修正本体と test 2 本)、`3609989` (コードレビュー 1 巡目の 7 件の反映)、`98190a1` (再確認レビューの 4 件の反映)。本書の commit がその上に乗る。local main (`4241b55`) には何も入れていない。cloud session からの push は作業ブランチのみで、`CI` の trigger は `main` への push と `workflow_dispatch` だけなので Actions は走っていない (`OC` §3 の 7)。
- 変更の中身 (Class C、`tools/change_class.py` の下限も C): `conformance-tests/socket_harness.py` の nginx 雛形と `r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example` の、proxied な 2 つの `location` で `proxy_set_header Host $host` → `$http_host` (client の `Host` を port ごと upstream へ渡す。upstream (Starlette 1.6.0 の `redirect_slashes`) は受け取った `Host` から `Location` の authority を組む)。test は `conformance-tests/test_wire_entry.py::test_socket_redirect_location_keeps_the_declared_authority` (socket の 2 plug × surface data / control の 4 item。timeout 付きの plain `httpx` 要求で、redirect は追わない) と `r2db-api/tests/test_deploy_nginx_host_header_static.py` (雛形の静的 pin: proxied location の集合 == `/v1/`・`/control/v1/`、各 1 つの `Host $http_host`、`$host` 無し)。文書は `docs/design/CONFORMANCE_ADAPTER_V1.md` §31.2 の Note、`docs/design/REFERENCE_CLIENT_V0_1.md` v0.7 註の【追記】と行番号参照、`docs/design/AUDIT_PROCESS_LOSS_V0_1.md`:44 の行番号参照、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` Step 5 の「Already-installed copies」の段落。
- cloud session で確認済み: 静的 test は `--noconftest` で `1 passed`。手製の変異確認 (雛形の一時コピーに test 関数を適用) は data block `$host` / control block `$host` / 第 3 の proxied location / 小文字の `host` directive の追加 / directive のコメントアウト の 5 通りがすべて赤。描画した harness の conf は `nginx -t` 合格 (nginx 1.24.0)。pre-commit の 3 hook (public-value-scan / check-doc-refs / ledger-check) は各 commit で Passed。レビュー担当 2 起動 (1 巡目 7 件、再確認 4 件。報告は cloud session の scratchpad にあり持ち越せないので、全件を本書の「裁定」に写した)。
- cloud session で**できなかったこと**: `initdb` が root を拒むため `tools/dev/pt.py` / `mutate.py` / `gate.py` が conftest の使い捨てクラスタ起動で止まる (exit 4)。非特権ユーザーの作成は許可されなかった。したがって wire の test の実測、`mutate.py` の 5 変異、完了ゲートは未実施。R-121 の台帳行は未着手のまま (追記は実測の後に書く。`OC` §1.5 の 34)。
- 記録の置き場: 本書を commit する変更セットで、最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` を `docs/archive/docs/work-orders/` へ移した (`OC` §1.16 の 78)。

## 2. 本チャットで閉じたもの

- 閉じた台帳行はない。R-121 は実装とレビュー 2 巡まで。
- 監督裁定 (R-121 の枠): 直し方は台帳行の候補 1 (`$http_host`)。候補 2 (peer が末尾 slash の redirect を返さない) は peer の挙動の変更になるので採らない。harness と r2db の本番雛形を同じ 1 語で直し、`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-3 の「写す」関係を保つ。MitateDB は本番で nginx を使わない (同 D-3) ので雛形の変更は r2db のみ。
- 完了条件 → 変異 (台帳行の【追記】に写す):
  1. socket の 2 plug で、data / control 両 surface の capabilities path に末尾 slash を付けた要求への 3xx の `Location` の authority (host:port) が、その surface の宣言の base URL の authority と一致し、path が capabilities の path である — `conformance-tests/test_wire_entry.py::test_socket_redirect_location_keeps_the_declared_authority` ↔ M1 (harness の `/v1/` の `$http_host` → `$host`)、M1b (同 `/control/v1/`)。
  2. r2db の本番雛形の proxied location が `/v1/`・`/control/v1/` だけで、各 1 つの `proxy_set_header Host $http_host;` を持ち `$host` を持たない — `r2db-api/tests/test_deploy_nginx_host_header_static.py` ↔ M2 (雛形の data-plane block)、M2b (control block)、M2c (`proxy_pass` 付きの第 3 の location を足す)。
- 変異 spec (5 件。`old` はすべて現物にちょうど 1 回出現する):

```json
{
 "pytest": ["-q"],
 "mutations": [
  {"id": "M1-harness-data-host-without-port", "file": "conformance-tests/socket_harness.py",
   "old": "            proxy_pass http://127.0.0.1:{data_port};\n            proxy_http_version 1.1;\n            proxy_set_header Host $http_host;",
   "new": "            proxy_pass http://127.0.0.1:{data_port};\n            proxy_http_version 1.1;\n            proxy_set_header Host $host;",
   "tests": ["conformance-tests/test_wire_entry.py", "-k", "test_socket_redirect_location_keeps_the_declared_authority"], "expect": "red"},
  {"id": "M1b-harness-control-host-without-port", "file": "conformance-tests/socket_harness.py",
   "old": "            proxy_pass http://127.0.0.1:{control_port};\n            proxy_http_version 1.1;\n            proxy_set_header Host $http_host;",
   "new": "            proxy_pass http://127.0.0.1:{control_port};\n            proxy_http_version 1.1;\n            proxy_set_header Host $host;",
   "tests": ["conformance-tests/test_wire_entry.py", "-k", "test_socket_redirect_location_keeps_the_declared_authority"], "expect": "red"},
  {"id": "M2-example-data-host-without-port", "file": "r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example",
   "old": "        # not carried here.\n        proxy_set_header Host $http_host;",
   "new": "        # not carried here.\n        proxy_set_header Host $host;",
   "tests": ["r2db-api/tests/test_deploy_nginx_host_header_static.py"], "expect": "red"},
  {"id": "M2b-example-control-host-without-port", "file": "r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example",
   "old": "        # (ledger R-121).\n        proxy_set_header Host $http_host;",
   "new": "        # (ledger R-121).\n        proxy_set_header Host $host;",
   "tests": ["r2db-api/tests/test_deploy_nginx_host_header_static.py"], "expect": "red"},
  {"id": "M2c-example-third-proxied-location-without-host", "file": "r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example",
   "old": "    location / {\n        return 404;\n    }",
   "new": "    location /extra/ {\n        proxy_pass http://127.0.0.1:9;\n    }\n\n    location / {\n        return 404;\n    }",
   "tests": ["r2db-api/tests/test_deploy_nginx_host_header_static.py"], "expect": "red"}
 ]
}
```

## 3. 次の一手 (作業機の監督チャット)

1. `git fetch origin claude/blissful-gauss-dk9gfk` → `git worktree add .claude/worktrees/r121 -b r121 origin/claude/blissful-gauss-dk9gfk` (共有ツリーを checkout しない。`OC` §1.2 の 14)。
2. 上の spec を scratchpad に `r121-mutations.json` として保存する。
3. 実測: `tools/dev/pt.py -C .claude/worktrees/r121 -- conformance-tests/test_wire_entry.py -q -k test_socket_redirect_location_keeps_the_declared_authority` (4 item。timeout 600000)。`MitateDB-api-socket-control` の item だけは静的読解に基づく見込み (裁定の表の再確認 1) なので、赤ならその時点で control 側の扱いを裁定し直す (候補: 登録 plug の control surface が未起動なら test の中で起動を強いる、または control 側を data 側と別の完了条件に分けて §4 の 2 の行の後へ回す)。
4. 変異: `tools/dev/mutate.py "$SP/r121-mutations.json" -C .claude/worktrees/r121` (5 件とも `red` が合格)。
5. 完了ゲート: `tools/dev/gate.py -C .claude/worktrees/r121 --label r121` (`OC` §1.3 の 22。`COLLECTION_FLOOR` は 5014 から +5 (wire 4 item + static 1) の見込み。更新は完了ゲートで監督が行う。`OC` §1.3 の 25)。
6. 台帳 v1.150 の変更セット (1 commit): R-121 の行に【追記 (v1.150)】(完了条件・変異・集計行・レビュー 2 起動・裁定の所在 = 本書) を書いて閉止し、行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の末尾へ逐語で移して §8.2 に索引行を足す (`OC` §1.16 の 79)。同じ変更セットで MitateDB socket plug の control 宣言の件を §8.1 に起票する (下の §4 の 2。番号は 121 の次)。版数ログは v1.150 の行を足し、6 版目 (v1.145) の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` のヘッダ直後へ回す (`OC` §1.16 の 78)。本書の末尾に追記 (集計行と閉止) を足す。
7. `tools/dev/finalize.py -C .claude/worktrees/r121 --branch r121 --allow 'conformance-tests/*' --allow 'r2db-api/*' --allow 'docs/*' -m <msg> --tools-tests` で commit し、local main へ `--no-ff` で merge する (`OC` §1.1 の 3〜4)。main の push は依頼者の指示の後、従来どおり作業機側の統制で行う。
8. 依頼者の運用作業: 実ホストに 8443 の雛形の copy が入っていれば、両 block の `Host` 行を `$http_host` に入れ替えて `nginx -t` と reload (runbook Step 5 の「Already-installed copies」)。

## 4. 依頼者判断待ち・未決

1. 既設の 8443 配備が今も稼働しているか (稼働していれば §3 の 8 を行う)。本書の材料からは分からない。
2. 起票予定の行 (番号は台帳の版上げ時に main を読んで振る。121 の次。`conformance-tests/test_wire_entry.py` の test の docstring はその番号を `ledger` 付きで先に名指しているので、版上げでは同じ番号を使う。規模 S 見込み、Class C 見込み、着手条件なし): **MitateDB の socket plug の isolated surface が宣言する control base URL は、port を予約するだけで応答する surface が無い。** `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` の `_reset_surface_state` が `_control_listen_reservation` を None にし、`_surfaces_value()` が新しい control port を予約して isolated copy の `FoundationConfig.control_base_url` に入るが、isolated copy の control client は親の `_control_client` (親の control surface) を使い回し、予約した port で応答する surface はどの経路でも作られない (r2db の socket plug は isolated copy が親の `_control_surface` を共有するので該当しない)。DB の利用者には見えないが、isolated surface の文書を信じて control を dial する test は応答待ちで止まる (再確認レビューの指摘 1)。直し方の候補: (i) `_reset_surface_state` で control の予約を reset せず r2db と同じく親の control 面を借りる、(ii) isolated copy に専用の control surface を立てる。直し方の候補の選択は監督裁定。
3. cloud session で完了ゲートまで回したい場合は、環境の setup script (非 root ユーザー、nginx、PostgreSQL 16 server) を一度整える必要がある。必要なら `OC` §2 の cloud session 条件として別に起票する。本件では採らなかった (推奨 2 を依頼者が採用、2026-10-02)。

## 5. 運用上の教訓

- cloud session (root コンテナ) では `initdb` が動かないので、PostgreSQL を要する test・変異・完了ゲートは回せない。回せるのは静的 test (`--noconftest`)、`nginx -t`、pre-commit の hook、レビュー担当の静的照合、commit と作業ブランチへの push。着手前にこの範囲を宣言しておくと、後の分担が決めやすい。
- 行番号参照 (`file:line`) を持つ設計文書は、ソースへの数行の挿入でずれる。R-121 の 8 行の挿入で `REFERENCE_CLIENT_V0_1.md` と `AUDIT_PROCESS_LOSS_V0_1.md` の計 8 箇所がずれた。挿入するコメントの行数を途中で変えると参照を全部やり直すことになる (再確認の後に 1 行足して戻した)。
- 「測った」は実測の後に書く (`OC` §1.5 の 34)。cloud session のように実測が後ろに回る場合、文書の註は「test が固定する。実測は台帳の追記」の形にしておく。

## 6. 裁定

`OC` §1.15 の 77。材料はレビュー担当の報告 2 通 (1 巡目 7 件、再確認 4 件。担当観点: 指定なし)。同じ変更セットで直した件は「直した」。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1 巡目 1 (harness の `/control/v1/` block を観測する test も変異も無い) | 直した | test を `surface` (data / control) で parametrize し、変異 M1b を足した (`3609989`) |
| レビュー 1 巡目 2 (設計文書の実測の記述 (`CA` §31.2、`RC` v0.7 註) と行番号の参照が古くなる) | 直した | 本文は消さず日付付きの Note / 【追記】を直後に足し、`RC`:127・:352 の行番号を現物に合わせた |
| レビュー 1 巡目 3 (既設の 8443 配備の copy には直しが届かない) | 直した (文書) + 依頼者の運用作業 | runbook Step 5 に「Already-installed copies」の段落。実ホストの入れ替えは §3 の 8 |
| レビュー 1 巡目 4 (Host の無い HTTP/1.0 要求が本番雛形で素の 400 になる) | 観察 | 契約の client は HTTP/1.1 で Host を送る。map は server block の外になるので置かない。雛形のコメントに「Disclosed:」として開示した |
| レビュー 1 巡目 5 (static test の parser の穴: proxied 集合、大文字小文字、入れ子) | 直した | proxied 集合 == `PROXIED_LOCATIONS`、directive 名は `.lower()`、入れ子は assert で拒む。変異 M2b・M2c を足した |
| レビュー 1 巡目 6 (雛形コメントの「carrying its bearer」が言い過ぎ) | 直した | 資格情報を付け直して redirect を追う client に限定した (雛形コメントと static test の docstring) |
| レビュー 1 巡目 7 (新 test の docstring と assert の不一致) | 直した | 「explicit port」に |
| 再確認 1 (MitateDB socket plug の isolated copy が宣言する control base URL は予約だけで応答が無く、control 側の test が応答待ちで止まる) | 直した (test) + 起票 (§4 の 2、番号は版上げ時) | test は control の URL を登録 plug 自身の文書 (`adapter.capability_document()`) から取り、要求を timeout 付きの plain `httpx` に変えた (`98190a1`)。plug の欠陥は §4 の 2 として起票する (DB の利用者は気づかないが、isolated surface の宣言を信じる test が止まるので検査器の穴として残さない) |
| 再確認 2 (実測前に「測った」と書いている。`OC` §1.5 の 34) | 直した | harness のコメント・`CA` §31.2 の Note・`RC` の【追記】を「test が固定する。実測は台帳 R-121 の追記」の形にした |
| 再確認 3 (`docs/design/AUDIT_PROCESS_LOSS_V0_1.md`:44 の行番号参照がずれた) | 直した | +8 行のずれを現物に合わせた (:802・:880・:974・:399-433) |
| 再確認 4 (`RC` v0.7 註の「上の項は書き換えない」と行番号の更新が食い違う) | 観察 | 行番号の更新は判定を覆すものではなく参照を解決可能に保つだけ (`OC` §1.8 の 56 の対象外) |
