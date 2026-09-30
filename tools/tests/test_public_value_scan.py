"""tools/tests/test_public_value_scan.py -- tests for the R2_url rule of
tools/public_value_scan.py: every host one URL match carries is judged
(ledger R-46).

Deliberately NOT under `conformance-tests/` and NOT discoverable by the
root suite (same convention as tools/tests/test_check_image_pins.py).

Run directly:
    ./.venv/bin/python -m pytest tools/tests/test_public_value_scan.py -q

Every input is synthetic. A deny-suffix host is assembled from parts at run
time, so this file carries no contiguous value the scanner itself would
flag when it scans this file.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from urllib.parse import unquote

_MODULE_PATH = Path(__file__).resolve().parents[1] / "public_value_scan.py"
_spec = importlib.util.spec_from_file_location("public_value_scan", _MODULE_PATH)
pvs = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("public_value_scan", pvs)
_spec.loader.exec_module(pvs)  # type: ignore[union-attr]

_S = "https" + "://"
_CF = ".".join(["cloudfunctions", "net"])
_RUN = ".".join(["run", "app"])
_DENY_CF = "svc-synth." + _CF
_UNLISTED = ".".join(["synth-host", "synth-corp", "dev"])
_ALLOWED = _S + "github.com/o/r"


def _rules(line: str) -> "list[str]":
    scanner = pvs.Scanner()
    scanner.scan_line("synthetic", 1, line)
    return [rule for _path, _lineno, rule, _masked in scanner.findings]


def _url_flagged(line: str) -> bool:
    return "R2_url" in _rules(line)


# -- controls: what the rule did before R-46 --------------------------------

def test_outer_deny_host_is_flagged() -> None:
    assert _url_flagged(_S + _DENY_CF + "/f")


def test_allowed_url_alone_is_not_flagged() -> None:
    assert _rules(_ALLOWED + "?q=1#frag") == []


# -- a second URL inside the match -------------------------------------------

def test_deny_host_url_nested_in_query_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?u=" + _S + _DENY_CF + "/f")


def test_deny_host_url_nested_in_fragment_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "#" + _S + _DENY_CF)


def test_deny_host_url_nested_in_path_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "/" + _S + _DENY_CF)


def test_deny_host_url_nested_two_levels_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?a=" + _S + "pypi.org/?b=" + _S + _DENY_CF)


def test_unlisted_host_url_nested_in_query_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?u=" + _S + _UNLISTED + "/f")


def test_allowed_url_nested_in_allowed_url_is_not_flagged() -> None:
    assert _rules(_ALLOWED + "?u=" + _S + "pypi.org/p/x") == []


# -- percent-encoding ---------------------------------------------------------

def test_percent_encoded_nested_deny_url_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?u=https%3A%2F%2F" + _DENY_CF + "%2Ff")


def test_double_percent_encoded_nested_unlisted_url_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?u=https%253A%252F%252F" + _UNLISTED)


def test_percent_encoded_dots_in_deny_host_are_flagged() -> None:
    assert _url_flagged(_S + _DENY_CF.replace(".", "%2E") + "/f")


# -- authority parsing: userinfo, port, query/fragment with no path ----------

def test_userinfo_with_password_does_not_hide_unlisted_host() -> None:
    assert _url_flagged(_S + "user:pw@" + _UNLISTED + "/f")


def test_allowed_host_as_userinfo_does_not_hide_deny_host() -> None:
    assert _url_flagged(_S + "github.com:x@" + _DENY_CF + "/f")


def test_unlisted_host_in_userinfo_position_is_flagged() -> None:
    assert _url_flagged(_S + _UNLISTED + ":@github.com/o/r")


def test_unlisted_host_in_password_position_is_flagged() -> None:
    assert _url_flagged(_S + "user:" + _UNLISTED + "!@github.com/o/r")


def test_query_directly_after_unlisted_host_is_not_read_as_host() -> None:
    # Before R-46 the host ran on into the query, whose hyphenated tail
    # then read as "last label cannot be a TLD".
    assert _url_flagged(_S + _UNLISTED + "?a=b-c")


def test_backslash_directly_after_unlisted_host_is_not_read_as_host() -> None:
    assert _url_flagged(_S + _UNLISTED + "\\x-y.example.invalid")


def test_fragment_directly_after_unlisted_host_is_not_read_as_host() -> None:
    # Before R-46 the fragment's `.invalid` tail read as a placeholder domain.
    assert _url_flagged(_S + _UNLISTED + "#x.example.invalid")


def test_port_is_not_part_of_the_host() -> None:
    assert _rules(_S + "localhost:8080/health") == []


# -- a deny-suffix host with no scheme of its own inside the match -----------

def test_schemeless_deny_host_in_query_value_is_flagged() -> None:
    assert _url_flagged(_ALLOWED + "?host=" + _DENY_CF)


def test_deny_host_in_userinfo_position_is_flagged() -> None:
    assert _url_flagged(_S + _DENY_CF + "@github.com/o/r")


def test_bare_deny_suffix_in_allowed_url_path_is_not_flagged() -> None:
    assert not _url_flagged(_S + "cloud.google.com/docs/" + _CF)


# -- placeholder exclusion is judged on each host's own span -----------------

def test_placeholder_redacted_deny_host_is_not_flagged() -> None:
    assert _rules(_S + "svc-<GCP_PROJECT_NUMBER>.<REGION>." + _RUN + "/f") == []


def test_placeholder_redacted_nested_deny_host_is_not_flagged() -> None:
    line = _ALLOWED + "?u=" + _S + "svc-<GCP_PROJECT_NUMBER>.<REGION>." + _RUN + "/f"
    assert _rules(line) == []


def test_placeholder_in_path_does_not_excuse_the_host() -> None:
    # A doubled hyphen is a redaction artifact only when the placeholder was
    # removed inside the host itself.
    assert _url_flagged(_S + _UNLISTED.replace("synth-host", "synth--host") + "/p/<TABLE_ID>")


def test_placeholder_in_outer_url_does_not_excuse_nested_host() -> None:
    line = _S + "<HOST>.example.invalid/x?u=" + _S + "synth--svc." + _CF
    assert _url_flagged(line)


def test_placeholder_in_outer_url_does_not_excuse_encoded_nested_host() -> None:
    nested = "https%3A%2F%2F" + _UNLISTED.replace("synth-host", "synth--host")
    assert _url_flagged(_ALLOWED + "/<REPO>?u=" + nested)


def test_placeholder_redacted_encoded_nested_deny_host_is_not_flagged() -> None:
    nested = "https%3A%2F%2Fsvc-<GCP_PROJECT_NUMBER>.<REGION>." + _RUN + "%2Ff"
    assert _rules(_ALLOWED + "?u=" + nested) == []


def test_placeholder_redacted_host_stays_excluded_beside_an_escape() -> None:
    # The decoded form names the same host again; it is traced back to the
    # same redacted span.
    assert _rules(_S + "svc-<GCP_PROJECT_NUMBER>.<REGION>." + _RUN + "/a%20b") == []


def _pct_all(text: str) -> str:
    return "".join("%%%02X" % b for b in text.encode("utf-8"))


def test_placeholder_next_to_fully_encoded_nested_host_does_not_excuse_it() -> None:
    nested = _pct_all(_S + _UNLISTED.replace("synth-host", "synth--host") + "/")
    assert _url_flagged(_ALLOWED + "?u=" + nested + "<X>")


def test_placeholder_after_non_ascii_escape_does_not_excuse_encoded_host() -> None:
    nested = _pct_all(_S + _UNLISTED.replace("synth-host", "synth--host") + "/\u00e9")
    assert _url_flagged(_ALLOWED + "?u=" + nested + "<X>")


def test_example_project_label_stays_excluded_when_nested() -> None:
    assert _rules(_ALLOWED + "?u=" + _S + "example-project.a." + _RUN) == []


# -- the position-carrying decoder decodes what urllib does -------------------

def test_pct_decode_once_equals_urllib_unquote() -> None:
    samples = [
        "plain", "a%2Fb", "%zz%2", "a%25b", "%E3%81%82x", "%FFa%41", "%e3%81", "x%2e%2Ey", "%C3%C3",
    ]
    for text in samples:
        spans = [(k, k + 1) for k in range(len(text))]
        decoded, decoded_spans = pvs._pct_decode_once(text, spans)
        assert decoded == unquote(text), text
        assert len(decoded_spans) == len(decoded), text
    # each decoded character maps to the escapes of its own bytes
    _decoded, spans = pvs._pct_decode_once("%41%E3%81%82%42", [(k, k + 1) for k in range(15)])
    assert spans == [(0, 3), (3, 12), (12, 15)]
    # an invalid sequence reported one byte late stays inside the run
    _decoded, spans = pvs._pct_decode_once("%C3%C3", [(k, k + 1) for k in range(6)])
    assert spans == [(0, 6), (3, 6)]
