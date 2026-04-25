#!/usr/bin/env python3
"""Repository-local market data archive manager.

This module exists to protect minute-level market data from being lost when
Yahoo's rolling intraday window expires. The archive directory is the durable
source of truth. Future agents should treat these rules as non-optional:

1. Never hand-edit or overwrite files under ``data/archive/``.
2. ``data/merged/`` must be rebuilt from archived snapshots only.
3. ``data/latest/`` is a convenience working copy, not the durable history.
4. If you need to refresh data, create a new dated snapshot instead of
   replacing older archive files.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from datetime import date

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
DATA_ROOT = REPO_ROOT


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().lower().replace("/", "-")


def latest_data_path(symbol: str, interval: str, data_root: str | os.PathLike | None = None) -> str:
    root = Path(data_root or DATA_ROOT)
    return str(root / "data" / "latest" / normalize_symbol(symbol) / f"{interval}.csv")


def archive_snapshot_path(
    symbol: str,
    interval: str,
    snapshot_date: str,
    data_root: str | os.PathLike | None = None,
) -> str:
    root = Path(data_root or DATA_ROOT)
    return str(root / "data" / "archive" / normalize_symbol(symbol) / interval / f"{snapshot_date}.csv")


def merged_data_path(symbol: str, interval: str, data_root: str | os.PathLike | None = None) -> str:
    root = Path(data_root or DATA_ROOT)
    return str(root / "data" / "merged" / normalize_symbol(symbol) / f"{interval}.csv")


def default_snapshot_date() -> str:
    return date.today().isoformat()


def market_data_paths(symbol: str, interval: str, use_merged: bool = False) -> dict:
    """Return the managed paths for one symbol.

    Agents should prefer these helpers over ad-hoc path joins so the repository
    keeps one consistent data layout.
    """
    return {
        "latest": latest_data_path(symbol, interval),
        "merged": merged_data_path(symbol, interval),
        "preferred": merged_data_path(symbol, interval) if use_merged else latest_data_path(symbol, interval),
    }


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _next_available_archive_path(path: str) -> str:
    """Keep archive snapshots append-only; never overwrite an existing snapshot."""
    candidate = Path(path)
    if not candidate.exists():
        return str(candidate)
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        next_candidate = candidate.with_name(f"{stem}-{counter}{suffix}")
        if not next_candidate.exists():
            return str(next_candidate)
        counter += 1


def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)
    return df.sort_index()


def record_snapshot_from_csv(
    *,
    symbol: str,
    interval: str,
    source_csv: str,
    snapshot_date: str,
    data_root: str | os.PathLike | None = None,
) -> dict:
    """Store a downloaded CSV into archive + latest without mutating history."""
    archive_path = _next_available_archive_path(
        archive_snapshot_path(symbol, interval, snapshot_date, data_root=data_root)
    )
    latest_path = latest_data_path(symbol, interval, data_root=data_root)
    _ensure_parent(archive_path)
    _ensure_parent(latest_path)

    shutil.copy2(source_csv, archive_path)
    shutil.copy2(source_csv, latest_path)
    merged_path = merge_archived_snapshots(symbol, interval, data_root=data_root)

    return {
        "archive": archive_path,
        "latest": latest_path,
        "merged": merged_path,
    }


def merge_archived_snapshots(
    symbol: str,
    interval: str,
    data_root: str | os.PathLike | None = None,
) -> str:
    """Rebuild a merged long-history file from immutable archive snapshots."""
    root = Path(data_root or DATA_ROOT)
    archive_dir = root / "data" / "archive" / normalize_symbol(symbol) / interval
    merged_path = merged_data_path(symbol, interval, data_root=data_root)
    _ensure_parent(merged_path)

    csv_files = sorted(archive_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No archived snapshots found in {archive_dir}")

    frames = [_load_csv(str(path)) for path in csv_files]
    merged = pd.concat(frames)
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    merged.to_csv(merged_path)
    return merged_path


def build_all_merged(data_root: str | os.PathLike | None = None) -> list[str]:
    root = Path(data_root or DATA_ROOT)
    archive_root = root / "data" / "archive"
    built = []
    if not archive_root.exists():
        return built
    for symbol_dir in archive_root.iterdir():
        if not symbol_dir.is_dir():
            continue
        for interval_dir in symbol_dir.iterdir():
            if not interval_dir.is_dir():
                continue
            built.append(
                merge_archived_snapshots(symbol_dir.name, interval_dir.name, data_root=data_root)
            )
    return built


def _csv_time_range(path: str) -> dict:
    df = _load_csv(path)
    if df.empty:
        return {"rows": 0, "start": None, "end": None}
    return {
        "rows": len(df),
        "start": str(df.index.min()),
        "end": str(df.index.max()),
    }


def health_check_market_data(
    pairs: list[tuple[str, str]] | None = None,
    data_root: str | os.PathLike | None = None,
) -> dict:
    """Validate that latest/archive/merged layers exist and are readable."""
    pairs = pairs or [("MSTU", "15m"), ("MSTR", "15m"), ("BTC-USD", "15m")]
    checks = []

    for symbol, interval in pairs:
        latest = latest_data_path(symbol, interval, data_root=data_root)
        merged = merged_data_path(symbol, interval, data_root=data_root)
        archive_dir = Path(
            archive_snapshot_path(symbol, interval, "dummy-date", data_root=data_root)
        ).parent

        if not os.path.exists(latest):
            checks.append({"symbol": symbol, "interval": interval, "layer": "latest", "status": "missing"})
        else:
            checks.append({
                "symbol": symbol,
                "interval": interval,
                "layer": "latest",
                "status": "ok",
                **_csv_time_range(latest),
            })

        archive_files = sorted(archive_dir.glob("*.csv")) if archive_dir.exists() else []
        if not archive_files:
            checks.append({"symbol": symbol, "interval": interval, "layer": "archive", "status": "missing"})
        else:
            checks.append({
                "symbol": symbol,
                "interval": interval,
                "layer": "archive",
                "status": "ok",
                "snapshots": len(archive_files),
                "latest_snapshot": archive_files[-1].name,
            })

        if not os.path.exists(merged):
            checks.append({"symbol": symbol, "interval": interval, "layer": "merged", "status": "missing"})
        else:
            checks.append({
                "symbol": symbol,
                "interval": interval,
                "layer": "merged",
                "status": "ok",
                **_csv_time_range(merged),
            })

    status = "ok" if all(item["status"] == "ok" for item in checks) else "error"
    return {"status": status, "checks": checks}


def market_data_inventory(data_root: str | os.PathLike | None = None) -> dict:
    """Summarize tracked market data for humans and future agents."""
    root = Path(data_root or DATA_ROOT)
    archive_root = root / "data" / "archive"
    latest_root = root / "data" / "latest"
    merged_root = root / "data" / "merged"

    symbols: dict[str, dict[str, dict]] = {}

    all_symbols = set()
    if archive_root.exists():
        all_symbols.update(p.name for p in archive_root.iterdir() if p.is_dir())
    if latest_root.exists():
        all_symbols.update(p.name for p in latest_root.iterdir() if p.is_dir())
    if merged_root.exists():
        all_symbols.update(p.name for p in merged_root.iterdir() if p.is_dir())

    for symbol in sorted(all_symbols):
        symbols[symbol] = {}
        intervals = set()
        symbol_archive = archive_root / symbol
        symbol_latest = latest_root / symbol
        symbol_merged = merged_root / symbol

        if symbol_archive.exists():
            intervals.update(p.name for p in symbol_archive.iterdir() if p.is_dir())
        if symbol_latest.exists():
            intervals.update(p.stem for p in symbol_latest.glob("*.csv"))
        if symbol_merged.exists():
            intervals.update(p.stem for p in symbol_merged.glob("*.csv"))

        for interval in sorted(intervals):
            archive_dir = symbol_archive / interval
            latest_path = symbol_latest / f"{interval}.csv"
            merged_path = symbol_merged / f"{interval}.csv"
            archive_files = sorted(archive_dir.glob("*.csv")) if archive_dir.exists() else []

            summary = {
                "archive_snapshots": len(archive_files),
                "latest_rows": 0,
                "merged_rows": 0,
                "latest_start": None,
                "latest_end": None,
                "merged_start": None,
                "merged_end": None,
            }

            if latest_path.exists():
                info = _csv_time_range(str(latest_path))
                summary["latest_rows"] = info["rows"]
                summary["latest_start"] = info["start"]
                summary["latest_end"] = info["end"]

            if merged_path.exists():
                info = _csv_time_range(str(merged_path))
                summary["merged_rows"] = info["rows"]
                summary["merged_start"] = info["start"]
                summary["merged_end"] = info["end"]

            symbols[symbol][interval] = summary

    return {
        "status": "ok" if symbols else "empty",
        "symbols": symbols,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage archived market data snapshots.")
    parser.add_argument("command", choices=["merge-all", "health-check", "inventory"], help="Operation to run")
    args = parser.parse_args()

    if args.command == "merge-all":
        built = build_all_merged()
        for path in built:
            print(path)
    elif args.command == "health-check":
        import json
        print(json.dumps(health_check_market_data(), ensure_ascii=False, indent=2))
    elif args.command == "inventory":
        import json
        print(json.dumps(market_data_inventory(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
