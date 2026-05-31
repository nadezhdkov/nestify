"""
nestifypy.yaml.scanner
-------------------
Incremental filesystem scanner for YAML configurations.
"""

import os
from pathlib import Path
from typing import Callable, List, Optional
try:
    import yaml as _yaml
except ImportError:
    pass

from nestifypy.slogger import Logger
from nestifypy.yaml.models import DotDict
from nestifypy.yaml.registry import PathRegistry
from nestifypy.yaml.cache import ConfigCache
from nestifypy.yaml.metadata import MetadataManager

class YamlScanner:
    """Handles discovering and incrementally scanning YAML files."""

    __slots__ = ("registry", "cache", "metadata", "scan_dirs")

    def __init__(
        self,
        registry: PathRegistry,
        cache: ConfigCache,
        metadata: MetadataManager
    ) -> None:
        self.registry = registry
        self.cache = cache
        self.metadata = metadata
        self.scan_dirs: List[Path] = []

    def _get_mtime(self, filepath: Path) -> float:
        return filepath.stat().st_mtime

    def _load_raw(self, filepath: Path) -> DotDict:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
        return DotDict(raw)

    def scan(self, directory: Path) -> None:
        """Incrementally scan a directory and update the registry/cache."""
        d = directory.resolve()
        if d not in self.scan_dirs:
            self.scan_dirs.append(d)

        # Track seen files to remove deleted ones
        seen_files = set()

        for yml_file in d.rglob("*.yml"):
            if any(part.startswith(".") for part in yml_file.parts):
                continue

            absolute_path = str(yml_file.resolve())
            seen_files.add(absolute_path)

            try:
                current_mtime = self._get_mtime(yml_file)
                
                # Check if modified
                if self.metadata.is_modified(absolute_path, current_mtime):
                    # Load, cache, index
                    cfg = self._load_raw(yml_file)
                    self.cache.set(absolute_path, cfg)
                    self.registry.index_file(yml_file, cfg.to_dict())
                    
                    # Compute hash (simple content hash or just rely on mtime for now to save CPU)
                    # We will just use mtime and empty hash for performance unless requested otherwise
                    self.metadata.update_file_meta(absolute_path, current_mtime, "")
                    
            except Exception as e:
                Logger.warn(f"Could not scan {yml_file}: {e}")

        # Remove deleted files from metadata and registry
        # We only check files that were previously in this directory tree
        known_files = list(self.metadata._metadata.keys())
        for fpath in known_files:
            if fpath.startswith(str(d)) and fpath not in seen_files:
                self.registry.remove_file(fpath)
                self.cache.remove(fpath)
                self.metadata.remove_file_meta(fpath)

        # Save metadata to disk
        self.metadata.save_metadata()
        self.metadata.save_index(self.registry.to_dict())

    def reload_file(self, filepath: Path) -> Optional[DotDict]:
        """Force reload a single file and update indices."""
        absolute_path = str(filepath.resolve())
        try:
            current_mtime = self._get_mtime(filepath)
            cfg = self._load_raw(filepath)
            
            self.cache.set(absolute_path, cfg)
            self.registry.index_file(filepath, cfg.to_dict())
            self.metadata.update_file_meta(absolute_path, current_mtime, "")
            
            self.metadata.save_metadata()
            self.metadata.save_index(self.registry.to_dict())
            return cfg
        except Exception as e:
            Logger.warn(f"Could not reload {filepath}: {e}")
            return None
