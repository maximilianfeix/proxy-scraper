import asyncio

import pytest

from proxyscraper import netio
from proxyscraper import parsing as p


def parse(data: bytes, ptype: str = "http"):
    return sorted(p.validate_candidates(p.extract_candidates(data, ptype)))


def test_plain_ip_port_lines():
    assert parse(b"1.2.3.4:8080\n5.6.7.8 3128\n") == ["http 1.2.3.4:8080", "http 5.6.7.8:3128"]


def test_space_separated_list_later_in_file():
    data = b"1.2.3.4:8080\n" * 3 + b"5.6.7.8\t3128\n"
    assert "http 5.6.7.8:3128" in parse(data)


def test_html_table_cells():
    assert parse(b"<tr><td>9.9.9.9</td><td>3128</td><td>US</td></tr>") == ["http 9.9.9.9:3128"]


def test_json_both_key_orders():
    data = b'[{"ip":"8.8.4.4","anonymity":"elite","port":"8000"},{"port":81,"ip":"8.8.8.9"}]'
    assert parse(data, "socks5") == ["socks5 8.8.4.4:8000", "socks5 8.8.8.9:81"]


def test_scheme_prefix_overrides_source_type():
    data = b"socks5://5.6.7.8:1080\nhttps://user:pw@4.4.4.4:8080\n1.2.3.4:80\n"
    assert parse(data, "socks4") == ["http user:pw@4.4.4.4:8080", "socks4 1.2.3.4:80", "socks5 5.6.7.8:1080"]


def test_auto_source_only_uses_prefixed_lines():
    assert parse(b"socks4://5.6.7.8:1080\n1.2.3.4:80\n", "auto") == ["socks4 5.6.7.8:1080"]


def test_private_and_invalid_addresses_are_dropped():
    data = b"10.0.0.1:80\n192.168.1.1:8080\n300.1.1.1:80\n1.1.1.1:70000\n001.002.003.004:0080\n"
    assert parse(data) == ["http 1.2.3.4:80"]


def test_ip_followed_by_ip_is_not_a_port():
    assert parse(b"11.1.1.1 12.1.1.1\n") == []


def test_parse_blob_filters_types_and_joins():
    out = p.parse_blob(b"socks5://5.6.7.8:1080\n1.2.3.4:80\n", "http", ("http",))
    assert out == "http 1.2.3.4:80"


def test_parse_proxy_lines_from_result_files():
    lines = ["socks5://1.2.3.4:1080", "# Kommentar", "5.6.7.8:3128", "http://u:p@9.9.9.9:80", "kaputt", "10.0.0.1:80"]
    assert p.parse_keys(lines) == ["socks5 1.2.3.4:1080", "http u:p@9.9.9.9:80"]
    assert p.parse_keys(lines, "socks4")[1] == "socks4 5.6.7.8:3128"


def test_response_respects_content_length_without_eof():
    # keep-alive-Server schließen nicht – es darf nur Content-Length gelesen werden
    async def go():
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 \r\nContent-Length: 5\r\nConnection: keep-alive\r\n\r\nhello")
        return await asyncio.wait_for(netio.read_response(reader), 1)

    status, _, body = asyncio.run(go())
    assert (status, body) == (200, b"hello")


def test_response_chunked():
    async def go():
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")
        reader.feed_eof()
        return await netio.read_response(reader)

    status, _, body = asyncio.run(go())
    assert (status, body) == (200, b"abcde")


@pytest.mark.parametrize("line, key", [
    ("socks5://alice:s3cret@1.2.3.4:1080", "socks5 alice:s3cret@1.2.3.4:1080"),
    ("http://alice:p%40ss%3Aword@1.2.3.4:80", "http alice:p%40ss%3Aword@1.2.3.4:80"),  # schon kodiert
    ("socks4://bob@1.2.3.4:1080", "socks4 bob@1.2.3.4:1080"),                         # nur Benutzer
    ("socks5://:nouser@1.2.3.4:1080", "socks5 1.2.3.4:1080"),                          # ohne Benutzer: weg
    ("alice:pw@1.2.3.4:3128", "http alice:pw@1.2.3.4:3128"),                           # ohne Schema
])
def test_credentials_are_kept_and_normalized(line, key):
    assert p.parse_proxy_line(line, "http") == key


def test_credentials_in_lists():
    data = b"socks5://alice:pw@1.2.3.4:1080\nsocks5://1.2.3.4:1080\n"
    # mit und ohne Login sind zwei verschiedene Proxys
    assert parse(data, "auto") == ["socks5 1.2.3.4:1080", "socks5 alice:pw@1.2.3.4:1080"]
