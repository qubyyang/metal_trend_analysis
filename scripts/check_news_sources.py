#!/usr/bin/env python3
"""Check configured news sources and print item counts.

This is a CLI diagnostic script, not a pytest test module. It is deliberately
named ``check_*`` so pytest does not attempt to collect ``check_sources`` as a
test function (which would fail on the unresolvable ``fetcher`` fixture).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config_loader import ConfigLoader
from src.data_fetchers.news_fetcher import NewsFetcher


def resolve_config_path(config_arg: str | None) -> Path:
    if config_arg:
        return Path(config_arg)

    for candidate in ("config/config.yaml", "config/config.yaml.example"):
        path = Path(candidate)
        if path.exists():
            return path

    raise FileNotFoundError("未找到 config/config.yaml 或 config/config.yaml.example")


def load_config(config_path: Path) -> Dict[str, Any]:
    loader = ConfigLoader(config_dir=str(config_path.parent))
    return loader.load_main_config(config_path.name)


def check_sources(fetcher: NewsFetcher) -> List[Tuple[str, str, int]]:
    results: List[Tuple[str, str, int]] = []

    for source in fetcher.sources:
        if not source.get("enabled", True):
            continue

        try:
            if source.get("type") == "rss":
                articles = fetcher._fetch_rss(source)
            elif source.get("type") == "api":
                articles = fetcher._fetch_api(source)
            elif source.get("type") == "html":
                articles = fetcher._fetch_html(source)
            else:
                results.append((source.get("name", "unknown"), "unknown type", 0))
                continue

            status = "ok" if articles else "empty"
            results.append((source.get("name", "unknown"), status, len(articles)))
        except Exception as exc:  # pragma: no cover - defensive guard
            results.append((source.get("name", "unknown"), f"error: {exc}", 0))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Check news sources in config")
    parser.add_argument("--config", type=str, default=None, help="Config path")
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    news_config = config.get("news", {})

    fetcher = NewsFetcher(config=news_config, keywords=[])
    fetcher.fetch_config["delay"] = 0

    results = check_sources(fetcher)

    print("News source check results:")
    for name, status, count in results:
        print(f"- {name}: {status}, items={count}")

    has_error = any(status.startswith("error") for _, status, _ in results)
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
