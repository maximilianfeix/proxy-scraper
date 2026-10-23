# MCP server: setup for every client

← [README](../README.md) · [All docs](README.md)

What the server does, its tools and the setup for Claude Code, Claude Desktop and Cursor are in the [README](../README.md#mcp).

**VS Code** – `.vscode/mcp.json`:

```json
{
  "servers": {
    "proxy-scraper": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
    }
  }
}
```

**Codex** – `~/.codex/config.toml`:

```toml
[mcp_servers.proxy-scraper]
command = "uvx"
args = ["--python", ">=3.10", "--from", "proxy-scraper-cli[mcp]", "proxy-scraper-mcp"]
```

**Without uv:** `pipx install --python python3.12 "proxy-scraper-cli[mcp]"` (any Python 3.10+), then use `proxy-scraper-mcp` as the command.

**Docker** – no Python needed, the image has everything:

```json
{
  "mcpServers": {
    "proxy-scraper": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/maximilianfeix/proxy-scraper", "--mcp"]
    }
  }
}
```

It's also in the [official MCP registry](https://registry.modelcontextprotocol.io) as `io.github.maximilianfeix/proxy-scraper`, so clients that browse the registry can install it from there.
