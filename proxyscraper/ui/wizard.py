"""Einrichtungsassistent: Beim Start per Pfeiltasten auswählen, welche Proxys gesucht werden.

Die Logik ist bewusst von der Tastatur getrennt – `Wizard.handle()` bekommt Tastennamen
("up", "space", "enter" …), `Wizard` selbst ist ein rich-Renderable. Dadurch lässt sich der
komplette Ablauf ohne Terminal testen.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Sequence, Set

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..geo import flag
from ..options import DEFAULT_SERVE_PORT, RunOptions
from ..parsing import PROXY_TYPES
from ..targets import SUGGESTIONS, target_label
from .widgets import ACCENT, GOOD, MUTED, TYPE_STYLE, WARN, fmt

NEXT, BACK = "next", "back"
VISIBLE_ROWS = 9

COUNTRIES = (
    ("DE", "Deutschland"), ("AT", "Österreich"), ("CH", "Schweiz"), ("NL", "Niederlande"),
    ("FR", "Frankreich"), ("GB", "Großbritannien"), ("PL", "Polen"), ("SE", "Schweden"),
    ("IT", "Italien"), ("ES", "Spanien"), ("US", "USA"), ("CA", "Kanada"), ("BR", "Brasilien"),
    ("JP", "Japan"), ("SG", "Singapur"), ("HK", "Hongkong"), ("KR", "Südkorea"), ("IN", "Indien"),
    ("ID", "Indonesien"), ("TH", "Thailand"), ("VN", "Vietnam"), ("TR", "Türkei"),
    ("RU", "Russland"), ("UA", "Ukraine"),
)
TYPE_HINTS = {
    "http": "Web-Proxys, HTTPS über CONNECT",
    "socks4": "älter, nur TCP, kein DNS über den Proxy",
    "socks5": "universell – Browser, Apps, Spiele",
}
ANON_TEXT = {"": "egal", "anonymous": "mindestens anonym", "elite": "nur Elite"}


@dataclass
class Option:
    label: str
    hint: str = ""
    value: Any = None

    @property
    def search_text(self) -> str:
        """Text für den Buchstabensprung: ohne Flaggen/Symbole davor, Umlaute wie Grundbuchstaben (Ö -> o)."""
        text = re.sub(r"^\W+", "", self.label)
        return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


# --------------------------------------------------------------------------- #
# Schritte
# --------------------------------------------------------------------------- #

class Step:
    title = ""
    subtitle = ""
    keys_help = "↑↓ auswählen · Enter weiter · Esc zurück · q beenden"

    def load(self, opts: RunOptions) -> None:
        """Aktuelle Einstellung vorauswählen."""

    def apply(self, opts: RunOptions) -> None:
        """Auswahl in die Einstellungen übernehmen."""

    def handle(self, key: str) -> Optional[str]:
        raise NotImplementedError

    def body(self) -> RenderableType:
        raise NotImplementedError


class _ListStep(Step):
    def __init__(self, title: str, subtitle: str, options: Sequence[Option]):
        self.title, self.subtitle = title, subtitle
        self.options = list(options)
        self.cursor = 0
        self.message = ""

    def _move(self, key: str) -> bool:
        n = len(self.options)
        if key in ("up", "k"):
            self.cursor = (self.cursor - 1) % n
        elif key in ("down", "j"):
            self.cursor = (self.cursor + 1) % n
        elif key in ("home", "pageup"):
            self.cursor = 0
        elif key in ("end", "pagedown"):
            self.cursor = n - 1
        elif len(key) == 1 and key.isalpha() and key not in "jkq":
            # Tippen springt zum nächsten Eintrag mit diesem Anfangsbuchstaben
            order = list(range(self.cursor + 1, n)) + list(range(0, self.cursor + 1))
            hit = next((i for i in order if self.options[i].search_text.startswith(key.lower())), None)
            if hit is None:
                return False
            self.cursor = hit
        else:
            return False
        self.message = ""
        return True

    def _window(self) -> range:
        n = len(self.options)
        if n <= VISIBLE_ROWS:
            return range(n)
        start = min(max(self.cursor - VISIBLE_ROWS // 2, 0), n - VISIBLE_ROWS)
        return range(start, start + VISIBLE_ROWS)

    numbered = False

    def _rows(self, marker: Callable[[int], Text]) -> Table:
        numbers = self.numbered and len(self.options) <= 9
        # Feste Breiten für Pfeil, Nummer, Markierung und Label – wird es eng, kürzt rich nur den Hinweis
        grid = Table.grid(padding=(0, 1), expand=True)
        grid.add_column(width=1)
        if numbers:
            grid.add_column(width=1, style=MUTED)
        grid.add_column(width=marker(0).cell_len)
        grid.add_column(min_width=max(len(o.label) for o in self.options), no_wrap=True)
        grid.add_column(style=MUTED, overflow="ellipsis", no_wrap=True, ratio=1)
        window = self._window()
        pad = [""] if numbers else []
        if window.start > 0:
            grid.add_row("", *pad, "", Text(f"↑ {window.start} weitere", style=MUTED), "")
        for i in window:
            opt = self.options[i]
            active = i == self.cursor
            grid.add_row(
                Text("❯", style=f"bold {ACCENT}") if active else "",
                *([str(i + 1)] if numbers else []),
                marker(i),
                Text(opt.label, style=f"bold {ACCENT}" if active else ""),
                opt.hint,
            )
        rest = len(self.options) - window.stop
        if rest > 0:
            grid.add_row("", *pad, "", Text(f"↓ {rest} weitere", style=MUTED), "")
        return grid

    def body(self) -> RenderableType:
        parts: List[RenderableType] = [self._rows(self._marker)]
        if self.message:
            parts.append(Text(f"\n{self.message}", style=WARN))
        return Group(*parts)

    def _marker(self, i: int) -> Text:
        raise NotImplementedError


class SelectStep(_ListStep):
    """Einfachauswahl – Zahlen 1–9 wählen direkt."""

    numbered = True

    def __init__(self, title, subtitle, options, read: Callable[[RunOptions], Any] = None,
                 write: Callable[[RunOptions, Any], None] = None):
        super().__init__(title, subtitle, options)
        self.read, self.write = read, write

    @property
    def value(self) -> Any:
        return self.options[self.cursor].value

    def load(self, opts: RunOptions) -> None:
        if self.read:
            current = self.read(opts)
            self.cursor = next((i for i, o in enumerate(self.options) if o.value == current), 0)

    def apply(self, opts: RunOptions) -> None:
        if self.write:
            self.write(opts, self.value)

    def handle(self, key: str) -> Optional[str]:
        if key == "enter":
            return NEXT
        if key.isdigit() and 0 < int(key) <= len(self.options):
            self.cursor = int(key) - 1
            return NEXT
        self._move(key)
        return None

    def _marker(self, i: int) -> Text:
        return Text("◉", style=f"bold {ACCENT}") if i == self.cursor else Text("○", style=MUTED)


class MultiStep(_ListStep):
    """Mehrfachauswahl mit Leertaste."""

    keys_help = "↑↓ auswählen · Leertaste an/aus · a alle/keine · Enter weiter · Esc zurück"

    def __init__(self, title, subtitle, options, read: Callable[[RunOptions], Set],
                 write: Callable[[RunOptions, List], None], min_selected: int = 0, empty_hint: str = ""):
        super().__init__(title, subtitle, options)
        self.read, self.write = read, write
        self.min_selected = min_selected
        self.empty_hint = empty_hint
        self.checked: Set[int] = set()

    def load(self, opts: RunOptions) -> None:
        current = self.read(opts)
        self.checked = {i for i, o in enumerate(self.options) if o.value in current}

    def apply(self, opts: RunOptions) -> None:
        self.write(opts, [o.value for i, o in enumerate(self.options) if i in self.checked])

    def handle(self, key: str) -> Optional[str]:
        if key == "space":
            self.checked ^= {self.cursor}
            self.message = ""
        elif key == "a":
            self.checked = set() if len(self.checked) == len(self.options) else set(range(len(self.options)))
            self.message = ""
        elif key == "enter":
            if len(self.checked) < self.min_selected:
                self.message = f"Bitte mindestens {self.min_selected} auswählen (Leertaste)."
                return None
            return NEXT
        else:
            self._move(key)
        return None

    def _marker(self, i: int) -> Text:
        return Text("[✔]", style=f"bold {GOOD}") if i in self.checked else Text("[ ]", style=MUTED)

    def body(self) -> RenderableType:
        chosen = [self.options[i].value for i in sorted(self.checked)]
        status = Text(f"{len(chosen)} ausgewählt", style=GOOD) if chosen else Text(self.empty_hint, style=MUTED)
        return Group(super().body(), Text(""), status)


class TargetStep(SelectStep):
    """Zielseite wählen. Ziele von der Kommandozeile, die keine Vorschläge sind, bleiben als Option erhalten."""

    def __init__(self):
        super().__init__(
            "Muss eine bestimmte Seite gehen?",
            "Viele Proxys kommen nicht auf Google, Discord & Co. – hier wird es echt ausprobiert.",
            [Option("Nein", "irgendeine Seite reicht", [])]
            + [Option(name, target_label(url), [url]) for name, url in SUGGESTIONS],
            read=lambda o: o.filters.targets, write=lambda o, v: setattr(o.filters, "targets", list(v)),
        )
        self._fixed = len(self.options)

    def load(self, opts: RunOptions) -> None:
        del self.options[self._fixed:]
        current = list(opts.filters.targets)
        if current and all(o.value != current for o in self.options):
            self.options.append(Option("Wie angegeben", ", ".join(target_label(u) for u in current), current))
        super().load(opts)


class SummaryStep(SelectStep):
    START, ADJUST, CANCEL = "start", "adjust", "cancel"

    def __init__(self):
        super().__init__("Alles bereit?", "So wird gesucht – Enter startet.", [
            Option("Suche starten", "", self.START),
            Option("Anpassen …", "jede Einstellung einzeln ändern", self.ADJUST),
            Option("Abbrechen", "", self.CANCEL),
        ])
        self.opts = RunOptions()

    def load(self, opts: RunOptions) -> None:
        self.opts = opts
        self.cursor = 0

    def body(self) -> RenderableType:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=MUTED, no_wrap=True)
        grid.add_column()
        for label, value in describe(self.opts):
            grid.add_row(label, value)
        command = Padding(Text(self.opts.to_command(), style=f"italic {MUTED}"), (0, 0, 0, 2))
        warnings = [Text(f"⚠ {w}", style=WARN) for w in warnings_for(self.opts)]
        return Group(grid, Text(""), *warnings, Text("Dasselbe direkt starten:", style=MUTED), command,
                     Text(""), self._rows(self._marker))


# --------------------------------------------------------------------------- #
# Beschreibung der Einstellungen
# --------------------------------------------------------------------------- #

def describe(opts: RunOptions) -> List[tuple]:
    f = opts.filters
    if opts.recheck is not None:
        rows = [("Modus", Text("letzte Treffer + Verlauf neu prüfen", style="bold"))]
    else:
        rows = [("Modus", Text("alle Quellen sammeln und prüfen", style="bold"))]
    types = Text()
    for i, t in enumerate(t for t in PROXY_TYPES if t in opts.types):
        if i:
            types.append(" · ", style=MUTED)
        types.append(t, style=f"bold {TYPE_STYLE[t]}")
    rows.append(("Protokolle", types))
    rows.append(("Länder", Text("  ".join(f"{flag(c)} {c}" for c in sorted(f.countries)) if f.countries else "alle")))
    rows.append(("Anonymität", Text(ANON_TEXT[f.min_anonymity])))
    rows.append(("HTTPS", Text("nur HTTPS-fähige", style=GOOD) if f.https_only else Text("egal")))
    rows.append(("Zielseite", Text(", ".join(target_label(u) for u in f.targets), style=ACCENT) if f.targets
                 else Text("egal")))
    rows.append(("Latenz", Text(f"unter {fmt_seconds(f.max_latency)}") if f.max_latency else Text("egal")))
    rows.append(("Menge", Text(f"stoppt bei {fmt(opts.want)}") if opts.want else Text("so viele wie möglich")))
    if opts.serve:
        rows.append(("Danach", Text(f"Proxy-Server auf 127.0.0.1:{opts.serve}", style=f"bold {ACCENT}")))
    rows.append(("Prüfung", Text("gründlich – mit HTTPS-Test") if opts.details
                 else Text("schnell – ohne HTTPS-Test")))
    return rows


def warnings_for(opts: RunOptions) -> List[str]:
    out = []
    f = opts.filters
    if opts.fast and f.needs_details:
        out.append("Der HTTPS-Filter braucht den HTTPS-Test – die gründliche Prüfung bleibt an.")
    if "socks4" in opts.types and len(opts.types) == 1 and f.https_only:
        out.append("SOCKS4 kann HTTPS tunneln, findet aber meist nur wenige passende Proxys.")
    return out


def short_description(opts: RunOptions) -> str:
    """Einzeilige Beschreibung für "Wie letztes Mal", z. B. "socks5 · DE,AT · nur HTTPS · 50 Stück"."""
    f = opts.filters
    parts = [" + ".join(opts.types) if opts.types != list(PROXY_TYPES) else "alle Protokolle"]
    if opts.recheck is not None:
        parts.insert(0, "Recheck")
    if f.countries:
        parts.append(",".join(sorted(f.countries)))
    if f.https_only:
        parts.append("nur HTTPS")
    if f.min_anonymity:
        parts.append(ANON_TEXT[f.min_anonymity])
    if f.max_latency:
        parts.append(f"< {fmt_seconds(f.max_latency)}")
    if f.targets:
        parts.append("→ " + ", ".join(target_label(u) for u in f.targets))
    if opts.want:
        parts.append(f"{fmt(opts.want)} Stück")
    if opts.fast:
        parts.append("schnell")
    return " · ".join(parts)


def fmt_seconds(ms: int) -> str:
    return f"{ms / 1000:g} s".replace(".", ",")


# --------------------------------------------------------------------------- #
# Assistent
# --------------------------------------------------------------------------- #

def _set_types(opts: RunOptions, values: List[str]) -> None:
    opts.types = values


def _set_countries(opts: RunOptions, values: List[str]) -> None:
    opts.filters.countries = set(values)


def _set_filter(name: str) -> Callable[[RunOptions, Any], None]:
    return lambda opts, value: setattr(opts.filters, name, value)


def custom_steps() -> List[Step]:
    return [
        MultiStep(
            "Welche Protokolle?", "Mehrfachauswahl mit der Leertaste.",
            [Option(t.upper(), TYPE_HINTS[t], t) for t in PROXY_TYPES],
            read=lambda o: set(o.types), write=_set_types, min_selected=1,
        ),
        MultiStep(
            "Aus welchen Ländern?", "Tippen springt zum Buchstaben. Nichts ausgewählt = alle Länder.",
            [Option(f"{flag(cc)} {name}", cc, cc) for cc, name in COUNTRIES],
            read=lambda o: o.filters.countries, write=_set_countries, empty_hint="keine Auswahl = alle Länder",
        ),
        SelectStep(
            "Wie anonym?", "SOCKS-Proxys sind immer Elite – sie fassen deinen Datenverkehr nicht an.",
            [Option("Egal", "auch transparente Proxys, die deine IP weitergeben", ""),
             Option("Mindestens anonym", "verbergen deine IP, geben sich aber als Proxy zu erkennen", "anonymous"),
             Option("Nur Elite", "nicht als Proxy erkennbar", "elite")],
            read=lambda o: o.filters.min_anonymity, write=_set_filter("min_anonymity"),
        ),
        SelectStep(
            "Brauchst du HTTPS?", "Für fast alle Webseiten nötig – der Proxy muss verschlüsselte Verbindungen tunneln.",
            [Option("Egal", "", False), Option("Nur HTTPS-fähige", "wird mit echtem TLS-Handshake geprüft", True)],
            read=lambda o: o.filters.https_only, write=_set_filter("https_only"),
        ),
        TargetStep(),
        SelectStep(
            "Wie schnell?", "Langsame Proxys werden gar nicht erst zu Ende geprüft.",
            [Option("Egal", "", 0), Option("Unter 0,5 s", "sehr streng", 500), Option("Unter 1 s", "flott", 1000),
             Option("Unter 2 s", "guter Kompromiss", 2000), Option("Unter 5 s", "fast alle", 5000)],
            read=lambda o: o.filters.max_latency, write=_set_filter("max_latency"),
        ),
        SelectStep(
            "Wie viele?", "Die Suche stoppt, sobald genug passende Proxys gefunden sind.",
            [Option("So viele wie möglich", "prüft alle Kandidaten", 0), Option("10", "", 10), Option("25", "", 25),
             Option("50", "", 50), Option("100", "", 100), Option("500", "", 500)],
            read=lambda o: o.want, write=lambda o, v: setattr(o, "want", v),
        ),
        SelectStep(
            "Danach als Proxy-Server bereitstellen?",
            "Ein lokaler Proxy, der jede Verbindung über einen anderen gefundenen Proxy schickt.",
            [Option("Nein", "nur die Ergebnisdateien", 0),
             Option(f"Ja, auf Port {DEFAULT_SERVE_PORT}", f"http://127.0.0.1:{DEFAULT_SERVE_PORT} – läuft bis Strg+C",
                    DEFAULT_SERVE_PORT)],
            read=lambda o: o.serve, write=lambda o, v: setattr(o, "serve", v),
        ),
        SelectStep(
            "Wie gründlich prüfen?", "Anonymität und Land gibt es immer – der HTTPS-Test kostet eine TLS-Verbindung.",
            [Option("Gründlich", "mit HTTPS-Test für jeden Treffer", False),
             Option("Schnell", "ohne HTTPS-Test (--fast)", True)],
            read=lambda o: o.fast, write=lambda o, v: setattr(o, "fast", v),
        ),
    ]


class Wizard:
    """Zustandsmaschine des Assistenten. `result` ist nach Abschluss gesetzt, `cancelled` bei Abbruch."""

    CUSTOM, LAST = "custom", "last"

    def __init__(self, initial: RunOptions, last: Optional[RunOptions] = None, can_recheck: bool = False):
        self.initial = initial
        self.last = last
        self.opts = copy.deepcopy(initial)
        self.custom = custom_steps()
        self.summary = SummaryStep()
        self.start = SelectStep("Was suchst du?", "Schnellauswahl – oder alles selbst einstellen.",
                                self._presets(can_recheck))
        self.step: Step = self.start
        self.history: List[Step] = []
        self.result: Optional[RunOptions] = None
        self.cancelled = False

    @property
    def done(self) -> bool:
        return self.result is not None or self.cancelled

    def _preset(self, types: Optional[Sequence[str]] = None, want: Optional[int] = None,
                recheck: Optional[str] = None, **filters) -> RunOptions:
        """Voreinstellung = Startwerte + nur das, was die Voreinstellung selbst festlegt.

        So bleiben Angaben von der Kommandozeile (z. B. -i --country DE -c 500) erhalten,
        solange die Voreinstellung sie nicht ausdrücklich ändert.
        """
        opts = replace(copy.deepcopy(self.initial), recheck=recheck)
        if types is not None:
            opts.types = list(types)
        if want is not None:
            opts.want = want
        for name, value in filters.items():
            setattr(opts.filters, name, value)
        return opts

    def _presets(self, can_recheck: bool) -> List[Option]:
        everything = self._preset(types=PROXY_TYPES)
        presets = [
            Option("Alles finden", "alle Protokolle – maximale Ausbeute", everything),
            Option("Surfen & Web", "HTTP + SOCKS5, HTTPS-fähig, mindestens anonym, unter 3 s", self._preset(
                types=["http", "socks5"], https_only=True, min_anonymity="anonymous", max_latency=3000)),
            Option("Maximal anonym", "nur Elite-SOCKS5 mit HTTPS – sonst liest der Betreiber mit", self._preset(
                types=["socks5"], https_only=True, min_anonymity="elite")),
            Option("Schnell & stabil", "nur Proxys unter 1 s Latenz", self._preset(max_latency=1000)),
            Option("Sofort ein paar", "stoppt nach 25 Treffern", self._preset(want=25)),
        ]
        if can_recheck:
            presets.append(Option("Letzte Treffer neu prüfen", "ohne Sammeln – dauert nur Sekunden",
                                  self._preset(recheck="")))
            quick_server = self._preset(recheck="")
            quick_server.serve = DEFAULT_SERVE_PORT
            presets.append(Option("Sofort als Proxy-Server", f"letzte Treffer prüfen, dann auf :{DEFAULT_SERVE_PORT} "
                                  "bereitstellen", quick_server))
        # Nur anbieten, wenn es sich von "Alles finden" unterscheidet – sonst steht dasselbe zweimal da
        if self.last is not None and self.last != everything:
            presets.append(Option("Wie letztes Mal", short_description(self.last), self.LAST))
        presets.append(Option("Eigene Auswahl …", "Schritt für Schritt alles einstellen", self.CUSTOM))
        return presets

    def _go(self, step: Step) -> None:
        self.history.append(self.step)
        self.step = step
        step.load(self.opts)

    def handle(self, key: str) -> None:
        if key in ("q", "ctrl-c"):
            self.cancelled = True
            return
        if key in ("esc", "left", "backspace"):
            if self.history:
                self.step = self.history.pop()
                self.step.load(self.opts)
            return
        if self.step.handle(key) != NEXT:
            return
        self.step.apply(self.opts)
        self._advance()

    def _advance(self) -> None:
        step = self.step
        if step is self.start:
            choice = self.start.value
            if choice == self.CUSTOM:
                # Mit dem starten, was schon auf der Kommandozeile stand (z. B. -i --country DE)
                self.opts = replace(copy.deepcopy(self.initial), recheck=None)
                self._go(self.custom[0])
            else:
                self.opts = copy.deepcopy(self.last if choice == self.LAST else choice)
                self._go(self.summary)
        elif step is self.summary:
            choice = self.summary.value
            if choice == SummaryStep.START:
                self.result = self.opts
            elif choice == SummaryStep.ADJUST:
                self.opts.recheck = None
                self._go(self.custom[0])
            else:
                self.cancelled = True
        else:
            i = self.custom.index(step)
            self._go(self.custom[i + 1] if i + 1 < len(self.custom) else self.summary)

    # ------------------------------------------------------------------ Darstellung

    def _position(self) -> Text:
        if self.step is self.start:
            return Text("Start", style=MUTED)
        if self.step is self.summary:
            return Text("Übersicht", style=MUTED)
        i = self.custom.index(self.step)
        dots = Text()
        for j in range(len(self.custom)):
            dots.append("●" if j <= i else "○", style=ACCENT if j <= i else MUTED)
        return dots + Text(f"  {i + 1}/{len(self.custom)}", style=MUTED)

    def __rich__(self) -> RenderableType:
        step = self.step
        title = Table.grid(expand=True)
        title.add_column()
        title.add_column(justify="right")
        title.add_row(Text(step.title, style="bold"), self._position())
        content = Group(
            title,
            Text(step.subtitle, style=MUTED),
            Text(""),
            step.body(),
        )
        panel = Panel(
            content, box=box.ROUNDED, border_style=ACCENT, padding=(1, 2),
            title=Text.assemble(("⚡ PROXY SCRAPER", f"bold {ACCENT}"), (" · Einrichtung", MUTED)),
            title_align="left",
        )
        help_line = Text("  " + step.keys_help, style=MUTED)
        if step is self.start or step is self.summary:
            help_line = Text("  ↑↓ auswählen · Enter bestätigen · Zahl = direkt wählen · Esc zurück · q beenden",
                             style=MUTED)
        return Group(panel, help_line)


def run_wizard(initial: RunOptions, last: Optional[RunOptions], can_recheck: bool, console) -> Optional[RunOptions]:
    """Zeigt den Assistenten im Terminal; None bei Abbruch."""
    from rich.live import Live

    from .keys import raw_keys

    wizard = Wizard(initial, last, can_recheck)
    try:
        with raw_keys() as read_key, Live(wizard, console=console, auto_refresh=False, transient=True) as live:
            while not wizard.done:
                wizard.handle(read_key())
                live.refresh()
    except KeyboardInterrupt:
        return None
    return wizard.result
