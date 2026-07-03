"""VAS trajectory analysis: clustering, change points, survival, shapelets."""

__all__ = ["clustering", "change_point", "survival", "shapelets", "plotting"]


def __getattr__(name):
    if name in __all__:
        import importlib

        return importlib.import_module(f"analysis.trajectory.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
