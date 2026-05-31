"""
nestifypy.yaml
-----------
Intelligent YAML configuration runtime engine with auto-bootstrap.
"""

from typing import Any, Callable, Dict, List, Optional, Union
from pathlib import Path

from nestifypy.yaml.engine import YamlEngine
from nestifypy.yaml.runtime import YamlRuntime
from nestifypy.yaml.models import DotDict
from nestifypy.yaml.exceptions import YamlPathError
from nestifypy.yaml.proxy import setup_module_proxy

# Legacy export for backwards compatibility
Yaml = YamlEngine

# ─────────────────────────────────────────────
#  Module-Level Public API (Explicit APIs)
# ─────────────────────────────────────────────

def file(path: Union[str, Path], defaults: Optional[Dict[str, Any]] = None) -> DotDict:
    return YamlEngine.file(path, defaults)

def get(*args: Any, default: Any = None) -> Any:
    return YamlEngine.get(*args, default=default)

def save(path: Union[str, Path], data: Union[Dict, DotDict]) -> None:
    YamlEngine.save(path, data)

def reload(path: Union[str, Path]) -> Optional[DotDict]:
    return YamlEngine.reload(path)

def scan(directory: Union[str, Path] = ".") -> None:
    YamlEngine.scan(directory)

def where(path: str) -> Optional[str]:
    return YamlEngine.where(path)

def paths() -> List[str]:
    return YamlEngine.paths()

def watch(enabled: bool = True) -> None:
    YamlEngine.watch(enabled)

def auto_reload(enabled: bool = True) -> None:
    YamlEngine.auto_reload(enabled)

def on_reload(callback: Callable) -> None:
    YamlEngine.on_reload(callback)

def validate(config: DotDict, schema: Dict[str, type]) -> bool:
    return YamlEngine.validate(config, schema)

def registry() -> Dict[str, str]:
    return YamlEngine.registry()

def invalidate_cache(path: Optional[Union[str, Path]] = None) -> None:
    YamlEngine.invalidate_cache(path)

# Runtime Lifecycle APIs
def bootstrap() -> None:
    YamlEngine.bootstrap()

def shutdown() -> None:
    YamlEngine.shutdown()

def runtime() -> YamlRuntime:
    return YamlEngine.runtime()

__all__ = [
    "Yaml",
    "DotDict",
    "YamlPathError",
    "file",
    "get",
    "save",
    "reload",
    "scan",
    "where",
    "paths",
    "watch",
    "auto_reload",
    "on_reload",
    "validate",
    "registry",
    "invalidate_cache",
    "bootstrap",
    "shutdown",
    "runtime",
]

# Apply magic routing (PEP 562 & __class__ replacement)
setup_module_proxy(__name__)
