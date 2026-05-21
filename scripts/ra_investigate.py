#!/usr/bin/env python3
"""
Resident Advisor access investigation.

Tests three approaches in order:
  1. RSS feed     — zero-cost, no scraping
  2. GraphQL API  — RA's internal JSON API (same endpoint the web app uses)
  3. CloakBrowser — stealth Chromium binary, last resort

Run:
  uv run scripts/ra_investigate.py
  uv run scripts/ra_investigate.py --graphql-only
  uv run scripts/ra_investigate.py --cloak        # also runs CloakBrowser test
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

RA_RSS_URL = "https://ra.co/events.rss?area=13"  # 13 = London

# RA's internal GraphQL endpoint (same one their React app hits)
RA_GRAPHQL_URL = "https://ra.co/graphql"

# Minimal headers that mimic a browser session
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://ra.co/",
    "Origin": "https://ra.co",
}

# GraphQL query for London events — mirrors what the RA web app sends
EVENTS_QUERY = """
query GET_EVENT_LISTINGS(
  $filters: FilterInputDtoInput
  $pageSize: Int
  $page: Int
) {
  eventListings(
    filters: $filters
    pageSize: $pageSize
    page: $page
  ) {
    data {
      id
      event {
        id
        startTime
        title
        lineup
        venue {
          id
          name
          address
          area {
            id
            name
          }
        }
        artists {
          id
          name
        }
      }
    }
    totalResults
  }
}
"""

EVENTS_VARIABLES = {
    "filters": {
        "areas": {"eq": 13},  # London
        "listingDate": {
            "gte": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "lte": "2099-12-31",
        },
        "listingPosition": 1,
    },
    "pageSize": 5,
    "page": 1,
}


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def fail(msg: str) -> None:
    print(f"  ✗  {msg}")


def info(msg: str) -> None:
    print(f"     {msg}")


# ── 1. RSS ────────────────────────────────────────────────────────────────────

def investigate_rss() -> bool:
    section("1. RSS feed")
    info(f"GET {RA_RSS_URL}")
    try:
        r = httpx.get(RA_RSS_URL, headers=BROWSER_HEADERS, timeout=15, follow_redirects=True)
    except Exception as e:
        fail(f"Request failed: {e}")
        return False

    info(f"Status: {r.status_code}  Content-Type: {r.headers.get('content-type', '?')}")

    if r.status_code != 200:
        fail(f"HTTP {r.status_code} — RSS feed not accessible")
        if r.status_code in (403, 429):
            info("Likely blocked (Cloudflare / rate-limit)")
        return False

    content_type = r.headers.get("content-type", "")
    if "html" in content_type and "<html" in r.text[:200].lower():
        fail("Response is HTML (Cloudflare challenge page), not RSS XML")
        info(f"First 200 chars: {r.text[:200]!r}")
        return False

    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        fail(f"XML parse error: {e}")
        info(f"Body preview: {r.text[:300]!r}")
        return False

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    channel = root.find("channel")
    if channel is None:
        fail("No <channel> element found in RSS")
        return False

    items = channel.findall("item")
    ok(f"RSS is live — {len(items)} items in feed")

    if items:
        first = items[0]
        fields = {child.tag: child.text for child in first}
        ok(f"Fields per item: {list(fields.keys())}")
        info(f"Sample title: {fields.get('title', '?')}")
        info(f"Sample date:  {fields.get('pubDate', '?')}")
        info(f"Sample link:  {fields.get('link', '?')}")
        has_venue = any("venue" in k.lower() for k in fields)
        has_lineup = any("lineup" in k.lower() or "artist" in k.lower() for k in fields)
        info(f"Has venue field:  {has_venue}")
        info(f"Has lineup field: {has_lineup}")
        if not has_venue or not has_lineup:
            info("Note: missing venue/lineup — may need to cross-reference with GraphQL")

    return True


# ── 2. GraphQL ────────────────────────────────────────────────────────────────

def investigate_graphql() -> bool:
    section("2. GraphQL API")
    info(f"POST {RA_GRAPHQL_URL}")

    payload = {"query": EVENTS_QUERY, "variables": EVENTS_VARIABLES}

    try:
        r = httpx.post(
            RA_GRAPHQL_URL,
            json=payload,
            headers={**BROWSER_HEADERS, "Content-Type": "application/json"},
            timeout=20,
            follow_redirects=True,
        )
    except Exception as e:
        fail(f"Request failed: {e}")
        return False

    info(f"Status: {r.status_code}  Content-Type: {r.headers.get('content-type', '?')}")

    if r.status_code == 403:
        fail("403 Forbidden — bot-detection active on GraphQL endpoint")
        cf_ray = r.headers.get("cf-ray")
        if cf_ray:
            info(f"Cloudflare Ray-ID: {cf_ray} — Cloudflare is in front")
        return False

    if r.status_code == 401:
        fail("401 Unauthorized — endpoint requires authentication")
        info("Next step: capture a logged-in session token from browser devtools")
        return False

    if r.status_code != 200:
        fail(f"HTTP {r.status_code}")
        info(f"Body: {r.text[:300]!r}")
        return False

    content_type = r.headers.get("content-type", "")
    if "html" in content_type:
        fail("Response is HTML (Cloudflare challenge), not JSON")
        info(f"First 200 chars: {r.text[:200]!r}")
        return False

    try:
        data = r.json()
    except Exception:
        fail("Response is not valid JSON")
        info(f"Body: {r.text[:300]!r}")
        return False

    if "errors" in data:
        fail(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
        return False

    listings = (
        data.get("data", {})
        .get("eventListings", {})
    )
    if not listings:
        fail("No eventListings in response — query shape may have changed")
        info(f"Keys returned: {list(data.get('data', {}).keys())}")
        return False

    total = listings.get("totalResults", "?")
    events = listings.get("data", [])
    ok(f"GraphQL is live — {total} total London events, returned {len(events)}")

    if events:
        listing = events[0]
        ev = listing.get("event") or listing  # fields nested under "event"
        ok(f"Listing keys: {list(listing.keys())}")
        ok(f"Event keys:   {list(ev.keys())}")
        info(f"Sample title:  {ev.get('title', '?')}")
        info(f"Sample time:   {ev.get('startTime', '?')}")
        venue = ev.get("venue") or {}
        info(f"Sample venue:  {venue.get('name', '?')} — {venue.get('address', '?')}")
        area = venue.get("area") or {}
        info(f"Sample area:   {area.get('name', '?')}")
        artists = ev.get("artists") or []
        info(f"Sample lineup: {[a['name'] for a in artists]}")
        info(f"Sample lineup text: {ev.get('lineup', '?')}")
        print()
        info("Raw first event (JSON):")
        print(json.dumps(listing, indent=4, default=str))

    return True


# ── 3. CloakBrowser ───────────────────────────────────────────────────────────

def investigate_cloak() -> bool:
    section("3. CloakBrowser (stealth Chromium)")
    info("Checking if cloakbrowser is installed...")

    try:
        from cloakbrowser import launch  # type: ignore
        ok("cloakbrowser package found")
    except ImportError:
        fail("cloakbrowser not installed")
        info("Install: uv add cloakbrowser  (or: pip install cloakbrowser)")
        info("It downloads a patched Chromium binary on first run (~300MB)")
        info("API is a Playwright drop-in: replace playwright import with cloakbrowser.launch()")
        return False

    info("Launching stealth browser to https://ra.co/events/uk/london ...")
    try:
        browser = launch(headless=True, humanize=True)
        page = browser.new_page()
        page.goto("https://ra.co/events/uk/london", timeout=30_000)
        title = page.title()
        content = page.content()
        browser.close()
    except Exception as e:
        fail(f"CloakBrowser launch/navigation failed: {e}")
        return False

    if "challenge" in title.lower() or "just a moment" in title.lower():
        fail(f"Cloudflare challenge page served — title: {title!r}")
        return False

    if "Resident Advisor" in title or "events" in title.lower():
        ok(f"Page loaded successfully — title: {title!r}")
        has_event_data = "__NEXT_DATA__" in content or "eventListings" in content
        info(f"Hydration JSON present (__NEXT_DATA__): {has_event_data}")
        if has_event_data:
            ok("Next.js hydration data found — parseable without additional GraphQL calls")
        return True

    fail(f"Unexpected page title: {title!r}")
    info(f"Content preview: {content[:200]!r}")
    return False


# ── 4. Filter introspection ───────────────────────────────────────────────────

INTROSPECT_FILTER_QUERY = """
query IntrospectFilterInput {
  __type(name: "FilterInputDtoInput") {
    name
    inputFields {
      name
      description
      type {
        name
        kind
        ofType { name kind }
      }
    }
  }
}
"""

INTROSPECT_EVENT_LISTING_QUERY = """
query IntrospectEventListing {
  __type(name: "EventListing") {
    name
    fields {
      name
      type { name kind ofType { name kind } }
    }
  }
}
"""

INTROSPECT_EVENT_QUERY = """
query IntrospectEvent {
  __type(name: "Event") {
    name
    fields {
      name
      type { name kind ofType { name kind } }
    }
  }
}
"""


def _graphql(query: str, variables: dict | None = None) -> dict:
    r = httpx.post(
        RA_GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={**BROWSER_HEADERS, "Content-Type": "application/json"},
        timeout=20,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.json()


def investigate_filters() -> bool:
    section("4. Filter schema introspection")

    # FilterInputDtoInput fields
    try:
        data = _graphql(INTROSPECT_FILTER_QUERY)
    except Exception as e:
        fail(f"Introspection request failed: {e}")
        return False

    filter_type = (data.get("data") or {}).get("__type")
    if not filter_type:
        fail("Introspection returned no __type (introspection may be disabled)")
        return False

    ok(f"FilterInputDtoInput fields:")
    for f in filter_type.get("inputFields") or []:
        inner = (f["type"].get("ofType") or {}).get("name") or f["type"].get("name") or "?"
        kind = f["type"].get("kind", "")
        print(f"     {f['name']:30s} {kind}/{inner}")

    # EventListing fields
    try:
        data2 = _graphql(INTROSPECT_EVENT_LISTING_QUERY)
        listing_type = (data2.get("data") or {}).get("__type")
        if listing_type:
            print()
            ok("EventListing fields:")
            for f in listing_type.get("fields") or []:
                inner = (f["type"].get("ofType") or {}).get("name") or f["type"].get("name") or "?"
                print(f"     {f['name']:30s} {inner}")
    except Exception:
        pass

    # Event fields
    try:
        data3 = _graphql(INTROSPECT_EVENT_QUERY)
        event_type = (data3.get("data") or {}).get("__type")
        if event_type:
            print()
            ok("Event fields:")
            for f in event_type.get("fields") or []:
                inner = (f["type"].get("ofType") or {}).get("name") or f["type"].get("name") or "?"
                print(f"     {f['name']:30s} {inner}")
    except Exception:
        pass

    # Try a genre/tag filter
    section("4b. Test genre filter")
    try:
        now = datetime.now(timezone.utc)
        genre_vars = {
            "filters": {
                "areas": {"eq": 13},
                "genres": {"eq": [1]},   # genre id 1 — likely Techno or similar
                "listingDate": {
                    "gte": now.strftime("%Y-%m-%d"),
                    "lte": "2099-12-31",
                },
                "listingPosition": 1,
            },
            "pageSize": 3,
            "page": 1,
        }
        genre_data = _graphql(EVENTS_QUERY, genre_vars)
        genre_listings = (genre_data.get("data") or {}).get("eventListings") or {}
        if "errors" in genre_data:
            fail(f"Genre filter error: {genre_data['errors'][0]['message']}")
        else:
            total = genre_listings.get("totalResults", "?")
            ok(f"genres filter works — {total} results for genre id=1")
    except Exception as e:
        fail(f"Genre filter test failed: {e}")

    # Try venue postcode area filter
    section("4c. Test smaller area (Shoreditch postcode EC2A)")
    try:
        now = datetime.now(timezone.utc)
        area_vars = {
            "filters": {
                "areas": {"eq": 13},
                "listingDate": {
                    "gte": now.strftime("%Y-%m-%d"),
                    "lte": "2099-12-31",
                },
                "listingPosition": 1,
            },
            "pageSize": 10,
            "page": 1,
        }
        area_data = _graphql(EVENTS_QUERY, area_vars)
        area_listings = (area_data.get("data") or {}).get("eventListings") or {}
        events = area_listings.get("data") or []
        # Check postcode distribution
        postcodes = []
        for listing in events:
            ev = listing.get("event") or {}
            addr = (ev.get("venue") or {}).get("address") or ""
            # Extract last token that looks like a postcode
            tokens = addr.split(",")
            if tokens:
                pc = tokens[-1].strip()
                postcodes.append(pc)
        ok(f"Postcode sample from first 10 results: {postcodes}")
        info("Neighbourhood filtering will be done post-fetch on venue.address")
    except Exception as e:
        fail(f"Area test failed: {e}")

    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="RA access investigation")
    parser.add_argument("--graphql-only", action="store_true")
    parser.add_argument("--filters", action="store_true", help="Run filter introspection")
    parser.add_argument("--cloak", action="store_true", help="Also run CloakBrowser test")
    args = parser.parse_args()

    print("\nResident Advisor — access investigation")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

    results: dict[str, bool] = {}

    if not args.graphql_only and not args.filters:
        results["rss"] = investigate_rss()

    if not args.filters:
        results["graphql"] = investigate_graphql()

    if args.filters or not args.graphql_only:
        results["filters"] = investigate_filters()

    if args.cloak:
        results["cloakbrowser"] = investigate_cloak()

    section("Summary")
    for name, passed in results.items():
        (ok if passed else fail)(name)

    print()
    if results.get("rss"):
        info("Recommended path: RSS feed (check if lineup/venue fields are sufficient)")
    elif results.get("graphql"):
        info("Recommended path: GraphQL API (unauthenticated, structured JSON)")
    elif results.get("cloakbrowser"):
        info("Recommended path: CloakBrowser + __NEXT_DATA__ parsing")
    else:
        info("All approaches blocked. Options:")
        info("  a) Add --cloak flag and install cloakbrowser")
        info("  b) Capture a logged-in RA session token and retry GraphQL with auth headers")
        info("  c) Skip RA and expand venues.yaml coverage instead")

    print()
    sys.exit(0 if any(results.values()) else 1)


if __name__ == "__main__":
    main()
