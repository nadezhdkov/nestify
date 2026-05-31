"""
nestifypy.json.serializer
-------------------------
Serialisation logic: Python → JSON string / file.

Improvements over the original
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``NestifyEncoder`` handles ``datetime``, ``date``, ``UUID``, ``Enum``,
  ``Path``, ``dataclass``, ``set``, ``frozenset``, ``bytes``, and any class
  decorated with ``@json_serializable`` — automatically, with no boilerplate.
* ``safe_save`` writes atomically via a sibling temp file + ``os.replace()``.
* Custom encoder / decoder registration via ``JsonSerializer.register_encoder``
  and ``JsonSerializer.register_decoder``.
* ``Logger`` call is now optional (only when a logger is available).
"""
from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Type, Union
from uuid import UUID


# ---------------------------------------------------------------------------
# Custom JSON encoder
# ---------------------------------------------------------------------------

class NestifyEncoder(json.JSONEncoder):
    """
    Extended JSON encoder that handles types the stdlib encoder rejects.

    Supported out-of-the-box
    ~~~~~~~~~~~~~~~~~~~~~~~~
    * ``datetime`` / ``date``       → ISO 8601 string
    * ``UUID``                      → str
    * ``Enum``                      → ``.value``
    * ``Path``                      → POSIX string
    * ``dataclass``                 → ``dataclasses.asdict()``
    * ``set`` / ``frozenset``       → sorted list
    * ``bytes``                     → base-64 string
    * ``@json_serializable`` class  → ``.to_dict()``

    Extend via ``JsonSerializer.register_encoder(MyType, my_fn)``.
    """

    # Class-level registry: type → callable(value) → JSON-safe value
    _registry: Dict[Type, Callable[[Any], Any]] = {}

    def default(self, obj: Any) -> Any:
        # User-registered encoders take highest priority
        for typ, fn in self.__class__._registry.items():
            if isinstance(obj, typ):
                return fn(obj)

        # @json_serializable objects
        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return obj.to_dict()

        # datetime before date (datetime IS-A date)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()

        if isinstance(obj, UUID):
            return str(obj)

        if isinstance(obj, Enum):
            return obj.value

        if isinstance(obj, Path):
            return obj.as_posix()

        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)

        if isinstance(obj, (set, frozenset)):
            return sorted(obj, key=str)

        if isinstance(obj, bytes):
            import base64
            return base64.b64encode(obj).decode("ascii")

        return super().default(obj)


# ---------------------------------------------------------------------------
# JsonSerializer
# ---------------------------------------------------------------------------

class JsonSerializer:
    """Serialise Python objects to JSON strings and files."""

    # ------------------------------------------------------------------
    # Encoder / decoder registration
    # ------------------------------------------------------------------

    @classmethod
    def register_encoder(cls, typ: Type, fn: Callable[[Any], Any]) -> None:
        """
        Register a custom serialiser for *typ*.

        Example::

            import numpy as np
            JsonSerializer.register_encoder(np.ndarray, lambda a: a.tolist())
        """
        NestifyEncoder._registry[typ] = fn

    # ------------------------------------------------------------------
    # String serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def stringify(
        data: Any,
        *,
        pretty: bool = False,
        sort_keys: bool = False,
        ensure_ascii: bool = False,
    ) -> str:
        """
        Serialise *data* to a JSON string.

        Parameters
        ----------
        pretty:
            Use 2-space indentation.
        sort_keys:
            Sort object keys alphabetically.
        ensure_ascii:
            Escape non-ASCII characters.
        """
        try:
            return json.dumps(
                data,
                cls=NestifyEncoder,
                indent=2 if pretty else None,
                sort_keys=sort_keys,
                ensure_ascii=ensure_ascii,
            )
        except (TypeError, ValueError) as exc:
            from nestifypy.json.exceptions import JsonSerializationError
            raise JsonSerializationError(f"Cannot serialise object to JSON: {exc}") from exc

    # ------------------------------------------------------------------
    # File serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def save(
        path: Union[str, Path],
        data: Any,
        *,
        pretty: bool = True,
        sort_keys: bool = False,
        ensure_ascii: bool = False,
    ) -> None:
        """
        Write *data* to a JSON file (standard, non-atomic).

        Parent directories are created automatically.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(
                    data,
                    fh,
                    cls=NestifyEncoder,
                    indent=2 if pretty else None,
                    sort_keys=sort_keys,
                    ensure_ascii=ensure_ascii,
                )
        except (TypeError, ValueError) as exc:
            from nestifypy.json.exceptions import JsonSerializationError
            raise JsonSerializationError(f"Cannot serialise object to JSON: {exc}") from exc

        try:
            from nestifypy.slogger import Logger
            Logger.info(f"Saved JSON → {p}")
        except Exception:
            pass

    @staticmethod
    def safe_save(
        path: Union[str, Path],
        data: Any,
        *,
        pretty: bool = True,
        sort_keys: bool = False,
        ensure_ascii: bool = False,
    ) -> None:
        """
        **Atomically** write *data* to a JSON file.

        Writes to a sibling temp file first, then uses ``os.replace()`` to
        swap it in.  The destination is never partially written even if the
        process is interrupted mid-write.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    data,
                    fh,
                    cls=NestifyEncoder,
                    indent=2 if pretty else None,
                    sort_keys=sort_keys,
                    ensure_ascii=ensure_ascii,
                )
            os.replace(tmp_path, p)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        try:
            from nestifypy.slogger import Logger
            Logger.info(f"Safe-saved JSON → {p}")
        except Exception:
            pass

    # Backwards-compatible alias
    save_file = save


__all__ = ["JsonSerializer", "NestifyEncoder"]
