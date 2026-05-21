from __future__ import annotations
from zoneinfo import ZoneInfo


def render_markdown(result: dict, enrichment: dict | None = None) -> str:
    """Render a single event as an enriched card."""
    lines = []
    lines.append(f"## {result['title']}")

    artists_str = ", ".join(result["artists"]) if result["artists"] else result["title"]
    lines.append(f"**Artist:** {artists_str}")

    local_dt = f"{result['date_local']} at {result['time_local']}"
    lines.append(f"**When:** {local_dt}")
    lines.append(f"**Where:** {result['venue']} ({result.get('postcode', '')})")

    if result.get("price"):
        lines.append(f"**Price:** {result['price']}")

    if result.get("ticket_url"):
        lines.append(f"**Tickets:** {result['ticket_url']}")

    if enrichment and enrichment.get("bio"):
        lines.append(f"\n**About {artists_str}:**")
        lines.append(enrichment["bio"])

    if enrichment and enrichment.get("notable_for"):
        lines.append(f"*{enrichment['notable_for']}*")

    return "\n".join(lines)
