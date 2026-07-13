"""Source-provenance generator: JSON via a serializer (never shell interpolation), so an
ETag containing literal double-quotes or a control char is escaped, not corrupted. The
PUBLIC record carries public URL / basename / hash / bytes / timestamps but NO machine
path; the operational record (with the local path) is kept separate and non-publishable.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_source_provenance as sp   # noqa: E402
from druglink.hashing import contains_local_path         # noqa: E402

HEADERS = (
    'HTTP/1.1 200 OK\r\n'
    'Content-Length: 5764252857\r\n'
    'Last-Modified: Fri, 29 May 2026 06:35:28 GMT\r\n'
    'ETag: "1571abc-deadbeef"\r\n'          # ETags legitimately contain double-quotes
    'Content-Type: application/x-gzip\r\n'
)


def test_etag_with_double_quotes_round_trips_through_json():
    op = sp.operational_record(
        name="chembl_sqlite", url="https://ftp.ebi.ac.uk/x/chembl_37_sqlite.tar.gz",
        headers=HEADERS, sha256="a" * 64, size_bytes=5764252857,
        accessed_start="2026-07-13T06:29:16Z", accessed_end="2026-07-13T07:08:12Z",
        local_path="/home/tcelab/.cache/x/chembl_37_sqlite.tar.gz")
    # the ETag is preserved verbatim, quotes and all, and the JSON is valid
    text = sp.to_json(op)
    back = json.loads(text)
    assert back["etag"] == '"1571abc-deadbeef"'


def test_control_char_in_header_is_escaped_not_corrupted():
    headers = 'HTTP/1.1 200 OK\r\nETag: "a\tb"\r\n'   # tab inside the value
    op = sp.operational_record(
        name="x", url="https://h/x", headers=headers, sha256="b" * 64,
        size_bytes=1, accessed_start="t", accessed_end="t")
    json.loads(sp.to_json(op))                # must parse; no exception


def test_public_record_has_no_machine_path():
    pub = sp.public_record(
        name="chembl_sqlite", url="https://ftp.ebi.ac.uk/x/chembl_37_sqlite.tar.gz",
        sha256="a" * 64, size_bytes=5764252857,
        last_modified="Fri, 29 May 2026 06:35:28 GMT",
        accessed_start="2026-07-13T06:29:16Z", accessed_end="2026-07-13T07:08:12Z",
        publisher_checksum="33c2037")
    assert contains_local_path(pub) == []          # no /home, /Users, ...
    assert "local_path" not in json.dumps(pub)
    assert pub["basename"] == "chembl_37_sqlite.tar.gz"
    assert pub["url"] and pub["sha256"] and pub["size_bytes"] == 5764252857


def test_operational_record_keeps_local_path_for_the_non_public_log():
    op = sp.operational_record(
        name="x", url="https://h/f.gz", headers="HTTP/1.1 200 OK\r\n",
        sha256="c" * 64, size_bytes=2, accessed_start="t", accessed_end="t",
        local_path="/home/tcelab/.cache/x/f.gz")
    assert op["local_path"] == "/home/tcelab/.cache/x/f.gz"       # operational only
    # but the PUBLIC projection of the same artifact drops it
    pub = sp.public_from_operational(op)
    assert contains_local_path(pub) == []


def test_write_json_emits_parseable_bytes(tmp_path):
    p = str(tmp_path / "rec.json")
    sp.write_json(p, {"etag": '"x"', "n": 1})
    with open(p) as fh:
        assert json.load(fh) == {"etag": '"x"', "n": 1}    # round-trips
