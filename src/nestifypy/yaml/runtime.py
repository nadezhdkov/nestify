"""
nestifypy.yaml.runtime
-------------------
Singleton runtime state manager for the YAML engine.
"""

from pathlib import Path
import threading

from nestifypy.yaml.registry import PathRegistry
from nestifypy.yaml.cache import ConfigCache
from nestifypy.yaml.metadata import MetadataManager
from nestifypy.yaml.scanner import YamlScanner
from nestifypy.yaml.watcher import YamlWatcher
from nestifypy.yaml.bootstrap import discover_project_root
from nestifypy.yaml.models import DotDict

class YamlRuntime:
    """Manages the lifecycle, state, and auto-bootstrap of the YAML engine."""
    
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self) -> None:
        self.is_initialized = False
        self.project_root: Path = Path(".")
        
        self.registry = PathRegistry()
        self.cache = ConfigCache()
        
        # Will be initialized in bootstrap
        self.metadata = None
        self.scanner = None
        
        # Watcher needs a reload callback
        self.watcher = YamlWatcher(self._reload_file)

    def _reload_file(self, filepath: Path) -> None:
        """Callback for the watcher to reload a file."""
        if self.scanner:
            self.scanner.reload_file(filepath)

    def ensure_initialized(self) -> None:
        """Lazy auto-bootstrap. Called before any engine operation."""
        if self.is_initialized:
            return
            
        with self._lock:
            if self.is_initialized:
                return
            self.bootstrap()

    def bootstrap(self) -> None:
        """Perform the actual bootstrap sequence."""
        # 1. Project discovery
        self.project_root = discover_project_root(Path("."))
        
        # 2. Metadata manager
        self.metadata = MetadataManager(self.project_root)
        self.metadata.load_metadata()
        
        # 3. Load persistent registry cache
        index_data = self.metadata.load_index()
        self.registry.load_from_dict(index_data)
        
        # 4. Scanner
        self.scanner = YamlScanner(self.registry, self.cache, self.metadata)
        
        # 5. Incremental Scan
        self.scanner.scan(self.project_root)
        
        # 6. Initialize watcher automatically (autonomous hot-reload)
        self.watcher.watch(True, [self.project_root])
        
        self.is_initialized = True

    def shutdown(self) -> None:
        """Gracefully shut down watchers and clear memory."""
        with self._lock:
            self.watcher.watch(False, [])
            self.cache.clear()
            self.registry.clear()
            if self.metadata:
                self.metadata.clear()
            self.is_initialized = False
