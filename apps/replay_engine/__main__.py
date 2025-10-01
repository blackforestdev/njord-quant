"""Entry point for replay engine module."""

from __future__ import annotations

import asyncio

from apps.replay_engine.main import main

if __name__ == "__main__":
    asyncio.run(main())
