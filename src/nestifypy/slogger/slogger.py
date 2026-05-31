"""
nestifypy.slogger
-----------------
SLogger – System Logger for the Nestifypy framework.

A professional, colorful, decorator-aware logger designed to be reusable
in any Python project – from a first "Hello, World!" to a full-scale app.

Features
--------
- Colored, leveled output with ANSI codes
- Optional ASCII art title banner (Nestifypy logo)
- Custom prefixes, timestamps, and file output
- @log, @trace, and @catch decorators
- Pluggable formatters
- Context managers for temporary settings
- Thread-safe file writing
- Zero external dependencies
"""

from __future__ import annotations

import functools
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, TextIO, Type, TypeVar, Union

F = TypeVar("F", bound=Callable[..., Any])


# ─────────────────────────────────────────────────────────────────────────────
#  ANSI palette
# ─────────────────────────────────────────────────────────────────────────────

class _C:
    """Raw ANSI escape sequences."""
    RST  = "\033[0m"
    BOLD = "\033[1m"
    DIM  = "\033[2m"
    ITAL = "\033[3m"

    BLK  = "\033[30m"
    RED  = "\033[31m"
    GRN  = "\033[32m"
    YEL  = "\033[33m"
    BLU  = "\033[34m"
    MAG  = "\033[35m"
    CYN  = "\033[36m"
    WHT  = "\033[37m"

    BRED = "\033[91m"
    BGRN = "\033[92m"
    BYEL = "\033[93m"
    BBLU = "\033[94m"
    BMAG = "\033[95m"
    BCYN = "\033[96m"
    BWHT = "\033[97m"

    BG_BLK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GRN = "\033[42m"
    BG_YEL = "\033[43m"
    BG_BLU = "\033[44m"
    BG_MAG = "\033[45m"
    BG_CYN = "\033[46m"


def _strip(text: str) -> str:
    """Remove all ANSI codes from a string."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ─────────────────────────────────────────────────────────────────────────────
#  LogLevel
# ─────────────────────────────────────────────────────────────────────────────

class LogLevel(IntEnum):
    """Numeric log levels. Higher value = more severe."""
    TRACE   = 0
    DEBUG   = 1
    INFO    = 2
    SUCCESS = 3
    WARN    = 4
    ERROR   = 5
    FATAL   = 6
    OFF     = 99  # Silence everything


_LEVEL_STYLES: dict[LogLevel, tuple[str, str]] = {
    #                 tag-label   color
    LogLevel.TRACE:   ("TRACE", _C.DIM  + _C.CYN),
    LogLevel.DEBUG:   ("DEBUG", _C.CYN),
    LogLevel.INFO:    ("INFO ", _C.BLU),
    LogLevel.SUCCESS: (" OK  ", _C.BGRN),
    LogLevel.WARN:    ("WARN ", _C.BYEL),
    LogLevel.ERROR:   ("ERROR", _C.BRED),
    LogLevel.FATAL:   ("FATAL", _C.BOLD + _C.BG_RED + _C.BWHT),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Formatter protocol
# ─────────────────────────────────────────────────────────────────────────────

class Formatter:
    """
    Base formatter. Subclass and override ``format`` to customise output.

    Parameters
    ----------
    show_timestamp : bool
        Include HH:MM:SS timestamp.
    show_prefix : bool
        Include the logger prefix/name.
    show_level : bool
        Include the level tag.
    """

    def __init__(
        self,
        show_timestamp: bool = True,
        show_prefix: bool = True,
        show_level: bool = True,
    ) -> None:
        self.show_timestamp = show_timestamp
        self.show_prefix    = show_prefix
        self.show_level     = show_level

    def format(
        self,
        level: LogLevel,
        prefix: str,
        message: str,
        timestamp: str,
    ) -> str:
        label, color = _LEVEL_STYLES[level]
        parts: list[str] = []

        if self.show_timestamp:
            parts.append(f"{_C.DIM}[{timestamp}]{_C.RST}")
        if self.show_level:
            parts.append(f"{color}{_C.BOLD}[{label}]{_C.RST}")
        if self.show_prefix:
            parts.append(f"{_C.DIM}[{prefix}]{_C.RST}")

        parts.append(message)
        return " ".join(parts)

    def format_plain(
        self,
        level: LogLevel,
        prefix: str,
        message: str,
        timestamp: str,
    ) -> str:
        """Plain (no ANSI) version for file writing."""
        label, _ = _LEVEL_STYLES[level]
        return f"[{timestamp}] [{label.strip()}] [{prefix}] {message}"


class SimpleFormatter(Formatter):
    """Minimal formatter: level + message only, no timestamp or prefix."""

    def format(self, level: LogLevel, prefix: str, message: str, timestamp: str) -> str:
        label, color = _LEVEL_STYLES[level]
        return f"{color}{_C.BOLD}[{label}]{_C.RST} {message}"


class JSONFormatter(Formatter):
    """Outputs each log line as a JSON object (useful for log ingestion)."""

    def format(self, level: LogLevel, prefix: str, message: str, timestamp: str) -> str:
        import json
        label, _ = _LEVEL_STYLES[level]
        obj = {
            "ts": timestamp,
            "level": label.strip(),
            "prefix": prefix,
            "msg": message,
        }
        return json.dumps(obj, ensure_ascii=False)

    def format_plain(self, level: LogLevel, prefix: str, message: str, timestamp: str) -> str:
        return self.format(level, prefix, message, timestamp)


# ─────────────────────────────────────────────────────────────────────────────
#  Nestifypy ASCII banner
# ─────────────────────────────────────────────────────────────────────────────

_BANNER = r"""
 ███╗   ██╗███████╗███████╗████████╗██╗███████╗██╗   ██╗██████╗ ██╗   ██╗
 ████╗  ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝╚██╗ ██╔╝██╔══██╗╚██╗ ██╔╝
 ██╔██╗ ██║█████╗  ███████╗   ██║   ██║█████╗   ╚████╔╝ ██████╔╝ ╚████╔╝ 
 ██║╚██╗██║██╔══╝  ╚════██║   ██║   ██║██╔══╝    ╚██╔╝  ██╔═══╝   ╚██╔╝  
 ██║ ╚████║███████╗███████║   ██║   ██║██║        ██║   ██║        ██║   
 ╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   ╚═╝╚═╝        ╚═╝   ╚═╝        ╚═╝   
"""

_BANNER_SUBTITLE = "  System Logger  ·  slogger  ·  v2.0.0"

_BANNER_COMPACT = r"""
  ╔╗╔┌─┐┌─┐┌┬┐┬┌─┐┬ ┬┌─┐┬ ┬
  ║║║├┤ └─┐ │ │├┤ └┬┘├─┘└┬┘
  ╝╚╝└─┘└─┘ ┴ ┴└   ┴ ┴   ┴ 
"""


def _print_banner(stream: TextIO = sys.stdout, compact: bool = False) -> None:
    banner = _BANNER_COMPACT if compact else _BANNER
    print(_C.BOLD + _C.BCYN + banner + _C.RST, file=stream)
    if not compact:
        print(_C.DIM + _C.CYN + _BANNER_SUBTITLE + _C.RST + "\n", file=stream)


# ─────────────────────────────────────────────────────────────────────────────
#  SLogger – main class
# ─────────────────────────────────────────────────────────────────────────────

class SLogger:
    """
    System Logger for Nestifypy.

    Can be used as a global singleton (``SLogger.<method>``) or
    instantiated per-module with a custom prefix.

    Quick start
    -----------
    ::

        from nestifypy.slogger import SLogger, LogLevel

        log = SLogger("my_app")
        log.info("Hello, world!")
        log.warn("Something looks off…")

    Or use the global logger:
    ::

        SLogger.set_prefix("app")
        SLogger.info("Running.")

    Decorators
    ----------
    ::

        @SLogger.log(level=LogLevel.DEBUG)
        def my_func(x):
            return x * 2

        @SLogger.trace
        def risky():
            raise ValueError("oops")

        @SLogger.catch(default=-1)
        def might_fail():
            return int("abc")
    """

    # ── class-level (singleton) state ──────────────────────────────────────
    _level:     LogLevel   = LogLevel.DEBUG
    _prefix:    str        = "nestifypy"
    _file_path: Optional[Path] = None
    _formatter: Formatter  = Formatter()
    _stream:    TextIO     = sys.stdout
    _lock:      threading.Lock = threading.Lock()
    _enabled:   bool       = True

    # ── instance state ──────────────────────────────────────────────────────
    def __init__(
        self,
        prefix: str = "nestifypy",
        level: LogLevel = LogLevel.DEBUG,
        formatter: Optional[Formatter] = None,
        file: Optional[Union[str, Path]] = None,
        show_banner: bool = False,
        compact_banner: bool = False,
    ) -> None:
        self._inst_prefix    = prefix
        self._inst_level     = level
        self._inst_formatter = formatter or Formatter()
        self._inst_file      = Path(file) if file else None
        self._inst_lock      = threading.Lock()

        if show_banner:
            _print_banner(compact=compact_banner)

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _write_file(self, plain: str, path: Optional[Path]) -> None:
        if path:
            with self._inst_lock:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(plain + "\n")

    # ── instance logging ────────────────────────────────────────────────────

    def _emit(self, level: LogLevel, *args: Any) -> None:
        if level < self._inst_level:
            return
        msg   = " ".join(str(a) for a in args)
        ts    = self._now()
        line  = self._inst_formatter.format(level, self._inst_prefix, msg, ts)
        plain = self._inst_formatter.format_plain(level, self._inst_prefix, msg, ts)
        print(line, file=self._stream)
        self._write_file(plain, self._inst_file)

    def trace(self, *args: Any)   -> None: self._emit(LogLevel.TRACE,   *args)
    def debug(self, *args: Any)   -> None: self._emit(LogLevel.DEBUG,   *args)
    def info(self, *args: Any)    -> None: self._emit(LogLevel.INFO,    *args)
    def success(self, *args: Any) -> None: self._emit(LogLevel.SUCCESS, *args)
    def warn(self, *args: Any)    -> None: self._emit(LogLevel.WARN,    *args)
    def error(self, *args: Any)   -> None: self._emit(LogLevel.ERROR,   *args)
    def fatal(self, *args: Any)   -> None: self._emit(LogLevel.FATAL,   *args)

    def exception(self, *args: Any) -> None:
        """Log at ERROR level and append the current traceback."""
        self._emit(LogLevel.ERROR, *args)
        tb = traceback.format_exc()
        if tb.strip() != "NoneType: None":
            for line in tb.splitlines():
                self._emit(LogLevel.ERROR, _C.DIM + line + _C.RST)

    def path_trace(self, path: Union[str, Path]) -> None:
        """
        Log the resolved, absolute path with existence status.

        ::

            log.path_trace("./config/settings.toml")
            # [INFO ] [app] 📂 ./config/settings.toml
            #         → /home/user/project/config/settings.toml  ✓ exists
        """
        p = Path(path)
        exists  = p.exists()
        kind    = "file" if p.is_file() else ("dir" if p.is_dir() else "?")
        icon    = "📄" if p.is_file() else ("📁" if p.is_dir() else "❓")
        status  = _C.BGRN + "✓ exists" + _C.RST if exists else _C.BRED + "✗ not found" + _C.RST
        self._emit(LogLevel.INFO, f"{icon} {path}")
        self._emit(LogLevel.TRACE, f"    → {p.resolve()}  [{kind}]  {status}")

    def ruler(self, char: str = "─", width: int = 60, label: str = "") -> None:
        """Print a horizontal divider, optionally with a centred label."""
        if label:
            pad   = max(0, (width - len(label) - 2) // 2)
            line  = char * pad + f" {label} " + char * pad
        else:
            line  = char * width
        print(_C.DIM + line + _C.RST, file=self._stream)

    def banner(self, compact: bool = False) -> None:
        """Print the Nestifypy ASCII banner to the stream."""
        _print_banner(stream=self._stream, compact=compact)

    # ── instance context manager ─────────────────────────────────────────────

    @contextmanager
    def level_context(self, level: LogLevel) -> Iterator[None]:
        """Temporarily change this instance's log level."""
        old = self._inst_level
        self._inst_level = level
        try:
            yield
        finally:
            self._inst_level = old

    # ── instance decorators ──────────────────────────────────────────────────

    def log_calls(
        self,
        level: LogLevel = LogLevel.DEBUG,
        show_args: bool = True,
        show_return: bool = False,
        show_time: bool = True,
    ) -> Callable[[F], F]:
        """
        Decorator: log function entry, optional args, optional return value,
        and optional elapsed time.

        ::

            log = SLogger("app")

            @log.log_calls(level=LogLevel.DEBUG, show_return=True)
            def add(a, b):
                return a + b
        """
        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                name = fn.__qualname__
                if show_args:
                    arg_str = ", ".join(
                        [repr(a) for a in args] +
                        [f"{k}={v!r}" for k, v in kwargs.items()]
                    )
                    self._emit(level, f"→ {name}({arg_str})")
                else:
                    self._emit(level, f"→ {name}(…)")

                t0  = time.perf_counter()
                ret = fn(*args, **kwargs)
                elapsed = time.perf_counter() - t0

                parts = [f"← {name}"]
                if show_return:
                    parts.append(f"= {ret!r}")
                if show_time:
                    parts.append(f"({elapsed * 1000:.2f} ms)")
                self._emit(level, " ".join(parts))
                return ret
            return wrapper  # type: ignore
        return decorator

    def catch_errors(
        self,
        *exceptions: Type[BaseException],
        default: Any = None,
        reraise: bool = False,
        level: LogLevel = LogLevel.ERROR,
    ) -> Callable[[F], F]:
        """
        Decorator: catch specified exceptions (default: Exception), log them,
        and return ``default`` or re-raise.

        ::

            @log.catch_errors(ValueError, default=0)
            def parse(s):
                return int(s)
        """
        caught = exceptions or (Exception,)

        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except caught as exc:  # type: ignore[misc]
                    self._emit(level, f"{fn.__qualname__} raised {type(exc).__name__}: {exc}")
                    tb = traceback.format_exc()
                    for line in tb.splitlines():
                        self._emit(LogLevel.TRACE, _C.DIM + line + _C.RST)
                    if reraise:
                        raise
                    return default
            return wrapper  # type: ignore
        return decorator

    def time_it(
        self,
        label: Optional[str] = None,
        level: LogLevel = LogLevel.INFO,
    ) -> Callable[[F], F]:
        """
        Decorator: measure and log execution time.

        ::

            @log.time_it(label="heavy task")
            def crunch():
                ...
        """
        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                tag = label or fn.__qualname__
                t0  = time.perf_counter()
                ret = fn(*args, **kwargs)
                ms  = (time.perf_counter() - t0) * 1000
                self._emit(level, f"⏱  {tag} completed in {ms:.2f} ms")
                return ret
            return wrapper  # type: ignore
        return decorator

    # ── class-level (global) API ────────────────────────────────────────────
    # These mirror the instance API but operate on a shared singleton state.

    @classmethod
    def set_level(cls, level: LogLevel) -> None:
        """Set the global minimum log level."""
        cls._level = level

    @classmethod
    def set_prefix(cls, prefix: str) -> None:
        """Set the global logger prefix (app name)."""
        cls._prefix = prefix

    @classmethod
    def set_file(cls, path: Union[str, Path]) -> None:
        """Direct global logs to a file (appends)."""
        cls._file_path = Path(path)

    @classmethod
    def set_formatter(cls, formatter: Formatter) -> None:
        """Replace the global formatter."""
        cls._formatter = formatter

    @classmethod
    def set_stream(cls, stream: TextIO) -> None:
        """Redirect global output (e.g. sys.stderr)."""
        cls._stream = stream

    @classmethod
    def disable(cls) -> None:
        """Silence all global logging."""
        cls._enabled = False

    @classmethod
    def enable(cls) -> None:
        """Re-enable global logging."""
        cls._enabled = True

    @classmethod
    def show_banner(cls, compact: bool = False) -> None:
        """Print the Nestifypy ASCII art banner to the global stream."""
        _print_banner(stream=cls._stream, compact=compact)

    @classmethod
    def _global_emit(cls, level: LogLevel, *args: Any) -> None:
        if not cls._enabled or level < cls._level:
            return
        msg   = " ".join(str(a) for a in args)
        ts    = cls._now()
        line  = cls._formatter.format(level, cls._prefix, msg, ts)
        plain = cls._formatter.format_plain(level, cls._prefix, msg, ts)
        with cls._lock:
            print(line, file=cls._stream)
            if cls._file_path:
                with open(cls._file_path, "a", encoding="utf-8") as fh:
                    fh.write(plain + "\n")

    @classmethod
    def _now(cls) -> str:
        return datetime.now().strftime("%H:%M:%S")

    # ── global log methods ───────────────────────────────────────────────────

    @classmethod
    def gtrace(cls, *args: Any)   -> None: cls._global_emit(LogLevel.TRACE,   *args)
    @classmethod
    def gdebug(cls, *args: Any)   -> None: cls._global_emit(LogLevel.DEBUG,   *args)
    @classmethod
    def ginfo(cls, *args: Any)    -> None: cls._global_emit(LogLevel.INFO,    *args)
    @classmethod
    def gsuccess(cls, *args: Any) -> None: cls._global_emit(LogLevel.SUCCESS, *args)
    @classmethod
    def gwarn(cls, *args: Any)    -> None: cls._global_emit(LogLevel.WARN,    *args)
    @classmethod
    def gerror(cls, *args: Any)   -> None: cls._global_emit(LogLevel.ERROR,   *args)
    @classmethod
    def gfatal(cls, *args: Any)   -> None: cls._global_emit(LogLevel.FATAL,   *args)

    @classmethod
    def gtrace_exc(cls) -> None:
        """Log the current exception traceback at TRACE level (global)."""
        tb = traceback.format_exc()
        if tb.strip() != "NoneType: None":
            for line in tb.splitlines():
                cls._global_emit(LogLevel.TRACE, _C.DIM + line + _C.RST)

    # ── global context manager ────────────────────────────────────────────────

    @classmethod
    @contextmanager
    def global_level_context(cls, level: LogLevel) -> Iterator[None]:
        """Temporarily change the global log level."""
        old = cls._level
        cls._level = level
        try:
            yield
        finally:
            cls._level = old

    # ── global decorators ─────────────────────────────────────────────────────

    @classmethod
    def log(
        cls,
        level: LogLevel = LogLevel.DEBUG,
        show_args: bool = True,
        show_return: bool = False,
        show_time: bool = True,
    ) -> Callable[[F], F]:
        """
        Global decorator: log function calls.

        ::

            @SLogger.log(level=LogLevel.INFO)
            def connect(host, port):
                ...
        """
        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                name = fn.__qualname__
                if show_args:
                    arg_str = ", ".join(
                        [repr(a) for a in args] +
                        [f"{k}={v!r}" for k, v in kwargs.items()]
                    )
                    cls._global_emit(level, f"→ {name}({arg_str})")
                else:
                    cls._global_emit(level, f"→ {name}(…)")

                t0  = time.perf_counter()
                ret = fn(*args, **kwargs)
                ms  = (time.perf_counter() - t0) * 1000

                parts = [f"← {name}"]
                if show_return:
                    parts.append(f"= {ret!r}")
                if show_time:
                    parts.append(f"({ms:.2f} ms)")
                cls._global_emit(level, " ".join(parts))
                return ret
            return wrapper  # type: ignore
        return decorator

    @classmethod
    def trace_exc(cls, fn: F) -> F:
        """
        Global decorator: print a full traceback if the function raises,
        then re-raise.

        ::

            @SLogger.trace_exc
            def risky():
                raise RuntimeError("boom")
        """
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                cls.gerror(f"{fn.__qualname__} raised an exception:")
                cls.gtrace_exc()
                raise
        return wrapper  # type: ignore

    @classmethod
    def catch(
        cls,
        *exceptions: Type[BaseException],
        default: Any = None,
        reraise: bool = False,
        level: LogLevel = LogLevel.ERROR,
    ) -> Callable[[F], F]:
        """
        Global decorator: catch and log exceptions.

        ::

            @SLogger.catch(ValueError, TypeError, default=None)
            def parse(s):
                return int(s)
        """
        caught = exceptions or (Exception,)

        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except caught as exc:  # type: ignore[misc]
                    cls._global_emit(level, f"{fn.__qualname__} raised {type(exc).__name__}: {exc}")
                    cls.gtrace_exc()
                    if reraise:
                        raise
                    return default
            return wrapper  # type: ignore
        return decorator

    @classmethod
    def timeit(
        cls,
        label: Optional[str] = None,
        level: LogLevel = LogLevel.INFO,
    ) -> Callable[[F], F]:
        """
        Global decorator: log function execution time.

        ::

            @SLogger.timeit(label="DB query")
            def fetch_users():
                ...
        """
        def decorator(fn: F) -> F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                tag = label or fn.__qualname__
                t0  = time.perf_counter()
                ret = fn(*args, **kwargs)
                ms  = (time.perf_counter() - t0) * 1000
                cls._global_emit(level, f"⏱  {tag} completed in {ms:.2f} ms")
                return ret
            return wrapper  # type: ignore
        return decorator

    # ── global ruler helper ───────────────────────────────────────────────────

    @classmethod
    def ruler(cls, char: str = "─", width: int = 60, label: str = "") -> None:
        """Print a horizontal divider (global)."""
        if label:
            pad   = max(0, (width - len(label) - 2) // 2)
            line  = char * pad + f" {label} " + char * pad
        else:
            line  = char * width
        print(_C.DIM + line + _C.RST, file=cls._stream)


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience factory
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(
    prefix: str = "app",
    level: LogLevel = LogLevel.DEBUG,
    file: Optional[Union[str, Path]] = None,
    formatter: Optional[Formatter] = None,
    show_banner: bool = False,
    compact_banner: bool = False,
) -> SLogger:
    """
    Factory function – create a configured :class:`SLogger` instance.

    ::

        log = get_logger("my_module", level=LogLevel.INFO, file="app.log")
        log.info("Ready.")
    """
    return SLogger(
        prefix=prefix,
        level=level,
        file=file,
        formatter=formatter,
        show_banner=show_banner,
        compact_banner=compact_banner,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Core
    "SLogger",
    "LogLevel",
    # Formatters
    "Formatter",
    "SimpleFormatter",
    "JSONFormatter",
    # Factory
    "get_logger",
]
