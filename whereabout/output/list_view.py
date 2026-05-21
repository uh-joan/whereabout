from __future__ import annotations


def render_markdown(results: list[dict], query_label: str, source_note: str = "live (DICE)") -> str:
    if not results:
        return f"No events found for: {query_label}\n\nTry a broader search or different neighbourhood."

    lines = [f"**{query_label}**\n"]
    for r in results:
        artists_str = ", ".join(r["artists"]) if r["artists"] else r["title"]
        lines.append(
            f"  {r['index']}. {artists_str:<35} {r['date_local']} {r['time_local']}  {r['venue']}"
        )
    lines.append(f"\nType 'more on <n>' or 'tickets for <n>' to drill in. Showing {len(results)} result(s).")
    lines.append(f"Source: {source_note}")
    return "\n".join(lines)


def render_json(results: list[dict]) -> str:
    import json
    return json.dumps(results, indent=2, default=str)
