---
name: whereabout
description: Hyper-local London live music discovery. Search for gigs by genre and neighbourhood using natural language.
version: "0.1.0"
trigger_patterns:
  - "gigs|live music|jazz|soul|funk|electronic|concerts|events"
  - "show me.*(?:gigs|music|live|events)"
  - "what.*(?:on|playing|happening).*(?:tonight|this weekend|this week)"
  - "(?:jazz|soul|funk|electronic|reggae|blues).*(?:in|near|around|at)"
---

# Whereabout — Live Music Discovery

This skill finds live music events in London using hyper-local neighbourhood precision.

## Usage

Ask naturally:
- "Show me jazz gigs around me"
- "Soul live music in Brixton this weekend"
- "What's on in Camden tonight?"
- "Jazz in Shoreditch next week"

## How it works

The skill runs the `whereabout` CLI tool to search for events.

```bash
whereabout query "<your query>" [--format markdown] [--limit 10]
```

For more detail on a specific event:
```bash
whereabout detail <event_id>
```

## Setup

1. Install: `uv tool install whereabout`
2. Set API key: `export ANTHROPIC_API_KEY=sk-ant-...`
3. Configure: `whereabout config init`
4. Check health: `whereabout doctor`

## Notes

- v1.0 searches DICE FM live. Results are neighbourhood-filtered to postcode level.
- "Around me" uses your configured home neighbourhood (`whereabout config get home_neighbourhood`).
- AC #7 (multi-source KB with RA + venues) is planned for v1.1.
