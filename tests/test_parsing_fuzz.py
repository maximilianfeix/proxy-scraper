"""Fuzzing the parser: 700+ lists throw everything at it. Whatever comes in, it must not crash, and whatever comes
out must be a well-formed key with a public address and a valid port (#120)."""

import re

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import assume, example, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from proxyscraper.parsing import (  # noqa: E402
    PROXY_TYPES,
    extract_candidates,
    normalize_public_ip,
    parse_proxy_line,
    validate_candidates,
)

KEY_RE = re.compile(r"^(http|socks4|socks5) (?:([^\s@]+)@)?(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$")
TYPES = [*PROXY_TYPES, "auto"]

octet = st.integers(0, 255)
ips = st.tuples(octet, octet, octet, octet).map(lambda t: ".".join(map(str, t)))
ports = st.integers(10, 65535)  # the parser wants 2+ digits: "1.2.3.4:5" is a version number, not a proxy
# text that looks a bit like proxy lists: digits, dots, colons, schemes, HTML and JSON bits
listish = st.text(alphabet=st.sampled_from(list("0123456789.:/ \n\t,;\"'{}[]<>@#=-_abcdhkopstxy")), max_size=400)


def keys_of(data: bytes, ptype: str):
    return validate_candidates(extract_candidates(data, ptype))


def assert_well_formed(key: str):
    m = KEY_RE.match(key)
    assert m, key
    ip, port = m[3], int(m[4])
    assert normalize_public_ip(ip.encode()) == ip, key  # public and without leading zeros
    assert 1 <= port <= 65535, key


@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=2000), st.sampled_from(TYPES))
def test_random_bytes_never_crash(data, ptype):
    for key in keys_of(data, ptype):
        assert_well_formed(key)


@settings(max_examples=300, deadline=None)
@given(listish, st.sampled_from(TYPES))
def test_list_like_text_only_yields_well_formed_keys(text, ptype):
    for key in keys_of(text.encode(), ptype):
        assert_well_formed(key)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(ips, ports), min_size=1, max_size=20),
       st.sampled_from(["{ip}:{port}", "{ip}:{port} ", "  {ip}:{port}", "{ip}\t{port}", "<td>{ip}</td><td>{port}</td>",
                        '{{"ip": "{ip}", "port": {port}}}']),
       st.sampled_from(PROXY_TYPES))
def test_every_public_address_is_found_whatever_the_format(pairs, fmt, ptype):
    data = "\n".join(fmt.format(ip=ip, port=port) for ip, port in pairs).encode()
    found = {k.split(" ", 1)[1] for k in keys_of(data, ptype)}
    expected = {f"{ip}:{port}" for ip, port in pairs if normalize_public_ip(ip.encode()) == ip}
    assert found == expected


@settings(max_examples=200, deadline=None)
@given(ips, ports, st.sampled_from(PROXY_TYPES))
def test_scheme_lines_keep_their_type(ip, port, ptype):
    assume(normalize_public_ip(ip.encode()) == ip)
    keys = keys_of(f"{ptype}://{ip}:{port}\n".encode(), "auto")
    assert keys == {f"{ptype} {ip}:{port}"}


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=200), st.sampled_from([None, *PROXY_TYPES]))
@example("1.2.3.4:\u00b2", "http")   # "²" passes str.isdigit(), int() can't read it (found in review)
@example("1.2.3.\u0661:80", "http")  # an Arabic-Indic digit
def test_result_file_lines_never_crash(line, default_type):
    key = parse_proxy_line(line, default_type)
    if key is not None:
        assert key.split(" ", 1)[0] in PROXY_TYPES
