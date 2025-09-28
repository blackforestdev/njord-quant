# ADR-0001: Foundation
- Local-first, no Docker; systemd per service
- Event-driven via Redis pub/sub (abstraction in core/bus.py)
- Postgres for state/journaling; NDJSON on disk for replay
- Strategies emit OrderIntent; Risk is single gatekeeper
