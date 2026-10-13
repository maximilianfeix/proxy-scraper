# The README clip. Run from the repository root:  vhs docs/demo/demo.tape
# Everything on screen is real output of the real command line – against the lab on localhost
# (docs/demo/lab_server.py), not against public proxies.

Output docs/demo/checks.gif

Set Shell bash
Set FontSize 16
Set Width 1500
Set Height 600
Set PlaybackSpeed 0.85
Set Padding 24
Set TypingSpeed 28ms
Set Theme "Catppuccin Mocha"

Hide
Type "source .venv/bin/activate && export PATH=$PWD/docs/demo:$PATH PS1='$ '" Enter
Type "python docs/demo/lab_server.py > /dev/null 2>&1 &" Enter
Sleep 2s
Type "clear" Enter
Show

Type "# Local demo: six simulated proxies on localhost. Not a measurement of public proxies." Enter
Sleep 2s
Type "proxy-scraper --pick 2 --verify --https-only" Enter
Sleep 6s
Type "proxy-scraper --diagnose 127.0.0.1:8083" Enter
Sleep 9s
Type "clear" Enter
Type "proxy-scraper --diagnose 127.0.0.1:8085 --json | jq '.verdict, .checks.https'" Enter
Sleep 7s

Hide
Type "kill %1" Enter
Sleep 500ms
