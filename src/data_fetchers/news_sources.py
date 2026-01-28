"""
News Sources Module
"""
from typing import List, Dict, Any


def get_news_sources_from_config(config: Dict[str, Any], enabled_only: bool = True) -> List[Dict[str, Any]]:
    """
    Get news sources from configuration

    Args:
        config: News configuration dictionary
        enabled_only: If True, only return enabled sources

    Returns:
        List of news source configurations
    """
    sources = config.get('sources', [])

    if enabled_only:
        return [source for source in sources if source.get('enabled', True)]
    else:
        return sources.copy()
