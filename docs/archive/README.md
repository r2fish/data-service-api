# docs/archive — 記録 (時点付きの履歴)

本ディレクトリは**記録**を置く。**記録 = 時点付きの履歴** (引き継ぎ書、台帳の版数ログ、改版履歴、「更新 (日付)」層、監査記録) であり、**正本 = 現在の状態を決める文** とは別である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` §1.16 の 78、設計は `docs/design/DOC_ARCHIVE_SPLIT_V1.md`。

- **path 規則**: ファイル全体は `docs/archive/<元 path>` (例 `docs/work-orders/HANDOVER_20260828.md` → `docs/archive/docs/work-orders/HANDOVER_20260828.md`)。ファイルの一部 (節) を抜いたものは `docs/archive/<元 dir>/<元 stem>__<部分名>.md` とし、先頭 3 行に 出所ファイル / 抜き出した時点 (元文書の版数と commit) / 「逐語。書き換えない」を置く。
- **参照の解決**: 他の文書が書いている `<元 path>` (`HANDOVER_X.md:NN` の行番号付きを含む) は**書き換えない**。ここへ来た文書は `docs/archive/<元 path>` で読む。移動は `git mv` で行うので行番号はそのまま通じ、`git log --follow` で履歴が繋がる。
- **本 README は例外である**: `docs/archive/` の中で**唯一の正本**であり、下の「書き換えない」規則の対象外である。規則を変えるときは設計 `docs/design/DOC_ARCHIVE_SPLIT_V1.md` の版上げと同時に行う。
- **書き換えない・消さない**: 本 README を除くここのファイルは記録であり、内容を直さない (`OPERATING_CONDITIONS.md` §1.8 の 56・57、台帳 R-14)。誤りが見つかったときは正本側に現在の値を書く。
- **検査器の扱い**: `tools/check_doc_refs.py` の**参照走査**と `tools/check_comment_provenance.py` は本ディレクトリを走査しない。`tools/change_class.py` は本ディレクトリ配下を**拡張子を問わず Class A** とする。
- **公開ゲートは変わらない**: 空 `.md` ガード (`check_doc_refs.py` の `git ls-files` 側) と `tools/public_value_scan.py` (pre-commit) は本ディレクトリにも掛かる。実 credential・実ホスト名・実ドメイン・実 DSN・作業機の絶対パスを置かないという条件は、置き場が変わっても 1 つも緩まない (`CLAUDE.md` Public Repository Security Gate 節、`OPERATING_CONDITIONS.md` §1.9)。
- **回転**: 新しい引き継ぎ書を commit する変更セットで最新 2 通から外れる引き継ぎ書を、台帳の版上げの変更セットで 6 版目の行を、それぞれ同時にここへ移す。新しく書く文書が**前々書以前**を指すときは、はじめから archive 側の path で書く。
- **台帳の閉止行**: `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の閉止・却下の行の全文は `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の `## R-N` 節にある (本体の §8.2 は索引)。「`RM` §8 の R-N 行」という既存の参照は書き換えず、ここで読む。後からの【追記】は当該節の末尾に 1 行足す (既存の行は変えない。版数ログに行を足すのと同じ扱い)。規律は `OPERATING_CONDITIONS.md` §1.16 の 79。
