"""
nestifypy.yaml.watcher
-------------------
Background daemon thread for hot-reloading YAML files with debounce.
"""

import threading
import time
from typing import Callable, Dict, List, Any, Optional
from pathlib import Path
from nestifypy.slogger import Logger

class YamlWatcher:
    """Manages file watching and debounced hot reloading for YAML configurations."""

    def __init__(self, engine_reload_func: Callable[[Path], None]) -> None:
        self._watching = False
        self._callbacks: List[Callable[[str], None]] = []
        self._engine_reload_func = engine_reload_func
        self._observer = None
        self._lock = threading.RLock()
        
        # Debounce tracking
        self._debounce_window = 0.1  # 100ms
        self._pending_updates: Dict[str, float] = {}
        self._debounce_thread: Optional[threading.Thread] = None

    def _debounce_worker(self) -> None:
        """Background thread to process debounced updates."""
        while self._watching:
            time.sleep(0.05)
            now = time.time()
            to_process = []
            
            with self._lock:
                for path_str, timestamp in list(self._pending_updates.items()):
                    if now - timestamp >= self._debounce_window:
                        to_process.append(path_str)
                        del self._pending_updates[path_str]
                        
            for path_str in to_process:
                self._trigger_reload(Path(path_str))

    def _trigger_reload(self, p: Path) -> None:
        Logger.info(f"[yaml.watch] Reloading {p.name}")
        try:
            self._engine_reload_func(p)
            with self._lock:
                cbs = list(self._callbacks)
            for cb in cbs:
                try:
                    cb(str(p))
                except Exception as e:
                    Logger.warn(f"[yaml.watch] Callback error: {e}")
        except Exception as e:
            Logger.warn(f"[yaml.watch] Reload failed: {e}")

    def watch(self, enabled: bool, scan_dirs: List[Path]) -> None:
        """Enable or disable hot reload on file changes."""
        with self._lock:
            if not enabled:
                self._watching = False
                if self._observer:
                    self._observer.stop()
                    self._observer.join()
                    self._observer = None
                return

            if self._watching:
                return  # already watching

            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler, FileModifiedEvent

                watcher_self = self

                class _Handler(FileSystemEventHandler):
                    def on_modified(self_, event: Any) -> None:
                        if not isinstance(event, FileModifiedEvent):
                            return
                        p = Path(event.src_path)
                        if p.suffix not in {".yml", ".yaml"}:
                            return
                        
                        # Register pending update for debounce
                        with watcher_self._lock:
                            watcher_self._pending_updates[str(p)] = time.time()

                self._observer = Observer()
                for d in scan_dirs or [Path(".")]:
                    self._observer.schedule(_Handler(), str(d), recursive=True)
                
                # Daemonize the observer thread so it doesn't block exit
                self._observer.daemon = True
                self._observer.start()
                
                self._watching = True
                
                # Start debounce worker
                self._debounce_thread = threading.Thread(target=self._debounce_worker, daemon=True)
                self._debounce_thread.start()
                
                # Logger.info("[yaml.watch] Hot reload enabled")

            except ImportError:
                Logger.warn(
                    "[Nestifypy:Yaml] Watchdog not installed. "
                    "Hot reload functionality is disabled. "
                    "Install 'watchdog' to enable automatic file watching."
                )

    def on_reload(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked when any YAML file is reloaded."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
