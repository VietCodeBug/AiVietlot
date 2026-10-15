"""Run reproducible historical simulations on the server/CI and save metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

# Also works from an uninstalled checkout, without requiring shell PYTHONPATH.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "collector"))

from mega_collector.analysis import AnalysisConfig, publish_analysis, run_analysis
from mega_collector.engine import write_json
from mega_collector.storage import StorageError, SupabaseRepository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward Mega 6/45 algorithm comparison")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "analysis.json")
    parser.add_argument("--windows", type=int, nargs="+", default=[100, 300])
    parser.add_argument("--tickets-per-draw", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--min-train", type=int, default=100)
    parser.add_argument("--smoothing", type=float, default=1.0)
    parser.add_argument("--half-life", type=float, default=50.0)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--block-length", type=int, default=10)
    parser.add_argument("--no-publish", action="store_true", help="Compute/save locally without inserting analysis_runs")
    args = parser.parse_args(argv)
    load_dotenv(args.env_file, encoding="utf-8-sig", override=False)
    repository = None
    try:
        config = AnalysisConfig(windows=tuple(args.windows), tickets_per_draw=args.tickets_per_draw,
            seed_count=args.seeds, seed=args.seed, min_train=args.min_train,
            smoothing=args.smoothing, half_life=args.half_life, bootstrap_samples=args.bootstrap_samples,
            block_length=args.block_length)
        config.validate()
        url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SECRET_KEY", "")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        repository = SupabaseRepository(url, key)
        result = run_analysis(repository.list_draws(), config)
        if not args.no_publish:
            result = publish_analysis(repository, result)
        write_json(args.output, result)
        print(json.dumps({"status": "succeeded", "published": not args.no_publish,
            "id": result.get("id"), "algorithm_version": result["algorithm_version"],
            "range": result["metrics"]["range"], "windows": result["config"]["effective_windows"],
            "seed_count": config.seed_count, "tickets_per_draw": config.tickets_per_draw}))
        return 0
    except StorageError as error:
        print(json.dumps({"status": "database_error", "error": str(error)}))
        return 1
    except (ValueError, OSError):
        print(json.dumps({"status": "analysis_error", "error": "Check configuration, completed draw continuity and output path"}))
        return 1
    except Exception as error:
        print(json.dumps({"status": "internal_error", "failure_type": type(error).__name__}))
        return 1
    finally:
        if repository is not None:
            repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
