"""
nestifypy.yaml.engine
------------------
Main YAML engine wrapping the runtime singleton.
"""

from __future__ import annotations

import typing
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import yaml as _yaml
except ImportError:
    pass

from nestifypy.slogger import ConfigError, Logger
from nestifypy.yaml.models import DotDict
from nestifypy.yaml.runtime import YamlRuntime


class YamlEngine:
    """
    Public API implementation wrapping the internal YamlRuntime.
    Provides lazy bootstrap automatically.
    """

    @classmethod
    def runtime(cls) -> YamlRuntime:
        """Access the runtime singleton."""
        rt = YamlRuntime()
        return rt

    @classmethod
    def bootstrap(cls) -> None:
        """Force manual bootstrap of the runtime."""
        rt = YamlRuntime()
        if not rt.is_initialized:
            rt.bootstrap()

    @classmethod
    def shutdown(cls) -> None:
        """Gracefully shutdown the runtime."""
        YamlRuntime().shutdown()

    # ── File loading ──────────────────────────

    @classmethod
    def file(
        cls,
        path: str | Path,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> DotDict:
        """Load and return a YAML file as a DotDict."""
        rt = cls.runtime()
        rt.ensure_initialized()
        p = Path(path)
        key = str(p.resolve())

        config = rt.cache.get(key)
        if config is None:
            config = cls._load_file(p, defaults)
            rt.cache.set(key, config)
            rt.registry.index_file(p, config.to_dict())

        return config

    @classmethod
    def _load_file(
        cls,
        path: Path,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> DotDict:
        if not path.exists():
            raise ConfigError(f"YAML file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
        if defaults:
            merged = {**defaults, **raw}
        else:
            merged = raw
        return DotDict(merged)

    # ── Global access ─────────────────────────

    @classmethod
    def get(cls, *args: Any, default: Any = None) -> Any:
        """Get a value by dot-path, with optional explicit file."""
        rt = cls.runtime()
        rt.ensure_initialized()
        
        if len(args) == 1:
            path: str = args[0]
            val = cls._global_get(rt, path)
            if val is None:
                return default
            return val
        elif len(args) == 2:
            filepath, path = args
            config = cls.file(filepath)
            return config.get(path, default)
        else:
            raise TypeError("Yaml.get() takes 1 or 2 positional arguments")

    @classmethod
    def _global_get(cls, rt: YamlRuntime, path: str) -> Any:
        """Resolve a path globally across all indexed files."""
        filename = rt.registry.find(path)
        if filename is None:
            return None
        config = rt.cache.get(filename)
        if config is None:
            # We have it in registry but not cache (lazy loading!)
            config = cls.file(filename)
            if config is None:
                return None
        return config.get(path, None)

    # ── Saving ────────────────────────────────

    @classmethod
    def save(cls, path: str | Path, data: Union[Dict, DotDict]) -> None:
        """Serialize and write data to a YAML file."""
        # Does not necessarily require bootstrap if they just want to save
        p = Path(path)
        raw = data.to_dict() if isinstance(data, DotDict) else data
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            _yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)
        Logger.info(f"Saved YAML → {p}")
        
        # If initialized, reload it
        rt = YamlRuntime()
        if rt.is_initialized:
            cls.reload(path)

    # ── Reload ────────────────────────────────

    @classmethod
    def reload(cls, path: str | Path) -> Optional[DotDict]:
        """Force reload a cached YAML file."""
        rt = YamlRuntime()
        if not rt.is_initialized:
            return None
        
        if rt.scanner:
            return rt.scanner.reload_file(Path(path))
        return None

    # ── Scan & Index ──────────────────────────

    @classmethod
    def scan(cls, directory: str | Path = ".") -> None:
        """Scan a directory for YAML files and index them."""
        rt = cls.runtime()
        rt.ensure_initialized()
        if rt.scanner:
            rt.scanner.scan(Path(directory))

    # ── Where ─────────────────────────────────

    @classmethod
    def where(cls, path: str) -> Optional[str]:
        """Return which file owns a given dot-path."""
        rt = cls.runtime()
        rt.ensure_initialized()
        return rt.registry.find(path)

    # ── Paths ─────────────────────────────────

    @classmethod
    def paths(cls) -> List[str]:
        """Return all indexed dot-paths."""
        rt = cls.runtime()
        rt.ensure_initialized()
        return rt.registry.all_paths()

    # ── Watch ─────────────────────────────────

    @classmethod
    def watch(cls, enabled: bool = True) -> None:
        """Enable or disable watcher explicitly."""
        rt = cls.runtime()
        rt.ensure_initialized()
        rt.watcher.watch(enabled, [rt.project_root])

    @classmethod
    def auto_reload(cls, enabled: bool = True) -> None:
        """Alias for watch() to enable or disable hot reload."""
        cls.watch(enabled)

    @classmethod
    def on_reload(cls, callback: typing.Callable) -> None:
        rt = cls.runtime()
        rt.ensure_initialized()
        rt.watcher.on_reload(callback)

    # ── Validation ────────────────────────────

    @classmethod
    def validate(
        cls,
        config: DotDict,
        schema: Dict[str, type],
    ) -> bool:
        """Validate a DotDict against a flat schema dict."""
        errors: List[str] = []
        for key, expected_type in schema.items():
            value = config.get(key)
            if value is None:
                errors.append(f"Missing required key: '{key}'")
            elif not isinstance(value, expected_type):
                errors.append(
                    f"Key '{key}' must be {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        if errors:
            raise ConfigError("YAML validation failed:\n" + "\n".join(errors))
        return True

    # ── Cache Management ──────────────────────

    @classmethod
    def invalidate_cache(cls, path: Optional[Union[str, Path]] = None) -> None:
        rt = cls.runtime()
        if path:
            absolute_path = str(Path(path).resolve())
            rt.cache.remove(absolute_path)
            rt.registry.remove_file(absolute_path)
            if rt.metadata:
                rt.metadata.remove_file_meta(absolute_path)
        else:
            rt.cache.clear()
            rt.registry.clear()
            if rt.metadata:
                rt.metadata.clear()

    @classmethod
    def registry(cls) -> Dict[str, str]:
        """Return the internal path → file index."""
        rt = cls.runtime()
        rt.ensure_initialized()
        return rt.registry.to_dict()
