# Install: every other way

← [README](../README.md) · [All docs](README.md)

The quick install (pipx, Homebrew) is in the [README](../README.md#install). Docker, pip, a faster event loop, the latest main and running from a clone:

```bash
# Docker – learned state and results stay in two folders next to you
mkdir -p proxy-data results
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/proxy-data:/data" -v "$PWD/results:/work/results" \
  ghcr.io/maximilianfeix/proxy-scraper --want 50 --https-only

# pip into the current environment
pip install proxy-scraper-cli

# optional: faster event loop on macOS/Linux
pipx install "proxy-scraper-cli[fast]"

# the latest main instead of the latest release
pipx install git+https://github.com/maximilianfeix/proxy-scraper.git

# no install at all
git clone https://github.com/maximilianfeix/proxy-scraper.git
cd proxy-scraper
pip install -r requirements.txt
python3 proxy_scraper.py
```

Every [release](https://github.com/maximilianfeix/proxy-scraper/releases/latest) also ships a wheel you can install with `pip install <file>.whl`, and a multi-arch image (amd64/arm64) on `ghcr.io`. In the container the wizard never shows up, it runs straight away. For the proxy server use `--serve --serve-host 0.0.0.0 --serve-open` with `-p 127.0.0.1:8899:8899`, so the port is only open on your own machine – or set `-e PROXY_SCRAPER_SERVE_PASSWORD=…` instead of `--serve-open`.

Tab completion for bash, zsh, fish and PowerShell:

```bash
eval "$(proxy-scraper --completion zsh)"     # in ~/.zshrc (after compinit), same for bash in ~/.bashrc
proxy-scraper --completion fish > ~/.config/fish/completions/proxy-scraper.fish
proxy-scraper --completion powershell | Out-String | Invoke-Expression   # in $PROFILE
```

Installed, the learned state lives in your user data folder (`~/Library/Application Support/proxy-scraper`, `%LOCALAPPDATA%\proxy-scraper` or `~/.local/share/proxy-scraper`; override with `PROXY_SCRAPER_HOME`) and results go to `./results`. Run from a clone, both stay inside the project. After the second run that finds proxies it asks once for a GitHub star; `PROXY_SCRAPER_NO_STAR_HINT=1` turns that off (it never shows in CI).
