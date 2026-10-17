"""Command line: ``python -m pipeline [--snapshots 2024 2025 2026] [--refresh] [--skip-extract]``."""
import argparse
import logging
import time

from . import config, extract, load, transform, validate


def main() -> None:
    p = argparse.ArgumentParser(description="WBG Scorecard data pipeline (extract -> transform -> load -> validate)")
    p.add_argument("--snapshots", nargs="+", type=int, default=config.SNAPSHOTS, help="Scorecard snapshot FYs")
    p.add_argument("--refresh", action="store_true", help="re-download raw files even if cached")
    p.add_argument("--skip-extract", action="store_true", help="rebuild from cached raw files only")
    p.add_argument("--countries-limit", type=int, help="only the first N countries (quick test runs)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    t0 = time.time()
    if not args.skip_extract:
        extract.run(args.snapshots, args.refresh, args.countries_limit)
    tables = transform.run(args.snapshots)
    load.run(tables)
    report = validate.run()
    counts = {r["t"]: r["n"] for r in report["row_counts"]}
    print(f"\nDone in {time.time() - t0:.0f}s -> {config.DB_PATH}")
    print("rows:", counts)
    print("snapshots:", [(r["snapshot_fy"], r["snapshot_date"][:10]) for r in report["snapshots"]])
    print(f"data-quality: {len(report['duplicate_result_keys'])} duplicate keys, "
          f"{len(report['achieved_above_expected'])} achieved>expected rows, "
          f"{len(report['results_without_total'])} indicators without a world total, "
          f"{len(report['regions_vs_world'])} region-sum mismatches -> data/processed/data_quality.json")


if __name__ == "__main__":
    main()
