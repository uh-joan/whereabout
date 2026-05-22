from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll, Vertical
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    ListItem,
    ListView,
    LoadingIndicator,
    Markdown,
    Static,
)
from textual import on, work

_BANNER = (
    "██╗    ██╗ ██╗  ██╗ ███████╗ ██████╗  ███████╗  █████╗  ██████╗   ██████╗  ████████╗\n"
    "██║    ██║ ██║  ██║ ██╔════╝ ██╔══██╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ██╔═══██╗ ╚══██╔══╝\n"
    "██║ █╗ ██║ ███████║ █████╗   ██████╔╝ █████╗   ███████║ ██████╔╝ ██║   ██║    ██║   \n"
    "██║███╗██║ ██╔══██║ ██╔══╝   ██╔══██╗ ██╔══╝   ██╔══██║ ██╔══██╗ ██║   ██║    ██║   \n"
    "╚███╔███╔╝ ██║  ██║ ███████╗ ██║  ██║ ███████╗ ██║  ██║ ██████╔╝ ╚██████╔╝    ██║   \n"
    " ╚══╝╚══╝  ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═╝ ╚═════╝   ╚═════╝    ╚═╝   \n"
    "                   L o n d o n   L i v e   M u s i c"
)

CSS = """
SearchScreen {
    layout: vertical;
}

#banner {
    height: auto;
    text-align: center;
    color: $primary;
    padding: 1 0 0 0;
}

#search-input {
    margin: 0;
}

#query-header {
    height: 1;
    background: $primary;
    color: $text;
    padding: 0 2;
    text-style: bold;
}

#results-table {
    height: 1fr;
    margin: 0 1;
}

#loading {
    height: 1fr;
}

#empty-label {
    height: 1fr;
    content-align: center middle;
    color: $text-muted;
}

DetailScreen {
    background: $surface;
}

#detail-scroll {
    padding: 1 3;
}

ChangeNeighbourhoodScreen {
    align: center middle;
    background: $background 70%;
}

#nb-box {
    width: 52;
    height: auto;
    background: $surface;
    border: thick $primary;
    padding: 1 2;
}

#nb-title {
    text-style: bold;
    margin-bottom: 1;
}

#nb-hint {
    color: $text-muted;
    margin-top: 1;
}

#nb-error {
    color: $error;
    margin-top: 1;
    display: none;
}

#nb-error.visible {
    display: block;
}

GenreFilterScreen {
    align: center middle;
    background: $background 70%;
}

#genre-box {
    width: 44;
    height: auto;
    background: $surface;
    border: thick $primary;
    padding: 1 2;
}

#genre-title {
    text-style: bold;
    margin-bottom: 1;
}

#genre-list {
    height: auto;
    max-height: 15;
    border: none;
}

#genre-hint {
    color: $text-muted;
    margin-top: 1;
}
"""


def _build_genre_options() -> list[tuple[str, str | None]]:
    import json
    from pathlib import Path
    order = json.loads(
        (Path(__file__).parent.parent / "data" / "genre_order.json").read_text()
    )
    opts: list[tuple[str, str | None]] = [("All genres", None)]
    for g in order:
        opts.append((g.title(), g))
    return opts


_GENRE_OPTIONS = _build_genre_options()


class GenreFilterScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def __init__(self, current: str | None = None) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="genre-box"):
            yield Static("Filter by genre", id="genre-title")
            yield ListView(
                *[ListItem(Static(label), id=f"genre-{i}") for i, (label, _) in enumerate(_GENRE_OPTIONS)],
                id="genre-list",
            )
            yield Static("↑↓  ·  Enter to apply  ·  Esc to cancel", id="genre-hint")

    def on_mount(self) -> None:
        lv = self.query_one("#genre-list", ListView)
        lv.focus()
        if self._current:
            for i, (_, val) in enumerate(_GENRE_OPTIONS):
                if val == self._current:
                    lv.index = i
                    break

    @on(ListView.Selected)
    def handle_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("genre-"):
            idx = int(item_id.split("-", 1)[1])
            _, genre = _GENRE_OPTIONS[idx]
            self.dismiss(genre if genre is not None else "")
        else:
            self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class ChangeNeighbourhoodScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def __init__(self, current: str | None = None) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="nb-box"):
            yield Static("Set home neighbourhood", id="nb-title")
            yield Input(
                value=self._current or "",
                placeholder="e.g. Brixton, Hackney, Camden…",
                id="nb-input",
            )
            yield Static("", id="nb-error")
            yield Static("Enter to save  ·  Esc to cancel", id="nb-hint")

    def on_mount(self) -> None:
        self.query_one("#nb-input", Input).focus()

    @on(Input.Submitted)
    def handle_submit(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return
        from whereabout import neighbourhoods as nb
        resolved = nb.resolve_name(value)
        if resolved is None:
            suggestions = nb.did_you_mean(value)
            hint = (
                f"Unknown. Did you mean: {', '.join(suggestions)}?"
                if suggestions
                else "Unknown neighbourhood — check spelling."
            )
            err = self.query_one("#nb-error", Static)
            err.update(hint)
            err.add_class("visible")
            return
        self.dismiss(resolved)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class DetailScreen(Screen):
    BINDINGS = [Binding("escape,b", "dismiss", "Back")]

    def __init__(self, result: dict) -> None:
        super().__init__()
        self._result = result

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="detail-scroll"):
            yield Markdown(self._placeholder(), id="detail-md")
        yield Footer()

    def on_mount(self) -> None:
        self._load_enrichments()

    def _placeholder(self) -> str:
        r = self._result
        artists = ", ".join(r["artists"]) if r["artists"] else r["title"]
        return (
            f"# {r['title']}\n\n"
            f"**{r['date_local']} {r['time_local']}  ·  {r['venue']}**\n\n"
            f"Artists: {artists}\n\n"
            f"*Loading bios…*"
        )

    @work(thread=True)
    def _load_enrichments(self) -> None:
        from whereabout.query.enrich import enrich_artist
        genres = self._result.get("genres", [])
        artists = self._result.get("artists", []) or []

        # If no artists listed, try extracting from the event title
        if not artists:
            extracted = _extract_artist_from_title(self._result.get("title", ""))
            if extracted:
                artists = [extracted]

        enrichments = {}
        for artist in artists:
            try:
                enrichments[artist] = enrich_artist(artist, context_genres=genres)
            except Exception as e:
                enrichments[artist] = {
                    "bio": f"(unavailable: {e})",
                    "genres": [],
                    "notable_for": "",
                }
        self.app.call_from_thread(self._update_content, enrichments)

    def _update_content(self, enrichments: dict) -> None:
        from whereabout.output import detail_view
        self.query_one("#detail-md", Markdown).update(
            detail_view.render_markdown(self._result, enrichments)
        )


import re as _re
_PAREN_SUFFIX_RE = _re.compile(r"\s*[\(\[].*?[\)\]]\s*$", _re.IGNORECASE)
_GENERIC_TITLE_WORDS = {"£", "$", "cocktail", "presents", "session", "residency", "free entry", "feat"}


def _extract_artist_from_title(title: str) -> str | None:
    clean = _PAREN_SUFFIX_RE.sub("", title).strip()
    lower = clean.lower()
    if any(ind in lower for ind in _GENERIC_TITLE_WORDS):
        return None
    if len(clean.split()) > 4:
        return None
    return clean or None


_HOME_MIN_RESULTS = 5
_HOME_RESULT_CAP = 15
_EXPAND_TO = {"tonight": "this week", "this weekend": None, "this week": None}


def _default_timeframe() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    day = datetime.now(ZoneInfo("Europe/London")).weekday()
    return "this weekend" if day in (4, 5) else "tonight"


class SearchScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit"),
        Binding("/,s", "focus_search", "Search"),
        Binding("h", "go_home", "Home"),
        Binding("n", "change_neighbourhood", "Neighbourhood"),
        Binding("g", "filter_genre", "Genre"),
        Binding("f", "toggle_festivals", "Festivals"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, home_neighbourhood: str | None = None) -> None:
        super().__init__()
        self._home_neighbourhood = home_neighbourhood
        self._results: list[dict] = []
        self._all_results: list[dict] = []
        self._last_label: str = ""
        self._last_source: str = ""
        self._auto_timeframe: str | None = None
        self._genre_filter: str | None = None
        self._show_festivals: bool = False

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="banner")
        yield Input(
            placeholder="Search — e.g. 'jazz in brixton tonight'",
            id="search-input",
        )
        yield Static(self._header_text(), id="query-header")
        yield LoadingIndicator(id="loading")
        yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
        yield Static("Type a query above to discover live music.", id="empty-label")
        yield Footer()

    def _header_text(self, label: str = "", count: int = 0) -> str:
        genre_tag = f"  ·  {self._genre_filter}" if self._genre_filter else ""
        festival_tag = "" if self._show_festivals else "  ·  no festivals"
        if label and count:
            return f"  {label}{genre_tag}{festival_tag}  ·  {count} result{'s' if count != 1 else ''}  ·  [underline]live[/underline]"
        loc = f"home: {self._home_neighbourhood}" if self._home_neighbourhood else "hyper-local live music"
        return f"  whereabout  ·  {loc}{genre_tag}{festival_tag}"

    def on_mount(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = False

        table = self.query_one("#results-table", DataTable)
        table.add_columns("#", "Artists / Title", "Date", "Time", "Venue")
        table.display = False

        inp = self.query_one("#search-input", Input)
        if self._home_neighbourhood:
            self._start_auto_fetch()
        else:
            inp.focus()

    def _start_auto_fetch(self, timeframe: str | None = None, force: bool = False) -> None:
        timeframe = timeframe or _default_timeframe()
        self._auto_timeframe = timeframe
        query = f"events in {self._home_neighbourhood} {timeframe}"
        inp = self.query_one("#search-input", Input)
        inp.value = query
        inp.focus()
        self.query_one("#empty-label", Static).display = False
        self.query_one("#loading", LoadingIndicator).display = True
        self._fetch(query, auto=True, genre_filter=self._genre_filter, force=force)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "go_home":
            return bool(self._home_neighbourhood)
        return True

    def action_go_home(self) -> None:
        if not self._home_neighbourhood:
            return
        self._genre_filter = None
        self.query_one("#results-table", DataTable).display = False
        self.query_one("#empty-label", Static).display = False
        self.query_one("#query-header", Static).update(self._header_text())
        self.query_one("#loading", LoadingIndicator).display = True
        self._start_auto_fetch()

    def action_focus_search(self) -> None:
        inp = self.query_one("#search-input", Input)
        inp.focus()
        inp.cursor_position = len(inp.value)

    def action_change_neighbourhood(self) -> None:
        def handle_result(resolved: str | None) -> None:
            if not resolved:
                return
            from whereabout.config import UserConfig
            cfg = UserConfig.load()
            cfg.home_neighbourhood = resolved
            cfg.save()
            self._home_neighbourhood = resolved
            self.query_one("#results-table", DataTable).display = False
            self.query_one("#empty-label", Static).display = False
            self.query_one("#query-header", Static).update(self._header_text())
            self._start_auto_fetch()

        self.app.push_screen(ChangeNeighbourhoodScreen(self._home_neighbourhood), handle_result)

    def action_filter_genre(self) -> None:
        def handle_result(result: str | None) -> None:
            if result is None:
                return  # cancelled
            new_filter = result or None  # "" = All genres → clear
            if new_filter == self._genre_filter:
                return
            self._genre_filter = new_filter
            self.query_one("#query-header", Static).update(self._header_text())
            text = self.query_one("#search-input", Input).value.strip()
            if text:
                self.query_one("#loading", LoadingIndicator).display = True
                self.query_one("#results-table", DataTable).display = False
                self.query_one("#empty-label", Static).display = False
                self._fetch(text, genre_filter=self._genre_filter)
            elif self._home_neighbourhood:
                self._start_auto_fetch()

        self.app.push_screen(GenreFilterScreen(self._genre_filter), handle_result)

    def action_refresh(self) -> None:
        text = self.query_one("#search-input", Input).value.strip()
        if not text and not self._home_neighbourhood:
            return
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#results-table", DataTable).display = False
        self.query_one("#empty-label", Static).display = False
        if text:
            self._fetch(text, genre_filter=self._genre_filter, force=True)
        else:
            self._auto_timeframe = None
            self._start_auto_fetch(force=True)

    def action_toggle_festivals(self) -> None:
        self._show_festivals = not self._show_festivals
        self._results = self._apply_festival_filter(self._all_results)
        self._render_table(self._results, self._last_label, self._last_source)

    def _apply_festival_filter(self, results: list[dict]) -> list[dict]:
        if self._show_festivals:
            return results
        return [r for r in results if not r.get("is_festival")]

    @on(Input.Submitted)
    def handle_search(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self._auto_timeframe = None  # manual search — disable adaptive logic
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#results-table", DataTable).display = False
        self.query_one("#empty-label", Static).display = False
        self._fetch(text, genre_filter=self._genre_filter)

    @work(thread=True)
    def _fetch(self, text: str, auto: bool = False, genre_filter: str | None = None, force: bool = False) -> None:
        results: list[dict] = []
        label = ""
        source = ""
        try:
            results, label, source = _run_query(text, self._home_neighbourhood, genre_filter, force=force)
        except Exception:
            pass
        self.app.call_from_thread(self._show_results, results, label, source, auto)

    def _show_results(
        self, results: list[dict], label: str, source: str, auto: bool = False
    ) -> None:
        raw_display = results[:_HOME_RESULT_CAP] if auto else results
        filtered = self._apply_festival_filter(raw_display)

        # Auto home fetch: expand window if too few visible results
        if auto and len(filtered) < _HOME_MIN_RESULTS and self._auto_timeframe:
            next_tf = _EXPAND_TO.get(self._auto_timeframe)
            if next_tf:
                self._start_auto_fetch(next_tf)
                return

        self._all_results = raw_display
        self._last_label = label
        self._last_source = source
        self._results = filtered
        self._render_table(filtered, label, source)

    def _render_table(self, display_results: list[dict], label: str, source: str) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        header = self.query_one("#query-header", Static)
        table = self.query_one("#results-table", DataTable)
        table.clear()

        if not display_results:
            header.update(self._header_text())
            header.tooltip = None
            # Check if festivals are the only reason we have no results
            festival_count = sum(1 for r in self._all_results if r.get("is_festival"))
            if festival_count and festival_count == len(self._all_results) and not self._show_festivals:
                empty_msg = (
                    f"Only festival{'s' if festival_count != 1 else ''} found ({festival_count}). "
                    f"Press [bold]f[/bold] to show them."
                )
            else:
                home_hint = "  Press [bold]h[/bold] to go home." if self._home_neighbourhood else ""
                empty_msg = f"No events found. Try a different query or neighbourhood.{home_hint}"
            self.query_one("#empty-label", Static).update(empty_msg)
            self.query_one("#empty-label", Static).display = True
            self.query_one("#search-input", Input).blur()
            self.refresh_bindings()
            return

        header.update(self._header_text(label, len(display_results)))
        header.tooltip = source
        for pos, r in enumerate(display_results):
            festival_prefix = "[F] " if r.get("is_festival") else ""
            artists_str = ", ".join(r["artists"]) if r["artists"] else r["title"]
            table.add_row(
                str(pos + 1),
                f"{festival_prefix}{artists_str}"[:50],
                r["date_local"],
                r["time_local"],
                r["venue"][:35],
                key=str(pos + 1),
            )
        table.display = True
        table.focus()
        self.refresh_bindings()

    @on(DataTable.RowSelected)
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value) - 1
        if 0 <= idx < len(self._results):
            self.app.push_screen(DetailScreen(self._results[idx]))


class WhereaboutApp(App):
    TITLE = "whereabout"
    CSS = CSS

    def __init__(self, home_neighbourhood: str | None = None) -> None:
        super().__init__()
        self._home_neighbourhood = home_neighbourhood

    def on_mount(self) -> None:
        self.push_screen(SearchScreen(self._home_neighbourhood))


def _run_query(text: str, home_neighbourhood: str | None, genre_filter: str | None = None, force: bool = False) -> tuple[list[dict], str, str]:
    from whereabout.query import parser, ranker
    from whereabout.config import UserConfig

    cfg = UserConfig.load()
    q = parser.parse(text)
    effective = q.neighbourhood or home_neighbourhood or cfg.home_neighbourhood
    if effective:
        q = q.model_copy(update={"neighbourhood": effective})
    if genre_filter:
        q = q.model_copy(update={"genres": [genre_filter]})

    results = ranker.rank(q, force=force)

    # Nearby fallback: if no results for a specific neighbourhood, try nearest ones
    nearby_label: str | None = None
    if not results and effective:
        from whereabout import neighbourhoods as nb
        for nearby in nb.nearby_neighbourhoods(effective, max_count=4):
            nearby_q = q.model_copy(update={"neighbourhood": nearby})
            nearby_results = ranker.rank(nearby_q, force=force)
            if nearby_results:
                results = nearby_results
                nearby_label = nearby
                break

    neighbourhood_label = nearby_label or effective or "London"
    genre_label = "/".join(q.genres) if q.genres else "all genres"
    delta_days = max(1, (q.date_range_end_utc - q.date_range_start_utc).days)
    if delta_days == 1:
        date_label = "tonight"
    elif delta_days == 2:
        date_label = "tomorrow"
    elif delta_days <= 4:
        date_label = "this weekend"
    elif delta_days <= 7:
        date_label = "this week"
    else:
        date_label = f"next {delta_days} days"
    if nearby_label:
        query_label = f"{genre_label} near {effective} ({nearby_label}) — {date_label}"
    else:
        query_label = f"{genre_label} in {neighbourhood_label} — {date_label}"

    sources = sorted({r["source"] for r in results}) if results else []
    source_note = (
        "live (" + " + ".join(s.replace("_", " ").upper() for s in sources) + ")"
        if sources else "live"
    )
    return results, query_label, source_note


def run_tui(home_neighbourhood: str | None = None) -> None:
    WhereaboutApp(home_neighbourhood=home_neighbourhood).run()
