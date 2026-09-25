# Discord bot

Posts every run of the [live proxy list](https://maximilianfeix.github.io/proxy-scraper/) into a Discord server and answers slash commands. It sets up its own channels, so after inviting it there is nothing to click.

| Channel | What's in it |
|---|---|
| `#about` | what the server is, pinned |
| `#live-feed` | a summary after every run (every 6 hours) with the 10 fastest proxies and `all.txt` attached |
| `#http` `#socks4` `#socks5` | the current list per protocol, replaced after every run |
| `#commands` | the only channel where members can write |

| Command | |
|---|---|
| `/proxies` | filter by type, country, HTTPS, elite, datacenter; up to 25 shown, the rest as a file |
| `/proxy` | one fast proxy to try, with a ready `curl` command |
| `/stats` | numbers of the last run |
| `/about` | what the bot does |

Answers to commands are only visible to whoever asked, so `#commands` doesn't fill up.

## Setup

1. **Create the application** at <https://discord.com/developers/applications> → *New Application* → *Bot* → *Reset Token*. No privileged intents are needed.
2. **Invite it** with this link (replace `APPLICATION_ID` with the ID from *General Information*):

   ```
   https://discord.com/oauth2/authorize?client_id=APPLICATION_ID&scope=bot+applications.commands&permissions=268561456
   ```

   The permissions are: view channels, send messages, embed links, attach files, read message history, manage messages (to replace its old lists and pin `#about`), manage channels and roles (to create its channels read-only) and manage server (to set the server icon once, if there is none).

3. **Add the secrets** to the repository (*Settings → Secrets and variables → Actions*):

   | Secret | |
   |---|---|
   | `DISCORD_TOKEN` | the bot token |
   | `DEPLOY_HOST` | IP or host name of the server |
   | `DEPLOY_SSH_KEY` | private key that may log in as `root` |
   | `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan -t ed25519 <host>`, so the workflow never talks to a server it doesn't know |

4. **Deploy**: every push to `main` that changes `bot/` runs [`.github/workflows/bot.yml`](../.github/workflows/bot.yml): tests, then the code goes to `/opt/proxybot/app`, the token to `/etc/proxybot.env` (mode 600) and [`deploy/install.sh`](deploy/install.sh) sets up a system user, a venv and a hardened systemd service. *Run workflow* on the Actions page redeploys by hand.

On the server:

```bash
systemctl status proxybot
journalctl -u proxybot -f
```

## Running it locally

```bash
cd bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DISCORD_TOKEN=... .venv/bin/python -m proxybot
```

| Variable | Default | |
|---|---|---|
| `DISCORD_TOKEN` | – | required |
| `PROXYBOT_FEED_URL` | the GitHub Pages site | where `stats.json`, `proxies.json` and `history.json` come from |
| `PROXYBOT_POLL_SECONDS` | `300` | how often to look for a new run (at least 60) |
| `PROXYBOT_STATE` | `state.json` | remembers which run was posted where, so restarts don't post twice |

Tests: `cd bot && python -m pytest tests`
