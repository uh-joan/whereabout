from __future__ import annotations
import sys
from pathlib import Path
import typer

app = typer.Typer(help="Hyper-local live music discovery")
config_app = typer.Typer(help="Manage whereabout configuration")
schedule_app = typer.Typer(help="Manage background refresh schedule")
app.add_typer(config_app, name="config")
app.add_typer(schedule_app, name="schedule")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", is_eager=True, help="Show version and exit"),
) -> None:
    from whereabout.logging import configure_logging
    configure_logging()
    if version:
        from whereabout import __version__
        typer.echo(f"whereabout {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@config_app.command("init")
def config_init() -> None:
    """Interactive first-run setup."""
    from whereabout.config import UserConfig
    from whereabout import neighbourhoods as nb
    typer.echo("Whereabout setup")
    known = nb.list_all()
    home = typer.prompt(f"Your home neighbourhood (e.g. Brixton, Camden). Known: {', '.join(known[:5])}...")
    resolved = nb.resolve_name(home)
    if resolved is None:
        suggestions = nb.did_you_mean(home)
        if suggestions:
            typer.echo(f"Unknown neighbourhood '{home}'. Did you mean: {', '.join(suggestions)}?")
        else:
            typer.echo(f"Unknown neighbourhood '{home}'. Run 'whereabout config list-neighbourhoods' to see all.")
        resolved = home  # Save as-is and let user fix later
    cfg = UserConfig(home_neighbourhood=resolved)
    cfg.save()
    typer.echo(f"Saved. Home neighbourhood: {resolved}")


@config_app.command("get")
def config_get(key: str) -> None:
    """Get a config value."""
    from whereabout.config import UserConfig
    cfg = UserConfig.load()
    value = getattr(cfg, key, None)
    if value is None:
        typer.echo(f"Unknown key: {key}", err=True)
        raise typer.Exit(1)
    typer.echo(str(value))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Set a config value."""
    from whereabout.config import UserConfig
    cfg = UserConfig.load()
    if not hasattr(cfg, key):
        typer.echo(f"Unknown key: {key}", err=True)
        raise typer.Exit(1)
    field_type = type(getattr(cfg, key))
    setattr(cfg, key, field_type(value))
    cfg.save()
    typer.echo(f"Set {key} = {value}")


@config_app.command("list-neighbourhoods")
def config_list_neighbourhoods() -> None:
    """List all known neighbourhoods."""
    from whereabout import neighbourhoods as nb
    for name in sorted(nb.list_all()):
        typer.echo(name)


@app.command("refresh")
def refresh(
    source: str = typer.Option("dice_fm", "--source", help="Source ID to refresh"),
    horizon_days: int = typer.Option(14, "--horizon-days", help="Days ahead to fetch"),
    browser: bool = typer.Option(False, "--browser/--no-browser", help="Also run browser-based venue scrapers (Jazz Cafe, Ronnie Scott's, Corsica Studios)"),
) -> None:
    """Admin: refresh the knowledge base from a source (v1.0: DICE only)."""
    import asyncio
    from datetime import datetime, timezone, timedelta
    from whereabout.sources.dice_fm import DICESource
    from whereabout.kb.ingest import ingest
    from whereabout.config import UserConfig
    from whereabout.models import Query

    cfg = UserConfig.load()
    now = datetime.now(timezone.utc)
    query = Query(
        raw_text=f"refresh {source}",
        genres=[],
        neighbourhood=cfg.home_neighbourhood or None,
        date_range_start_utc=now,
        date_range_end_utc=now + timedelta(days=horizon_days),
    )

    if source != "dice_fm":
        typer.echo(f"Unknown source: {source}. Only 'dice_fm' is available in v1.0.", err=True)
        raise typer.Exit(1)

    src = DICESource()
    typer.echo(f"Fetching from DICE FM (horizon: {horizon_days} days)...")
    raws = asyncio.run(src.fetch(query))
    typer.echo(f"Fetched {len(raws)} events.")
    upserted = ingest(raws)
    typer.echo(f"Upserted {upserted} new events into KB.")

    if browser:
        from whereabout.sources.venues.jazz_cafe import JazzCafeSource
        from whereabout.sources.venues.ronnie_scotts import RonnieScottsSource
        from whereabout.sources.venues.corsica_studios import CorsicaStudiosSource

        browser_sources = [JazzCafeSource(), RonnieScottsSource(), CorsicaStudiosSource()]

        async def _fetch_browser() -> list:
            results = await asyncio.gather(
                *[s.fetch(query) for s in browser_sources], return_exceptions=True
            )
            raws_all = []
            for r in results:
                if isinstance(r, list):
                    raws_all.extend(r)
            return raws_all

        typer.echo("Fetching from browser-based venue scrapers...")
        browser_raws = asyncio.run(_fetch_browser())
        typer.echo(f"Fetched {len(browser_raws)} events from browser scrapers.")
        if browser_raws:
            browser_upserted = ingest(browser_raws)
            typer.echo(f"Upserted {browser_upserted} new events from browser scrapers into KB.")


@app.command("query")
def query_cmd(
    text: str = typer.Argument(..., help="Natural language query, e.g. 'jazz in brixton'"),
    fmt: str = typer.Option("markdown", "--format", help="Output format: markdown or json"),
    limit: int = typer.Option(10, "--limit"),
    force_refresh: bool = typer.Option(False, "--refresh", "-r", help="Bypass cache and re-fetch all sources"),
) -> None:
    """Search for live music events."""
    import re
    from whereabout.query import parser, ranker
    from whereabout.output import list_view
    from whereabout.config import UserConfig

    cfg = UserConfig.load()
    if cfg.is_first_run():
        typer.echo("First run! Let's set your home neighbourhood first.")
        config_init()

    try:
        q = parser.parse(text)
    except Exception as e:
        typer.echo(f"Parser error: {e}", err=True)
        raise typer.Exit(1)

    # Surface did-you-mean substitution
    if "[did_you_mean:" in q.raw_text:
        m = re.search(r"\[did_you_mean:(.+?)\]", q.raw_text)
        if m:
            typer.echo(f"No exact match — showing results for {m.group(1)}.")

    # Always resolve to a specific neighbourhood — fall back to home, never "London"
    effective_neighbourhood = q.neighbourhood or cfg.home_neighbourhood
    if effective_neighbourhood:
        q = q.model_copy(update={"neighbourhood": effective_neighbourhood})

    neighbourhood_label = effective_neighbourhood or "London"
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

    try:
        results = ranker.rank(q, force=force_refresh)
    except Exception as e:
        typer.echo(f"Fetch error: {e}", err=True)
        raise typer.Exit(1)

    if fmt == "json":
        typer.echo(list_view.render_json(results))
    else:
        sources = sorted({r["source"] for r in results}) if results else []
        source_note = "live (" + " + ".join(s.replace("_", " ").upper() for s in sources) + ")" if sources else "live"
        typer.echo(list_view.render_markdown(results, query_label, source_note))


@app.command("detail")
def detail_cmd(
    event_id: str = typer.Argument(..., help="Event ID or index from last query (e.g. '1' or 'dice_fm:abc123')"),
    fmt: str = typer.Option("markdown", "--format"),
) -> None:
    """Get detailed info and artist bios for a specific event."""
    import json
    from zoneinfo import ZoneInfo
    from datetime import datetime, timezone
    from whereabout.db import get_connection
    from whereabout.output import detail_view
    from whereabout.query.enrich import enrich_artist

    with get_connection() as conn:
        row = conn.execute(
            """SELECT e.*, v.name as venue_name, v.postcode as venue_postcode
               FROM events e LEFT JOIN venues v ON e.venue_id = v.id
               WHERE e.stable_hash LIKE ? OR e.source_urls LIKE ?
               LIMIT 1""",
            (f"%{event_id}%", f"%{event_id}%")
        ).fetchone()

        if not row:
            typer.echo(f"Event not found: {event_id}", err=True)
            raise typer.Exit(1)

        artist_rows = conn.execute(
            """SELECT a.name FROM artists a
               JOIN event_artists ea ON a.id = ea.artist_id
               WHERE ea.event_id = ?""",
            (row["id"],)
        ).fetchall()

    dt = datetime.fromisoformat(row["date_start_utc"].replace("Z", "+00:00"))
    local_dt = dt.astimezone(ZoneInfo("Europe/London"))
    artists = [r["name"] for r in artist_rows]

    result = {
        "title": row["title"],
        "artists": artists,
        "venue": row["venue_name"] or "",
        "postcode": row["venue_postcode"] or "",
        "date_local": local_dt.strftime("%a %d %b"),
        "time_local": local_dt.strftime("%H:%M"),
        "ticket_url": row["ticket_url"],
        "price": "",
        "genres": json.loads(row["genres"]),
    }

    event_genres = result["genres"]

    # Enrich each artist
    enrichments = {}
    for artist in artists:
        try:
            enrichments[artist] = enrich_artist(artist, context_genres=event_genres)
        except Exception as e:
            enrichments[artist] = {"bio": f"(enrichment unavailable: {e})", "genres": [], "notable_for": ""}

    typer.echo(detail_view.render_markdown(result, enrichments))


@app.command("session")
def session_cmd(
    tui: bool = typer.Option(True, "--tui/--no-tui", help="Use full TUI (default) or plain REPL"),
) -> None:
    """Start an interactive session with query history and result navigation."""
    from whereabout.config import UserConfig
    cfg = UserConfig.load()
    if tui:
        from whereabout.tui.app import run_tui
        run_tui(home_neighbourhood=cfg.home_neighbourhood)
    else:
        from whereabout.session import run_session
        run_session(home_neighbourhood=cfg.home_neighbourhood)


_PLIST_LABEL = "com.whereabout.refresh"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"


def _plist_content(binary: str, interval: int, log_dir: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{binary}</string>
        <string>refresh</string>
        <string>--browser</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir / "refresh.log"}</string>
    <key>StandardErrorPath</key>
    <string>{log_dir / "refresh.err"}</string>
</dict>
</plist>
"""


@schedule_app.command("install")
def schedule_install(
    interval_hours: int = typer.Option(6, "--interval-hours", help="Refresh interval in hours"),
) -> None:
    """Install a launchd agent to run browser refresh on a schedule (macOS only)."""
    import subprocess

    binary = Path(sys.executable).parent / "whereabout"
    if not binary.exists():
        typer.echo(f"Could not find whereabout binary at {binary}", err=True)
        raise typer.Exit(1)
    binary = str(binary)

    log_dir = Path.home() / ".local" / "share" / "whereabout" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(_plist_content(binary, interval_hours * 3600, log_dir))

    # Unload first in case it's already loaded
    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(_PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"launchctl load failed: {result.stderr.strip()}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Installed: refresh every {interval_hours}h")
    typer.echo(f"Plist:     {_PLIST_PATH}")
    typer.echo(f"Logs:      {log_dir}/refresh.log")
    typer.echo(f"Errors:    {log_dir}/refresh.err")
    typer.echo("\nTo uninstall: whereabout schedule uninstall")


@schedule_app.command("uninstall")
def schedule_uninstall() -> None:
    """Remove the launchd refresh agent."""
    import subprocess

    if not _PLIST_PATH.exists():
        typer.echo("No schedule installed.")
        return
    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True)
    _PLIST_PATH.unlink()
    typer.echo("Schedule removed.")


@schedule_app.command("status")
def schedule_status() -> None:
    """Show whether the refresh schedule is active."""
    import subprocess

    if not _PLIST_PATH.exists():
        typer.echo("Not installed. Run: whereabout schedule install")
        return
    result = subprocess.run(
        ["launchctl", "list", _PLIST_LABEL], capture_output=True, text=True
    )
    if result.returncode == 0:
        typer.echo(f"Active — {_PLIST_PATH}")
        typer.echo(result.stdout.strip())
    else:
        typer.echo(f"Plist exists but agent not loaded: {_PLIST_PATH}")


@app.command("doctor")
def doctor(prune: bool = typer.Option(False, "--prune", help="Also prune old events")) -> None:
    """Run health checks."""
    from whereabout import doctor as doc
    from whereabout.db import get_connection
    results = doc.run_checks()
    all_pass = True
    for passed, msg in results:
        typer.echo(msg)
        if not passed:
            all_pass = False
    if prune:
        with get_connection() as conn:
            deleted = conn.execute(
                "DELETE FROM events WHERE date_start_utc < datetime('now', '-7 days')"
            ).rowcount
            conn.commit()
        typer.echo(f"Pruned {deleted} past events.")
    raise typer.Exit(0 if all_pass else 1)
