"""Tab-Vervollständigung für bash, zsh und fish – direkt aus dem argparse-Parser erzeugt.

So kann das Skript nie veralten: jede neue Option taucht automatisch auf, mit ihren Auswahlwerten
(--types, --rotate, …) und dem Anfang ihres Hilfetexts als Beschreibung (zsh, fish).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

SHELLS = ("bash", "zsh", "fish")
PROG = "proxy-scraper"
FILE_OPTIONS = {"--recheck": ("live",), "--output": ()}  # Wert ist ein Dateipfad (oder eines dieser Wörter)
GERMAN = {"help": "Hilfe anzeigen", "version": "Version anzeigen"}  # die Texte von argparse selbst sind englisch


@dataclass
class Option:
    flags: List[str]
    help: str
    takes_value: bool
    optional_value: bool  # nargs="?": der Wert darf fehlen (--recheck, --serve)
    choices: Tuple[str, ...]
    is_file: bool
    extra: Tuple[str, ...] = ()  # Wörter, die statt einer Datei gehen (--recheck live)

    @property
    def long(self) -> Optional[str]:
        return next((f for f in self.flags if f.startswith("--")), None)

    @property
    def short(self) -> Optional[str]:
        return next((f for f in self.flags if not f.startswith("--")), None)


def short_help(text: Optional[str], width: int = 60) -> str:
    """Nur der Anfang des Hilfetexts: bis zur ersten Klammer, zum Gedankenstrich, Semikolon oder Beispiel."""
    text = re.split(r" \(| – |; |,? z\. B\.", text or "")[0].strip()
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def options(parser: argparse.ArgumentParser) -> List[Option]:
    found = []
    for action in parser._actions:  # argparse bietet keine öffentliche Liste
        if not action.option_strings or action.help == argparse.SUPPRESS:
            continue
        takes_value = action.nargs != 0
        found.append(Option(
            flags=list(action.option_strings),
            help=GERMAN.get(action.dest) or short_help(action.help),
            takes_value=takes_value,
            optional_value=action.nargs == "?",
            choices=tuple(str(c) for c in action.choices or ()),
            is_file=takes_value and any(f in FILE_OPTIONS for f in action.option_strings),
            extra=next((FILE_OPTIONS[f] for f in action.option_strings if f in FILE_OPTIONS), ()),
        ))
    return found


def bash(opts: List[Option]) -> str:
    words = " ".join(f for o in opts for f in o.flags)
    cases = []
    for o in opts:
        if not o.takes_value or o.optional_value and not o.is_file:
            continue
        pattern = "|".join(o.flags)
        if o.choices:
            cases.append(f'        {pattern}) COMPREPLY=($(compgen -W "{" ".join(o.choices)}" -- "$cur")); return ;;')
        elif o.is_file:
            extra = f'$(compgen -W "{" ".join(o.extra)}" -- "$cur") ' if o.extra else ""
            cases.append(f'        {pattern}) COMPREPLY=({extra}$(compgen -f -- "$cur")); return ;;')
        else:
            cases.append(f"        {pattern}) return ;;  # freier Wert")
    return f"""# bash-Vervollständigung für {PROG}
# einbinden: eval "$({PROG} --completion bash)"  (z. B. in ~/.bashrc)
_proxy_scraper() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}" prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    COMPREPLY=()
    case "$prev" in
{chr(10).join(cases)}
    esac
    COMPREPLY=($(compgen -W "{words}" -- "$cur"))
}}
complete -F _proxy_scraper {PROG}
"""


def _zsh_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace("[", "\\[").replace("]", "\\]")


def zsh(opts: List[Option]) -> str:
    specs = []
    for o in opts:
        repeat = "*" if o.long in ("--target", "--types") else ""
        # '(-c --concurrency)'{-c,--concurrency}'[…]' – die Klammer {} darf nicht in Anführungszeichen stehen
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
            spec += f"{colon}{o.long.lstrip('-')}:{action}"
        specs.append(f"  '{spec}'")
    body = " \\\n".join(specs)
    return f"""#compdef {PROG}
# zsh-Vervollständigung für {PROG}
# einbinden: eval "$({PROG} --completion zsh)"  (in ~/.zshrc, nach compinit)
_proxy_scraper() {{
  _arguments -s \\
{body}
}}
compdef _proxy_scraper {PROG}
"""


def _fish_quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def fish(opts: List[Option]) -> str:
    lines = [f"# fish-Vervollständigung für {PROG}",
             f"# einbinden: {PROG} --completion fish > ~/.config/fish/completions/{PROG}.fish",
             f"complete -c {PROG} -f"]
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
    return "\n".join(lines) + "\n"


def script(parser: argparse.ArgumentParser, shell: str) -> str:
    return {"bash": bash, "zsh": zsh, "fish": fish}[shell](options(parser))


class CompletionAction(argparse.Action):
    """--completion SHELL: Skript ausgeben und beenden – wie --version, noch bevor irgendetwas startet."""

    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, choices=SHELLS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        sys.stdout.write(script(parser, values))
        parser.exit()
