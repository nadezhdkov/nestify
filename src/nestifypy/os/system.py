"""
nestifypy.os.system
-------------------
Complete cross-platform system-information utilities.

Design rules
~~~~~~~~~~~~
* Read-only introspection — no side-effects.
* Every method degrades gracefully: unavailable metrics return ``None``
  rather than raising.
* No third-party dependencies; stdlib only.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Dataclasses (typed return values)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiskUsage:
    path: str
    total: int       # bytes
    used: int        # bytes
    free: int        # bytes

    @property
    def total_human(self) -> str:
        return _human(self.total)

    @property
    def used_human(self) -> str:
        return _human(self.used)

    @property
    def free_human(self) -> str:
        return _human(self.free)

    @property
    def percent_used(self) -> float:
        return round(self.used / self.total * 100, 1) if self.total else 0.0


@dataclass(frozen=True)
class MemoryInfo:
    total: int       # bytes
    available: int   # bytes
    used: int        # bytes

    @property
    def total_human(self) -> str:
        return _human(self.total)

    @property
    def available_human(self) -> str:
        return _human(self.available)

    @property
    def used_human(self) -> str:
        return _human(self.used)

    @property
    def percent_used(self) -> float:
        return round(self.used / self.total * 100, 1) if self.total else 0.0


def _human(n: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class System:
    """Complete system-information utilities (read-only, no side-effects)."""

    # ------------------------------------------------------------------
    # OS / platform identity
    # ------------------------------------------------------------------

    @staticmethod
    def os_name() -> str:
        """Human-readable OS name: ``"Windows"``, ``"Linux"``, ``"Darwin"``."""
        return platform.system()

    @staticmethod
    def os_version() -> str:
        """Full OS version string."""
        return platform.version()

    @staticmethod
    def os_release() -> str:
        """Short release identifier (e.g. ``"22.04"`` on Ubuntu)."""
        return platform.release()

    @staticmethod
    def is_windows() -> bool:
        return platform.system() == "Windows"

    @staticmethod
    def is_linux() -> bool:
        return platform.system() == "Linux"

    @staticmethod
    def is_mac() -> bool:
        return platform.system() == "Darwin"

    @staticmethod
    def is_64bit() -> bool:
        return sys.maxsize > 2**32

    @staticmethod
    def arch() -> str:
        """Machine architecture: ``"x86_64"``, ``"arm64"``, etc."""
        return platform.machine()

    @staticmethod
    def hostname() -> str:
        """Network hostname of the machine."""
        return platform.node()

    @staticmethod
    def user() -> str:
        """Login name of the current user."""
        return os.getlogin() if hasattr(os, "getlogin") else os.environ.get("USER", "unknown")

    @staticmethod
    def shell() -> Optional[str]:
        """
        Return the current shell path (``$SHELL`` on POSIX,
        ``$COMSPEC`` on Windows).  ``None`` if not set.
        """
        return os.environ.get("SHELL") or os.environ.get("COMSPEC")

    # ------------------------------------------------------------------
    # Python
    # ------------------------------------------------------------------

    @staticmethod
    def python_version() -> str:
        """Current Python version string: ``"3.12.2"``."""
        return platform.python_version()

    @staticmethod
    def python_version_tuple() -> tuple[int, int, int]:
        """Return ``(major, minor, micro)`` as integers."""
        info = sys.version_info
        return (info.major, info.minor, info.micro)

    @staticmethod
    def python_implementation() -> str:
        """``"CPython"``, ``"PyPy"``, etc."""
        return platform.python_implementation()

    @staticmethod
    def python_path() -> str:
        """Absolute path of the current interpreter."""
        return sys.executable

    @staticmethod
    def python_paths() -> List[str]:
        """``sys.path`` — ordered list of directories searched for imports."""
        return list(sys.path)

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    @staticmethod
    def cpu_count() -> int:
        """Total logical CPU count (hyperthreading included)."""
        return os.cpu_count() or 1

    @staticmethod
    def cpu_count_physical() -> Optional[int]:
        """
        Physical (slogger) CPU count.

        Returns ``None`` if the information is unavailable without
        third-party packages.
        """
        # Best-effort via /proc/cpuinfo on Linux
        try:
            if platform.system() == "Linux":
                ids: set = set()
                with open("/proc/cpuinfo") as fh:
                    for line in fh:
                        if line.startswith("slogger id"):
                            ids.add(line.split(":")[1].strip())
                return len(ids) or None
        except OSError:
            pass
        return None

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    @staticmethod
    def memory() -> Optional[MemoryInfo]:
        """
        Return memory statistics as a :class:`MemoryInfo`.

        Works on Linux (via ``/proc/meminfo``) and macOS (via ``sysctl``).
        Returns ``None`` on unsupported platforms.
        """
        system = platform.system()
        try:
            if system == "Linux":
                return System._memory_linux()
            elif system == "Darwin":
                return System._memory_macos()
        except Exception:
            pass
        return None

    @staticmethod
    def _memory_linux() -> MemoryInfo:
        info: Dict[str, int] = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, val = line.partition(":")
                info[key.strip()] = int(val.split()[0]) * 1024  # kB → bytes
        total = info["MemTotal"]
        available = info.get("MemAvailable", info.get("MemFree", 0))
        return MemoryInfo(total=total, available=available, used=total - available)

    @staticmethod
    def _memory_macos() -> MemoryInfo:
        import subprocess
        total_raw = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True
        ).strip()
        total = int(total_raw)
        vm_stat = subprocess.check_output(["vm_stat"], text=True)
        page_size = 4096
        free_pages = 0
        for line in vm_stat.splitlines():
            if "Pages free" in line:
                free_pages = int(line.split(":")[1].strip().rstrip("."))
                break
        available = free_pages * page_size
        return MemoryInfo(total=total, available=available, used=total - available)

    # ------------------------------------------------------------------
    # Disk
    # ------------------------------------------------------------------

    @staticmethod
    def disk_usage(path: str = "/") -> DiskUsage:
        """
        Return disk usage statistics for the partition containing *path*.
        """
        usage = shutil.disk_usage(path)
        return DiskUsage(
            path=path,
            total=usage.total,
            used=usage.used,
            free=usage.free,
        )

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    @staticmethod
    def uptime() -> Optional[timedelta]:
        """
        Return system uptime as a ``timedelta``.

        Works on Linux and macOS.  Returns ``None`` elsewhere.
        """
        try:
            if platform.system() == "Linux":
                with open("/proc/uptime") as fh:
                    seconds = float(fh.read().split()[0])
                return timedelta(seconds=seconds)
            elif platform.system() == "Darwin":
                import subprocess
                boot_raw = subprocess.check_output(
                    ["sysctl", "-n", "kern.boottime"], text=True
                )
                # Format: { sec = 1234567890, usec = 0 } Thu ...
                sec = int(boot_raw.split("sec = ")[1].split(",")[0])
                return timedelta(seconds=time.time() - sec)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------

    @staticmethod
    def env_vars() -> Dict[str, str]:
        """Return a copy of the current environment variables."""
        return dict(os.environ)

    @staticmethod
    def env_var(key: str, default: Optional[str] = None) -> Optional[str]:
        """Return a single environment variable."""
        return os.environ.get(key, default)

    # ------------------------------------------------------------------
    # Convenience summary
    # ------------------------------------------------------------------

    @staticmethod
    def info() -> Dict[str, object]:
        """
        Return a summary dict of the most useful system properties.

        Useful for logging at startup::

            import json
            print(json.dumps(System.info(), indent=2, default=str))
        """
        mem = System.memory()
        disk = System.disk_usage()
        up = System.uptime()
        return {
            "os": System.os_name(),
            "os_version": System.os_version(),
            "arch": System.arch(),
            "hostname": System.hostname(),
            "user": System.user(),
            "python": System.python_version(),
            "python_impl": System.python_implementation(),
            "cpu_logical": System.cpu_count(),
            "memory_total": mem.total_human if mem else None,
            "memory_used_pct": mem.percent_used if mem else None,
            "disk_total": disk.total_human,
            "disk_used_pct": disk.percent_used,
            "uptime": str(up) if up else None,
        }


__all__ = ["System", "DiskUsage", "MemoryInfo"]
