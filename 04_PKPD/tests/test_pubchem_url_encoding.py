"""PubChem embeds the compound NAME in the URL path — so the name segment must be encoded.

The blocker: `compound/name/{name}/cids/JSON` with `name = "SALMETEROL XINAFOATE"` puts a raw space
in the path, and urllib raises `InvalidURL` before the request is even sent. In a bulk warm-up that
crashed the whole run — a non-Rejection exception is not a counted miss.

The fix must be SURGICAL:

  * the NAME path segment is percent-encoded (`quote(name, safe="")`) — space -> %20, reserved and
    non-ASCII characters escaped;
  * the path SEPARATORS and the `/cids/JSON` structure are NOT touched;
  * the property path (`compound/cid/{cid}/property/A,B,C/JSON`) keeps its commas — those are
    PubChem's list separator, not data to encode;
  * a simple ASCII name is byte-for-byte unchanged, so no existing cache entry moves.
"""

from __future__ import annotations

import pytest

from analysis.pubchem import PROPERTIES, name_to_cids_path


def test_a_space_in_the_name_is_percent_encoded_not_left_raw():
    """THE BLOCKER. SALMETEROL XINAFOATE crashed the run with InvalidURL."""
    path = name_to_cids_path("SALMETEROL XINAFOATE")
    assert path == "compound/name/SALMETEROL%20XINAFOATE/cids/JSON"
    assert " " not in path


@pytest.mark.parametrize("name,expected", [
    ("temozolomide", "compound/name/temozolomide/cids/JSON"),        # simple: UNCHANGED
    ("SALMETEROL XINAFOATE", "compound/name/SALMETEROL%20XINAFOATE/cids/JSON"),
    ("N,N-dimethyl", "compound/name/N%2CN-dimethyl/cids/JSON"),      # comma -> %2C (it is data here)
    ("3/4-substituted", "compound/name/3%2F4-substituted/cids/JSON"),  # slash -> %2F, not a sep
    ("acetazolamide?", "compound/name/acetazolamide%3F/cids/JSON"),  # reserved query char
    ("l-arginine", "compound/name/l-arginine/cids/JSON"),            # hyphen stays (unreserved)
])
def test_reserved_and_separator_characters_are_escaped_in_the_name_segment(name, expected):
    assert name_to_cids_path(name) == expected


def test_a_non_ascii_name_is_encoded_as_utf8_percent_bytes():
    path = name_to_cids_path("β-alanine")
    assert path == "compound/name/%CE%B2-alanine/cids/JSON"     # β = U+03B2 = CE B2 in UTF-8
    assert path.isascii()                                       # the URL itself is pure ASCII


def test_a_simple_name_is_byte_identical_so_no_cache_entry_moves():
    """The regression guard for the happy path: the fix must not change the URL — and therefore
    the cache key — of any name that already worked."""
    assert name_to_cids_path("temozolomide") == "compound/name/temozolomide/cids/JSON"
    assert name_to_cids_path("aspirin") == "compound/name/aspirin/cids/JSON"


def test_the_property_path_keeps_its_commas_they_are_pubchems_list_separator():
    """The commas between property names are STRUCTURE, not data. Encoding them would ask PubChem
    for a single property literally named 'A,B,C' and get nothing."""
    from analysis.pubchem import cid_to_property_path

    path = cid_to_property_path("5394")
    assert path == f"compound/cid/5394/property/{','.join(PROPERTIES)}/JSON"
    assert "," in path and "%2C" not in path


# ------------------------------------------------------- end to end, through the real adapter


def test_a_name_with_a_space_reaches_the_transport_as_a_valid_encoded_url():
    """The whole point: the encoded URL is what goes on the wire, and it no longer contains a raw
    space. Driven through the real adapter with an offline transport that records what it is asked
    for."""
    from analysis.acquire_http import Client, StaticTransport
    from analysis.acquisition import RunRoot
    from analysis.firewall import Rejection

    PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    url = f"{PUG}/compound/name/SALMETEROL%20XINAFOATE/cids/JSON"
    routes = {url: (200, {"content-type": "application/json"},
                    b'{"IdentifierList": {"CID": [5152]}}')}
    transport = StaticTransport(routes, clock="2026-07-13T05:00:00Z")

    import tempfile

    client = Client(transport=transport, allow_network=True)
    from analysis.pubchem import acquire_pubchem_identity

    # the property fetch will 404 in this minimal fixture; we only care that the NAME url was valid
    try:
        acquire_pubchem_identity(client, RunRoot(tempfile.mkdtemp() + "/run"),
                                 "SALMETEROL XINAFOATE")
    except Rejection:
        pass

    assert transport.seen, "no request was attempted"
    assert transport.seen[0] == url                  # the encoded URL, no raw space
    assert " " not in transport.seen[0]
