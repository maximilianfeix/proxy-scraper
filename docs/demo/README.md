# The demo

`checks.gif` at the top of the README is a recording of a real terminal. The commands, the checks and every line of output are the tool's own. What is simulated is the other side: six proxies and three check targets that run on localhost.

**It is a demo of how results are reported. It measures nothing about public proxies.**

## What is in the lab

`lab_server.py` starts the check targets and these "proxies" (from [`tests/lab.py`](../../tests/lab.py), the same lab the tests use). The exit IPs are documentation addresses (203.0.113.x, RFC 5737).

| Address | Behaviour | What the tool reports |
|---|---|---|
| 127.0.0.1:8081 | nothing listens there | `basic: failed (connect_refused)` |
| 127.0.0.1:8082 | the second site sees another exit IP | `confirm: failed (exit_ip_mismatch)` |
| 127.0.0.1:8083 | adds a `<script>` tag to the test page | `content: failed (content_mismatch)` |
| 127.0.0.1:8084 | forwards honestly | every check passed |
| 127.0.0.1:8085 | refuses CONNECT | `https: failed (tunnel_refused)` |
| 127.0.0.1:8086 | forwards honestly | every check passed |

The lab also plays the hourly list: its six entries are "published 41 minutes ago".

## Run it yourself

From the repository root, with the development install (`pip install -e ".[dev]"`):

```bash
python docs/demo/lab_server.py &            # the lab, until you stop it
export PATH="$PWD/docs/demo:$PATH"          # `proxy-scraper` is now the wrapper in this folder

proxy-scraper --pick 2 --verify --https-only
proxy-scraper --diagnose 127.0.0.1:8083
proxy-scraper --diagnose 127.0.0.1:8085 --json

kill %1
```

`docs/demo/proxy-scraper` is the real command line with two things swapped: the list comes from the lab instead of GitHub, and the check targets are the lab's instead of checkip.amazonaws.com and httpbin.org.

## Record it again

```bash
vhs docs/demo/demo.tape                     # needs https://github.com/charmbracelet/vhs
```

The older images in `docs/` (`demo.svg`, `dashboard.svg`, `summary.svg`, `wizard.svg`) are different: they show the real interface with made-up numbers, rendered by `docs/make_demo.py`. They are illustrations, and the README labels them as such.
