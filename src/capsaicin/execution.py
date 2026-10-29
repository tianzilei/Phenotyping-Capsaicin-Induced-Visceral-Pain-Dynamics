"""Optional execution telemetry, separate from statistical output."""


def memory_usage():
    try:
        import psutil
    except ImportError:
        return {"resource_monitoring": "unavailable"}
    return {
        "rss_bytes": psutil.Process().memory_info().rss,
        "resource_monitoring": "available",
    }
