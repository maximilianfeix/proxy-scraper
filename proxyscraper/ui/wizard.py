"""Setup wizard: pick with the arrow keys at startup which proxies to look for.

The logic is deliberately separate from the keyboard – `Wizard.handle()` receives key names
("up", "space", "enter" …), `Wizard` itself is a rich renderable. That way the whole flow can be
tested without a terminal.
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
    ("DE", "Germany"), ("AT", "Austria"), ("CH", "Switzerland"), ("NL", "Netherlands"),
    ("FR", "France"), ("GB", "United Kingdom"), ("PL", "Poland"), ("SE", "Sweden"),
    ("IT", "Italy"), ("ES", "Spain"), ("US", "USA"), ("CA", "Canada"), ("BR", "Brazil"),
    ("JP", "Japan"), ("SG", "Singapore"), ("HK", "Hong Kong"), ("KR", "South Korea"), ("IN", "India"),
    ("ID", "Indonesia"), ("TH", "Thailand"), ("VN", "Vietnam"), ("TR", "Turkey"),
    ("RU", "Russia"), ("UA", "Ukraine"),
)
TYPE_HINTS = {
    "http": "web proxies, HTTPS via CONNECT",
    "socks4": "older, TCP only, no DNS through the proxy",
    "socks5": "universal – browsers, apps, games",
}
ANON_TEXT = {"": "any", "anonymous": "at least anonymous", "elite": "elite only"}


@dataclass
class Option:
    label: str
    hint: str = ""
    value: Any = None

    @property
    def search_text(self) -> str:
        """Text for jumping by letter: without leading flags/symbols, accents as base letters (Ö -> o)."""
        text = re.sub(r"^\W+", "", self.label)
        return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

class Step:
    title = ""
    subtitle = ""
    keys_help = "↑↓ select · Enter next · Esc back · q quit"

    def load(self, opts: RunOptions) -> None:
        """Preselect the current setting."""

    def apply(self, opts: RunOptions) -> None:
        """Apply the selection to the settings."""

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
            # typing jumps to the next entry starting with that letter
            order = list(range(self.cursor + 1, n)) + list(range(self.cursor + 1))
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
        # fixed widths for arrow, number, marker and label – when space runs out, rich only shortens the hint
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
            grid.add_row("", *pad, "", Text(f"↑ {window.start} more", style=MUTED), "")
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
            grid.add_row("", *pad, "", Text(f"↓ {rest} more", style=MUTED), "")
        return grid

    def body(self) -> RenderableType:
        parts: List[RenderableType] = [self._rows(self._marker)]
        if self.message:
            parts.append(Text(f"\n{self.message}", style=WARN))
        return Group(*parts)

    def _marker(self, i: int) -> Text:
        raise NotImplementedError


class SelectStep(_ListStep):
    """Single choice – numbers 1–9 pick directly."""

    numbered = True

    def __init__(self, title, subtitle, options, read: Optional[Callable[[RunOptions], Any]] = None,
                 write: Optional[Callable[[RunOptions, Any], None]] = None):
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
    """Multiple choice with the space bar."""

    keys_help = "↑↓ select · Space on/off · a all/none · Enter next · Esc back"

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
                self.message = f"Please select at least {self.min_selected} (space bar)."
                return None
            return NEXT
        else:
            self._move(key)
        return None

    def _marker(self, i: int) -> Text:
        return Text("[✔]", style=f"bold {GOOD}") if i in self.checked else Text("[ ]", style=MUTED)

    def body(self) -> RenderableType:
        chosen = [self.options[i].value for i in sorted(self.checked)]
        status = Text(f"{len(chosen)} selected", style=GOOD) if chosen else Text(self.empty_hint, style=MUTED)
        return Group(super().body(), Text(""), status)


class TargetStep(SelectStep):
    """Pick a target site. Targets from the command line that aren't suggestions stay available as an option."""

    def __init__(self):
        super().__init__(
            "Does a specific site have to work?",
            "Many proxies can't reach Google, Discord and the like – this actually tries it.",
            [Option("No", "any site is fine", [])]
            + [Option(name, target_label(url), [url]) for name, url in SUGGESTIONS],
            read=lambda o: o.filters.targets, write=lambda o, v: setattr(o.filters, "targets", list(v)),
        )
        self._fixed = len(self.options)

    def load(self, opts: RunOptions) -> None:
        del self.options[self._fixed:]
        current = list(opts.filters.targets)
        if current and all(o.value != current for o in self.options):
            self.options.append(Option("As given", ", ".join(target_label(u) for u in current), current))
        super().load(opts)


class ServeStep(SelectStep):
    """Proxy server afterwards? A custom port from the command line (-i --serve 9000) stays selectable."""

    def __init__(self):
        super().__init__(
            "Serve them as a proxy server afterwards?",
            "A local proxy that sends every connection through a different proxy that was found.",
            [Option("No", "just the result files", 0),
             Option(f"Yes, on port {DEFAULT_SERVE_PORT}", f"http://127.0.0.1:{DEFAULT_SERVE_PORT} – runs until Ctrl+C",
                    DEFAULT_SERVE_PORT)],
            read=lambda o: o.serve, write=lambda o, v: setattr(o, "serve", v),
        )

    def load(self, opts: RunOptions) -> None:
        del self.options[2:]
        if opts.serve not in (0, DEFAULT_SERVE_PORT):
            self.options.append(Option(f"Yes, on port {opts.serve}", "as given", opts.serve))
        super().load(opts)


class SummaryStep(SelectStep):
    START, ADJUST, CANCEL = "start", "adjust", "cancel"

    def __init__(self):
        super().__init__("All set?", "This is what will be searched – Enter starts.", [
            Option("Start the search", "", self.START),
            Option("Adjust …", "change every setting one by one", self.ADJUST),
            Option("Cancel", "", self.CANCEL),
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
        return Group(grid, Text(""), *warnings, Text("Start the same directly:", style=MUTED), command,
                     Text(""), self._rows(self._marker))


# --------------------------------------------------------------------------- #
# Describing the settings
# --------------------------------------------------------------------------- #

def describe(opts: RunOptions) -> List[tuple]:
    f = opts.filters
    if opts.recheck is not None:
        rows = [("Mode", Text("recheck the last hits + history", style="bold"))]
    else:
        rows = [("Mode", Text("collect and check all sources", style="bold"))]
    types = Text()
    for i, t in enumerate(t for t in PROXY_TYPES if t in opts.types):
        if i:
            types.append(" · ", style=MUTED)
        types.append(t, style=f"bold {TYPE_STYLE[t]}")
    rows.append(("Protocols", types))
    rows.append(("Countries", Text("  ".join(f"{flag(c)} {c}" for c in sorted(f.countries)) if f.countries else "all")))
    rows.append(("Anonymity", Text(ANON_TEXT[f.min_anonymity])))
    rows.append(("HTTPS", Text("HTTPS-capable only", style=GOOD) if f.https_only else Text("any")))
    rows.append(("Target site", Text(", ".join(target_label(u) for u in f.targets), style=ACCENT) if f.targets
                 else Text("any")))
    rows.append(("Latency", Text(f"under {fmt_seconds(f.max_latency)}") if f.max_latency else Text("any")))
    rows.append(("Amount", Text(f"stops at {fmt(opts.want)}") if opts.want else Text("as many as possible")))
    if opts.serve:
        rows.append(("Afterwards", Text(f"proxy server on 127.0.0.1:{opts.serve}", style=f"bold {ACCENT}")))
    rows.append(("Checks", Text("thorough – with HTTPS test") if opts.details
                 else Text("fast – without HTTPS test")))
    return rows


def warnings_for(opts: RunOptions) -> List[str]:
    out = []
    f = opts.filters
    if opts.fast and f.needs_details:
        out.append("The HTTPS filter needs the HTTPS test – thorough checks stay on.")
    if "socks4" in opts.types and len(opts.types) == 1 and f.https_only:
        out.append("SOCKS4 can tunnel HTTPS, but usually finds only a few matching proxies.")
    return out


def short_description(opts: RunOptions) -> str:
    """One-line description for "Same as last time", e.g. "socks5 · DE,AT · HTTPS only · 50 proxies"."""
    f = opts.filters
    parts = [" + ".join(opts.types) if opts.types != list(PROXY_TYPES) else "all protocols"]
    if opts.recheck is not None:
        parts.insert(0, "Recheck")
    if f.countries:
        parts.append(",".join(sorted(f.countries)))
    if f.https_only:
        parts.append("HTTPS only")
    if f.min_anonymity:
        parts.append(ANON_TEXT[f.min_anonymity])
    if f.max_latency:
        parts.append(f"< {fmt_seconds(f.max_latency)}")
    if f.targets:
        parts.append("→ " + ", ".join(target_label(u) for u in f.targets))
    if opts.want:
        parts.append(f"{fmt(opts.want)} proxies")
    if opts.fast:
        parts.append("fast")
    return " · ".join(parts)


def fmt_seconds(ms: int) -> str:
    return f"{ms / 1000:g} s"


# --------------------------------------------------------------------------- #
# Wizard
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
            "Which protocols?", "Pick several with the space bar.",
            [Option(t.upper(), TYPE_HINTS[t], t) for t in PROXY_TYPES],
            read=lambda o: set(o.types), write=_set_types, min_selected=1,
        ),
        MultiStep(
            "From which countries?", "Typing jumps to the letter. Nothing selected = all countries.",
            [Option(f"{flag(cc)} {name}", cc, cc) for cc, name in COUNTRIES],
            read=lambda o: o.filters.countries, write=_set_countries, empty_hint="no selection = all countries",
        ),
        SelectStep(
            "How anonymous?", "SOCKS proxies are always elite – they don't touch your traffic.",
            [Option("Any", "also transparent proxies that pass on your IP", ""),
             Option("At least anonymous", "hide your IP, but identify themselves as a proxy", "anonymous"),
             Option("Elite only", "not recognizable as a proxy", "elite")],
            read=lambda o: o.filters.min_anonymity, write=_set_filter("min_anonymity"),
        ),
        SelectStep(
            "Do you need HTTPS?", "Needed for almost every website – the proxy has to tunnel encrypted connections.",
            [Option("Any", "", False), Option("HTTPS-capable only", "checked with a real TLS handshake", True)],
            read=lambda o: o.filters.https_only, write=_set_filter("https_only"),
        ),
        TargetStep(),
        SelectStep(
            "How fast?", "Slow proxies aren't even checked to the end.",
            [Option("Any", "", 0), Option("Under 0.5 s", "very strict", 500), Option("Under 1 s", "snappy", 1000),
             Option("Under 2 s", "good compromise", 2000), Option("Under 5 s", "almost all", 5000)],
            read=lambda o: o.filters.max_latency, write=_set_filter("max_latency"),
        ),
        SelectStep(
            "How many?", "The search stops as soon as enough matching proxies are found.",
            [Option("As many as possible", "checks every candidate", 0), Option("10", "", 10), Option("25", "", 25),
             Option("50", "", 50), Option("100", "", 100), Option("500", "", 500)],
            read=lambda o: o.want, write=lambda o, v: setattr(o, "want", v),
        ),
        ServeStep(),
        SelectStep(
            "How thorough?", "Anonymity and country are always included – the HTTPS test costs a TLS connection.",
            [Option("Thorough", "with an HTTPS test for every hit", False),
             Option("Fast", "without HTTPS test (--fast)", True)],
            read=lambda o: o.fast, write=lambda o, v: setattr(o, "fast", v),
        ),
    ]


class Wizard:
    """State machine of the wizard. `result` is set when finished, `cancelled` when aborted."""

    CUSTOM, LAST = "custom", "last"

    def __init__(self, initial: RunOptions, last: Optional[RunOptions] = None, can_recheck: bool = False):
        self.initial = initial
        self.last = last
        self.opts = copy.deepcopy(initial)
        self.custom = custom_steps()
        self.summary = SummaryStep()
        self.start = SelectStep("What are you looking for?", "Quick pick – or set everything yourself.",
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
        """Preset = starting values + only what the preset itself sets.

        That way options from the command line (e.g. -i --country DE -c 500) are kept
        as long as the preset doesn't explicitly change them.
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
            Option("Find everything", "all protocols – maximum yield", everything),
            Option("Browsing & web", "HTTP + SOCKS5, HTTPS-capable, at least anonymous, under 3 s", self._preset(
                types=["http", "socks5"], https_only=True, min_anonymity="anonymous", max_latency=3000)),
            Option("Maximum anonymity", "elite SOCKS5 with HTTPS only – so the operator can't read along", self._preset(
                types=["socks5"], https_only=True, min_anonymity="elite")),
            Option("Fast & stable", "only proxies under 1 s latency", self._preset(max_latency=1000)),
            Option("A few right now", "stops after 25 hits", self._preset(want=25)),
        ]
        if can_recheck:
            presets.append(Option("Recheck the last hits", "no collecting – takes only seconds",
                                  self._preset(recheck="")))
            quick_server = self._preset(recheck="")
            quick_server.serve = DEFAULT_SERVE_PORT
            presets.append(Option("Proxy server right away", f"recheck the last hits, then serve them on "
                                  f":{DEFAULT_SERVE_PORT}", quick_server))
        # only offer it if it differs from "Find everything" – otherwise the same thing shows up twice
        if self.last is not None and self.last != everything:
            presets.append(Option("Same as last time", short_description(self.last), self.LAST))
        presets.append(Option("Custom …", "set everything step by step", self.CUSTOM))
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
                # start with what was already on the command line (e.g. -i --country DE)
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

    # ------------------------------------------------------------------ rendering

    def _position(self) -> Text:
        if self.step is self.start:
            return Text("Start", style=MUTED)
        if self.step is self.summary:
            return Text("Summary", style=MUTED)
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
            title=Text(" Setup ", style=f"bold {ACCENT}"),  # the banner above already says what this is
            title_align="left",
        )
        help_line = Text("  " + step.keys_help, style=MUTED)
        if step is self.start or step is self.summary:
            help_line = Text("  ↑↓ select · Enter confirm · number = pick directly · Esc back · q quit",
                             style=MUTED)
        return Group(panel, help_line)


def run_wizard(initial: RunOptions, last: Optional[RunOptions], can_recheck: bool, console) -> Optional[RunOptions]:
    """Shows the wizard in the terminal; None when cancelled."""
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
