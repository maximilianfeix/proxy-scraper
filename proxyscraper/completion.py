"""Tab completion for bash, zsh and fish – generated straight from the argparse parser.

That way the script can never go stale: every new option shows up automatically, with its choices
(--types, --rotate, …) and the start of its help text as the description (zsh, fish).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

SHELLS = ("bash", "zsh", "fish")
PROG = "proxy-scraper"
FILE_OPTIONS = {"--recheck": ("live",), "--output": ()}  # the value is a file path (or one of these words)
OWN_HELP = {"help": "show help", "version": "show the version"}  # shorter than argparse's own texts


@dataclass
class Option:
    flags: List[str]
    help: str
    takes_value: bool
    optional_value: bool  # nargs="?": the value may be missing (--recheck, --serve)
    choices: Tuple[str, ...]
    is_file: bool
    extra: Tuple[str, ...] = ()  # words that work instead of a file (--recheck live)
    multi: bool = False  # nargs="+": several values in a row (--types http socks5)

    @property
    def long(self) -> Optional[str]:
        return next((f for f in self.flags if f.startswith("--")), None)

    @property
    def short(self) -> Optional[str]:
        return next((f for f in self.flags if not f.startswith("--")), None)


def short_help(text: Optional[str], width: int = 60) -> str:
    """Only the start of the help text: up to the first parenthesis, dash, semicolon or example."""
    text = re.split(r" \(| – |; |,? e\.g\.", text or "")[0].strip()
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def options(parser: argparse.ArgumentParser) -> List[Option]:
    found = []
    for action in parser._actions:  # argparse offers no public list
        if not action.option_strings or action.help == argparse.SUPPRESS:
            continue
        takes_value = action.nargs != 0
        found.append(Option(
            flags=list(action.option_strings),
            help=OWN_HELP.get(action.dest) or short_help(action.help),
            takes_value=takes_value,
            optional_value=action.nargs == "?",
            choices=tuple(str(c) for c in action.choices or ()),
            is_file=takes_value and any(f in FILE_OPTIONS for f in action.option_strings),
            extra=next((FILE_OPTIONS[f] for f in action.option_strings if f in FILE_OPTIONS), ()),
            multi=action.nargs in ("+", "*"),
        ))
    return found


def bash(opts: List[Option]) -> str:
    words = " ".join(f for o in opts for f in o.flags)
    cases, multi = [], []
    for o in opts:
        if not o.takes_value or o.optional_value and not o.is_file:
            continue
        pattern = "|".join(o.flags)
        if o.choices:
            reply = f'COMPREPLY=($(compgen -W "{" ".join(o.choices)}" -- "$cur")); return ;;'
            cases.append(f"        {pattern}) {reply}")
            if o.multi:
                multi.append(f"                {pattern}) {reply}")
        elif o.is_file:
            # line by line, so "file with spaces" stays one entry
            extra = f'$(compgen -W "{" ".join(o.extra)}" -- "$cur") ' if o.extra else ""
            cases.append(f"        {pattern}) compopt -o filenames 2>/dev/null; local IFS=$'\\n'; "
                         f'COMPREPLY=({extra}$(compgen -f -- "$cur")); return ;;')
        else:
            cases.append(f"        {pattern}) return ;;  # freier Wert")
    return f"""# bash completion for {PROG}
# enable: eval "$({PROG} --completion bash)"  (e.g. in ~/.bashrc)
_proxy_scraper() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}" prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    COMPREPLY=()
    case "$prev" in
{chr(10).join(cases)}
    esac
    # more values for options like --types http socks5: the last option before counts
    if [[ "$cur" != -* ]]; then
        local i
        for ((i = COMP_CWORD - 1; i > 0; i--)); do
            [[ "${{COMP_WORDS[i]}}" == -* ]] || continue
            case "${{COMP_WORDS[i]}}" in
{chr(10).join(multi)}
            esac
            break
        done
    fi
    COMPREPLY=($(compgen -W "{words}" -- "$cur"))
}}
complete -F _proxy_scraper {PROG}
"""


def _zsh_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace("[", "\\[").replace("]", "\\]")


def zsh(opts: List[Option]) -> str:
    specs = []
    for o in opts:
        repeat = "*" if o.long == "--target" else ""
        # '(-c --concurrency)'{-c,--concurrency}'[…]' – the braces {} must not be inside quotes
        spec = f"({' '.join(o.flags)}){repeat}'{{{','.join(o.flags)}}}'" if len(o.flags) > 1 else repeat + o.flags[0]
        spec += f"[{_zsh_escape(o.help)}]"
        if o.takes_value:
            colon = "::" if o.optional_value else ":"
            if o.choices:
                action = f"({' '.join(o.choices)})"
            elif o.is_file:
                action = "{_files; compadd " + " ".join(o.extra) + "}" if o.extra else "_files"
            else:
                action = " "
            if o.multi:
                colon += "*-*:"  # every word up to the next option belongs to it
            spec += f"{colon}{o.long.lstrip('-')}:{action}"
        specs.append(f"  '{spec}'")
    body = " \\\n".join(specs)
    return f"""#compdef {PROG}
# zsh completion for {PROG}
# enable: eval "$({PROG} --completion zsh)"  (in ~/.zshrc, after compinit)
_proxy_scraper() {{
  _arguments -s \\
{body}
}}
compdef _proxy_scraper {PROG}
"""


def _fish_quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def fish(opts: List[Option]) -> str:
    lines = [f"# fish completion for {PROG}",
             f"# enable: {PROG} --completion fish > ~/.config/fish/completions/{PROG}.fish",
             f"complete -c {PROG} -f",
             "# is the last option before the cursor $argv[1]? (for several values like --types http socks5)",
             "function __proxy_scraper_after",
             "    set -l tokens (commandline -opc)",
             "    test (count $tokens) -gt 1; or return 1",
             "    for token in $tokens[-1..2]",
             "        string match -q -- '-*' $token; or continue",
             "        test $token = $argv[1]; return",
             "    end",
             "    return 1",
             "end"]
    for o in opts:
        parts = [f"complete -c {PROG}"]
        if o.long:
            parts.append(f"-l {o.long[2:]}")
        if o.short:
            parts.append(f"-s {o.short[1:]}")
        if o.help:
            parts.append(f"-d {_fish_quote(o.help)}")
        if o.choices:
            parts.append(f"-xa {_fish_quote(' '.join(o.choices))}")
        elif o.is_file:
            parts.append("-rF" + (f" -a {_fish_quote(' '.join(o.extra))}" if o.extra else ""))
        elif o.takes_value and not o.optional_value:
            parts.append("-x")
        lines.append(" ".join(parts))
        if o.multi and o.choices:
            lines.append(f"complete -c {PROG} -n {_fish_quote('__proxy_scraper_after ' + o.long)} "
                         f"-xa {_fish_quote(' '.join(o.choices))}")
    return "\n".join(lines) + "\n"


def script(parser: argparse.ArgumentParser, shell: str) -> str:
    return {"bash": bash, "zsh": zsh, "fish": fish}[shell](options(parser))


class CompletionAction(argparse.Action):
    """--completion SHELL: print the script and exit – like --version, before anything starts."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, choices=SHELLS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        sys.stdout.write(script(parser, values))
        parser.exit()
