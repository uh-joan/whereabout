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

    return "\n".join(lines)
