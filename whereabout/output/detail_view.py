from __future__ import annotations


def render_markdown(result: dict, enrichments: dict[str, dict]) -> str:
    """Render a detailed event view with all artist bios."""
    lines = []
    lines.append(f"# {result['title']}")
    lines.append(f"**{result['date_local']} {result['time_local']}  ·  {result['venue']}**")

    if result.get("postcode"):
        lines.append(f"Neighbourhood: {result['postcode']}")

    if result.get("ticket_url"):
        lines.append(f"\n[Get Tickets]({result['ticket_url']})  {result.get('price', '')}")

    if enrichments:
        lines.append("\n---\n**Artists**\n")
        for artist, enrich in enrichments.items():
            lines.append(f"### {artist}")
            if enrich.get("bio"):
                lines.append(enrich["bio"])
            if enrich.get("notable_for"):
                lines.append(f"*{enrich['notable_for']}*")
            if enrich.get("genres"):
                lines.append(f"Genres: {', '.join(enrich['genres'])}")
            links = enrich.get("links") or {}
            if links:
                link_parts = []
                if links.get("soundcloud"):
                    link_parts.append(f"[SoundCloud]({links['soundcloud']})")
                if links.get("bandcamp"):
                    link_parts.append(f"[Bandcamp]({links['bandcamp']})")
                if links.get("website"):
                    link_parts.append(f"[Website]({links['website']})")
                lines.append("  ".join(link_parts))

    return "\n".join(lines)
