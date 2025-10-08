#!/usr/bin/env python3
"""CLI tool for manual metrics retention and cleanup.

This script allows manual execution of metrics retention policies,
including downsampling, compression, and deletion of old metrics.

Usage:
    python scripts/metrics_cleanup.py --journal-dir data/journals
    python scripts/metrics_cleanup.py --config-root config --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from telemetry.contracts import RetentionPolicy
from telemetry.retention import MetricsRetention


def load_retention_policy(config_root: Path) -> RetentionPolicy:
    """Load retention policy from config.

    Args:
        config_root: Root config directory

    Returns:
        RetentionPolicy instance

    Raises:
        FileNotFoundError: If retention config not found
        ValueError: If config is invalid
    """
    # Try to load from base.yaml
    base_config_path = config_root / "base.yaml"
    if not base_config_path.exists():
        raise FileNotFoundError(f"Config file not found: {base_config_path}")

    with base_config_path.open() as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError("Empty config file")

    # Check if retention config exists
    if "retention" not in config:
        # Use default retention policy
        return RetentionPolicy.from_dict(
            {
                "raw_metrics": [
                    {"resolution": "1m", "retention_days": 7},
                    {"resolution": "5m", "retention_days": 30},
                    {"resolution": "1h", "retention_days": 180},
                    {"resolution": "1d", "retention_days": 730},
                ],
                "cleanup_schedule": "0 2 * * *",
            }
        )

    return RetentionPolicy.from_dict(config["retention"])


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments

    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(
        description="Manual metrics retention and cleanup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply retention policy to default journal dir
  python scripts/metrics_cleanup.py

  # Apply retention policy with custom journal dir
  python scripts/metrics_cleanup.py --journal-dir /var/lib/njord/journals

  # Dry run (show what would be done)
  python scripts/metrics_cleanup.py --dry-run

  # Use custom config root
  python scripts/metrics_cleanup.py --config-root /etc/njord
        """,
    )

    parser.add_argument(
        "--journal-dir",
        type=Path,
        default=Path("data/journals"),
        help="Journal directory (default: data/journals)",
    )

    parser.add_argument(
        "--config-root",
        type=Path,
        default=Path("config"),
        help="Config root directory (default: config)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args(argv)

    try:
        # Load retention policy
        policy = load_retention_policy(args.config_root)

        if args.verbose:
            print(f"Retention policy loaded from {args.config_root}")
            print("Retention levels:")
            for level in policy.raw_metrics:
                print(f"  - {level.resolution}: {level.retention_days} days")
            print(f"Cleanup schedule: {policy.cleanup_schedule}")
            print()

        # Initialize retention manager
        retention = MetricsRetention(journal_dir=args.journal_dir, policy=policy)

        if args.dry_run:
            print(f"DRY RUN: Would apply retention policy to {args.journal_dir}")
            print("No changes will be made.")
            return 0

        # Apply retention policy
        print(f"Applying retention policy to {args.journal_dir}...")
        stats = retention.apply_retention()

        print("\nRetention policy applied successfully:")
        print(f"  Files downsampled: {stats['downsampled']}")
        print(f"  Files compressed:  {stats['compressed']}")
        print(f"  Files deleted:     {stats['deleted']}")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: Invalid configuration - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
