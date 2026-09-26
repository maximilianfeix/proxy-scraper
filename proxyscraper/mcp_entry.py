"""`proxy-scraper-mcp`: starts the MCP server over stdio – or explains what's missing.

A separate module on purpose: it has to run without the MCP SDK, to say how to install it.
stdout belongs to the MCP protocol: every message here goes to stderr.
"""

import sys

INSTALL_HINT = 'The MCP server needs the MCP SDK: pip install "proxy-scraper[mcp]"  (or: pipx inject proxy-scraper mcp)'


def _load_server():
    from . import mcp_server
    return mcp_server


def main() -> int:
    if sys.version_info < (3, 10):
        print(f"The MCP server needs Python 3.10 or newer (this is {sys.version_info[0]}.{sys.version_info[1]}). "
              "The rest of proxy-scraper works on 3.9.", file=sys.stderr)
        return 1
    try:
        server = _load_server()
    except ImportError as e:
        if e.name and e.name.split(".")[0] in ("mcp", "pydantic"):
            print(INSTALL_HINT, file=sys.stderr)
            return 1
        raise
    return server.serve()


if __name__ == "__main__":
    sys.exit(main())
