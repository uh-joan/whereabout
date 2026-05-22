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
    LoadingIndicator,
    Markdown,
    Static,
)
from textual import on, work

CSS = """
SearchScreen {
    layout: vertical;
}

#search-input {
    dock: top;
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
"""


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
        enrichments = {}
        for artist in self._result.get("artists", []):
            try:
                enrichments[artist] = enrich_artist(
                    artist, context_genres=self._result.get("genres", [])
                )
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


class SearchScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit"),
        Binding("/,s", "focus_search", "Search"),
        Binding("n", "change_neighbourhood", "Neighbourhood"),
    ]

    def __init__(self, home_neighbourhood: str | None = None) -> None:
        super().__init__()
        self._home_neighbourhood = home_neighbourhood
        self._results: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search — e.g. 'jazz in brixton tonight'",
            id="search-input",
        )
        yield Static(self._header_text(), id="query-header")
        yield LoadingIndicator(id="loading")
        yield DataTable(id="results-table", cursor_type="row", zebra_stripes=True)
        yield Static("Type a query above to discover live music.", id="empty-label")
        yield Footer()

    def _header_text(self, label: str = "", count: int = 0, source: str = "") -> str:
        if label and count:
            return f"  {label}  ·  {count} result{'s' if count != 1 else ''}  ·  {source}"
        loc = f"home: {self._home_neighbourhood}" if self._home_neighbourhood else "hyper-local live music"
        return f"  whereabout  ·  {loc}"

    def on_mount(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = False

        table = self.query_one("#results-table", DataTable)
        table.add_columns("#", "Artists / Title", "Date", "Time", "Venue")
        table.display = False

        inp = self.query_one("#search-input", Input)
        if self._home_neighbourhood:
            default_query = f"events in {self._home_neighbourhood}"
            inp.value = default_query
            inp.focus()
            self.query_one("#empty-label", Static).display = False
            self.query_one("#loading", LoadingIndicator).display = True
            self._fetch(default_query)
        else:
            inp.focus()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "change_neighbourhood":
            return bool(self._results)
        return True

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
            query = f"events in {resolved}"
            inp = self.query_one("#search-input", Input)
            inp.value = query
            self.query_one("#loading", LoadingIndicator).display = True
            self.query_one("#results-table", DataTable).display = False
            self.query_one("#empty-label", Static).display = False
            self.query_one("#query-header", Static).update(self._header_text())
            self._fetch(query)

        self.app.push_screen(ChangeNeighbourhoodScreen(self._home_neighbourhood), handle_result)

    @on(Input.Submitted)
    def handle_search(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#results-table", DataTable).display = False
        self.query_one("#empty-label", Static).display = False
        self._fetch(text)

    @work(thread=True)
    def _fetch(self, text: str) -> None:
        results: list[dict] = []
        label = ""
        source = ""
        try:
            results, label, source = _run_query(text, self._home_neighbourhood)
        except Exception:
            pass
        self.app.call_from_thread(self._show_results, results, label, source)

    def _show_results(self, results: list[dict], label: str, source: str) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        self._results = results

        header = self.query_one("#query-header", Static)
        table = self.query_one("#results-table", DataTable)
        table.clear()

        if not results:
            header.update(self._header_text())
            self.query_one("#empty-label", Static).update(
                "No events found. Try a different query or neighbourhood."
            )
            self.query_one("#empty-label", Static).display = True
            self.refresh_bindings()
            return

        header.update(self._header_text(label, len(results), source))
        for r in results:
            artists_str = ", ".join(r["artists"]) if r["artists"] else r["title"]
            table.add_row(
                str(r["index"]),
                artists_str[:50],
                r["date_local"],
                r["time_local"],
                r["venue"][:35],
                key=str(r["index"]),
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


def _run_query(text: str, home_neighbourhood: str | None) -> tuple[list[dict], str, str]:
    from whereabout.query import parser, ranker
    from whereabout.config import UserConfig

    cfg = UserConfig.load()
    q = parser.parse(text)
    effective = q.neighbourhood or home_neighbourhood or cfg.home_neighbourhood
    if effective:
        q = q.model_copy(update={"neighbourhood": effective})

    results = ranker.rank(q)

    neighbourhood_label = effective or "London"
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
    query_label = f"{genre_label} in {neighbourhood_label} — {date_label}"

    sources = sorted({r["source"] for r in results}) if results else []
    source_note = (
        "live (" + " + ".join(s.replace("_", " ").upper() for s in sources) + ")"
        if sources else "live"
    )
    return results, query_label, source_note


def run_tui(home_neighbourhood: str | None = None) -> None:
    WhereaboutApp(home_neighbourhood=home_neighbourhood).run()
