```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                          ║
║  ██╗    ██╗ ██╗  ██╗ ███████╗ ██████╗  ███████╗  █████╗  ██████╗   ██████╗  ████████╗  ║
║  ██║    ██║ ██║  ██║ ██╔════╝ ██╔══██╗ ██╔════╝ ██╔══██╗ ██╔══██╗ ██╔═══██╗ ╚══██╔══╝  ║
║  ██║ █╗ ██║ ███████║ █████╗   ██████╔╝ █████╗   ███████║ ██████╔╝ ██║   ██║    ██║      ║
║  ██║███╗██║ ██╔══██║ ██╔══╝   ██╔══██╗ ██╔══╝   ██╔══██║ ██╔══██╗ ██║   ██║    ██║      ║
║  ╚███╔███╔╝ ██║  ██║ ███████╗ ██║  ██║ ███████╗ ██║  ██║ ██████╔╝ ╚██████╔╝    ██║      ║
║   ╚══╝╚══╝  ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═╝ ╚══════╝ ╚═╝  ╚═╝ ╚═════╝   ╚═════╝    ╚═╝      ║
║                                                                                          ║
║                        L o n d o n   L i v e   M u s i c                                ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
```

# Whereabot

Hyper-local live music discovery for London. Ask in plain English; get neighbourhood-precise gig listings pulled live from DICE, Resident Advisor, Songkick, and 49 venue websites.

```
whereabout session              # interactive TUI (recommended)
whereabout query "jazz in brixton this weekend"
whereabout query "soul in camden tonight" --limit 20
```

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install whereabout
```

## Setup

### 1. Configure your home neighbourhood

```bash
whereabout config init
# Prompts: "Your home neighbourhood (e.g. Brixton, Camden):"
```

"Around me" queries resolve to this neighbourhood by default.

### 3. Health check

```bash
whereabout doctor
```

## Usage

### Interactive TUI (recommended)

```bash
whereabout session
```

| Key | Action |
|-----|--------|
| `/` or `s` | Focus search input |
| `Enter` | Run query |
| `h` | Go home (clears genre filter, runs home neighbourhood) |
| `n` | Change home neighbourhood |
| `g` | Filter by genre |
| `f` | Toggle festival events (hidden by default) |
| `r` | Force-refresh all sources |
| `p` | Play preview for focused row |
| `Enter` on row | Open event detail with artist bios |
| `Esc` / `b` | Back |
| `Ctrl+C` | Quit |

When a query returns no results, the TUI automatically tries the nearest neighbourhoods before showing the empty state. If results only exist as festivals, it prompts you to press `f`.

### Music preview

Hover over any result row for ~350ms and a 30-second preview plays automatically via [Deezer](https://www.deezer.com). Press `p` to trigger manually. A green status bar shows the track name, artist, and source. If no preview is available, an amber bar shows the reason and auto-dismisses after 4 seconds. No account or API key required.

### CLI queries

```bash
whereabout query "jazz in brixton"
whereabout query "soul music in camden this weekend"
whereabout query "electronic gigs near me tonight"
whereabout query "show me jazz gigs around me" --limit 20
```

### Drill into an event

```bash
whereabout detail <event_id>
```

### Manage config

```bash
whereabout config get home_neighbourhood
whereabout config set home_neighbourhood Dalston
whereabout config list-neighbourhoods   # 52 supported neighbourhoods
```

## Sources

Events are fetched from multiple sources and merged into a local SQLite knowledge base, deduplicated by venue + time.

| Source | Type | Coverage |
|--------|------|----------|
| DICE FM | Live JSON API | Major London venues |
| Resident Advisor | Live scraper | Electronic / club nights |
| Songkick | Live scraper | 2000+ London metro events |
| Africa Centre | Venue scraper | London Bridge |
| Barbican Centre | Venue scraper | Shoreditch |
| Electric Ballroom | Venue scraper | Camden |
| Grow Hackney | Venue scraper | Mile End |
| Southbank Centre | Venue scraper | Bermondsey |
| The Windmill Brixton | Venue scraper | Brixton |
| Alexandra Palace | Venue scraper | Wood Green |
| Amersham Arms | Venue scraper | New Cross |
| Boisdale of Canary Wharf | Venue scraper | Canary Wharf |
| Brilliant Corners | Venue scraper | Dalston |
| Brixton Jamm | Venue scraper | Brixton |
| Cadogan Hall | Venue scraper | Chelsea |
| Cafe OTO | Venue scraper | Dalston |
| Cecil Sharp House | Venue scraper | Camden |
| Clapham Grand | Venue scraper | Clapham |
| Conway Hall | Venue scraper | Holborn |
| Corsica Studios | Venue scraper | Elephant & Castle |
| Dalston Superstore | Venue scraper | Dalston |
| Dingwalls | Venue scraper | Camden |
| EartH Hackney | Venue scraper | Hackney |
| Electric Brixton | Venue scraper | Brixton |
| Green Note | Venue scraper | Camden |
| Hackney Empire | Venue scraper | Hackney |
| Hootananny Brixton | Venue scraper | Brixton |
| Jazz Cafe | Venue scraper | Camden |
| LSO St Luke's | Venue scraper | Clerkenwell |
| The Lexington | Venue scraper | Islington |
| O2 Shepherd's Bush Empire | Venue scraper | Shepherd's Bush |
| Half Moon Putney | Venue scraper | Putney |
| Moth Club | Venue scraper | Hackney Wick |
| Peckham Levels | Venue scraper | Peckham |
| Shacklewell Arms | Venue scraper | Dalston |
| Oslo Hackney | Venue scraper | Dalston |
| The Harrison | Venue scraper | King's Cross |
| Paper Dress Vintage | Venue scraper | Dalston |
| Phonox | Venue scraper | Brixton |
| Rich Mix | Venue scraper | Bethnal Green |
| Ronnie Scott's | Venue scraper | Soho |
| Roundhouse | Venue scraper | Camden |
| Scala | Venue scraper | King's Cross |
| The 606 Club | Venue scraper | Chelsea |
| The Social | Venue scraper | Soho |
| St Martin-in-the-Fields | Venue scraper | Covent Garden |
| The Underworld Camden | Venue scraper | Camden |
| Village Underground | Venue scraper | Shoreditch |
| Vortex Jazz Club | Venue scraper | Stoke Newington |
| Wigmore Hall | Venue scraper | Marylebone |
| XOYO | Venue scraper | Clerkenwell |

Sources are refreshed when stale (2–6 hour cache per source).

## Neighbourhoods

52 London neighbourhoods supported, resolved from postcode prefixes and aliases. Includes colloquial names — "stokey" resolves to Stoke Newington, "angel" to Islington, etc.

```bash
whereabout config list-neighbourhoods
```

## Architecture

| Module | Role |
|--------|------|
| `query/parser.py` | NL → structured Query via Claude |
| `query/ranker.py` | Fetches live sources, filters by neighbourhood + genre + festival flag |
| `query/enrich.py` | Artist bios via Claude, cached 30 days |
| `kb/ingest.py` | Upserts events into SQLite (multi-source, deduplication) |
| `kb/read.py` | Reads events from KB by date range |
| `sources/` | Per-source scrapers (DICE, RA, Songkick, 49 venue scrapers) |
| `neighbourhoods.py` | Postcode-prefix → neighbourhood resolver, nearby fallback |
| `tui/app.py` | Textual TUI (search, genre filter, festival toggle, detail view) |
| `doctor.py` | Health checks |

### Location resolution

"In Brixton" resolves to postcodes SW2 and SW9. Postcode-prefix matching is used throughout — not ONS ward names. Ward aliases (e.g. "Brixton Windrush") and colloquial aliases (e.g. "stokey", "angel") are all mapped to canonical neighbourhood names.

### Festival detection

Events are flagged as festivals if: the Songkick URL contains `/festivals/`, the venue name contains outdoor keywords (park, common, fields), or 6+ artists are listed. Festivals are hidden by default in the TUI; press `f` to show them.

## Development

```bash
git clone ...
cd whereabout
uv sync
uv run pytest
uv run whereabout --version
```

Test ritual before any PR:
```bash
uv run pytest && uv run whereabout doctor
```

## Data & Privacy

- Event data is fetched from public APIs and venue websites.
- Artist bios are AI-generated. No personal data is sent.
- All data is stored locally in `~/.local/share/whereabout/whereabout.db`.
- Cache files live in `~/.cache/whereabout/`.
- For personal use only. Respect source sites' terms of service.

## Licence

MIT
