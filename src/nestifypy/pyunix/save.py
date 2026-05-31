"""
nestifypy.pyunix.save
---------------------
Simple, robust save/load system backed by JSON files.

Supports multiple save slots, auto-save on a timer, default values,
and a type-safe accessor API. Data is stored as plain Python dicts so
anything JSON-serialisable can be persisted without extra work.

Usage:
    # Configure once at startup
    Save.set_path("saves/")          # directory for .json files
    Save.set_defaults({
        "score":    0,
        "level":    1,
        "upgrades": [],
    })

    # Write
    Save.set("score", 1500)
    Save.set("upgrades", ["double_jump", "dash"])
    Save.commit()                    # flush to disk immediately

    # Read
    score  = Save.get("score")       # 1500
    level  = Save.get("level")       # 1  (from defaults)
    all_   = Save.all()              # full dict snapshot

    # Multiple slots
    Save.use_slot(2)
    Save.set("score", 0)
    Save.commit()
    Save.use_slot(1)                 # back to slot 1

    # Auto-save every 60 seconds
    Save.auto_save(interval=60.0)    # call Save.tick(dt) in your game loop

    # Wipe
    Save.reset()                     # clears in-memory state to defaults
    Save.delete_slot(2)              # removes the .json file for slot 2
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class SaveSystem:
    """
    JSON-backed save/load manager with slot support and auto-save.

    All data is kept in an in-memory dict that mirrors the on-disk file.
    Call commit() (or enable auto_save) to flush changes to disk.
    """

    def __init__(self) -> None:
        self._base_path:  Path = Path("saves")
        self._slot:       int  = 1
        self._defaults:   Dict[str, Any] = {}
        self._data:       Dict[str, Any] = {}
        self._dirty:      bool  = False      # True when in-memory differs from disk
        self._auto_interval: float = 0.0    # 0 = disabled
        self._auto_accum:    float = 0.0
        self._loaded:     bool  = False

    # ── Configuration ────────────────────────

    def set_path(self, path: str | Path) -> None:
        """Set the directory where .json save files are stored."""
        self._base_path = Path(path)
        self._loaded = False   # force reload on next access

    def set_defaults(self, defaults: Dict[str, Any]) -> None:
        """
        Register default values for every key.

        Defaults are returned by get() when a key is missing from the save,
        and are used to populate a fresh save after reset().
        """
        self._defaults = copy.deepcopy(defaults)

    def use_slot(self, slot: int) -> None:
        """
        Switch to a different save slot.

        The current slot is NOT automatically committed — call commit() first
        if you want to preserve unsaved changes.

        Args:
            slot: Positive integer identifying the save file (slot 1 → save_1.json).
        """
        if slot < 1:
            raise ValueError("Slot number must be >= 1")
        self._slot   = slot
        self._loaded = False   # next access triggers a load from the new slot

    @property
    def current_slot(self) -> int:
        return self._slot

    @property
    def is_dirty(self) -> bool:
        """True when there are unsaved in-memory changes."""
        return self._dirty

    # ── Path helpers ─────────────────────────

    def _slot_path(self, slot: Optional[int] = None) -> Path:
        s = slot if slot is not None else self._slot
        return self._base_path / f"save_{s}.json"

    # ── Load / Save ──────────────────────────

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def load(self, slot: Optional[int] = None) -> bool:
        """
        Load data from disk into memory.

        Args:
            slot: If given, switch to that slot before loading.

        Returns:
            True if the file existed and was loaded; False if a fresh save
            was initialised from defaults.
        """
        if slot is not None:
            self._slot = slot

        path = self._slot_path()
        self._loaded = True

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                # Merge stored data on top of defaults so new keys appear
                self._data = copy.deepcopy(self._defaults)
                self._data.update(stored)
                self._dirty = False
                return True
            except (json.JSONDecodeError, OSError):
                pass   # fall through to fresh init

        # No file or corrupt — start from defaults
        self._data  = copy.deepcopy(self._defaults)
        self._dirty = False
        return False

    def commit(self, slot: Optional[int] = None) -> None:
        """
        Write in-memory data to disk.

        Args:
            slot: If given, write to that slot instead of the current one.
        """
        self._ensure_loaded()
        path = self._slot_path(slot)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            self._dirty = False
        except OSError as exc:
            raise OSError(f"[SaveSystem] Failed to write {path}: {exc}") from exc

    # Alias
    save = commit

    def slot_exists(self, slot: Optional[int] = None) -> bool:
        """Return True if a save file exists for the given (or current) slot."""
        return self._slot_path(slot).exists()

    def delete_slot(self, slot: Optional[int] = None) -> None:
        """Delete the save file for the given slot. Does NOT affect in-memory data."""
        path = self._slot_path(slot)
        if path.exists():
            path.unlink()

    # ── Data access ──────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Return the value for `key`.

        Resolution order: in-memory data → registered defaults → `default` arg.
        """
        self._ensure_loaded()
        if key in self._data:
            return self._data[key]
        if key in self._defaults:
            return copy.deepcopy(self._defaults[key])
        return default

    def set(self, key: str, value: Any) -> None:
        """Set a value in memory (does NOT write to disk — call commit() for that)."""
        self._ensure_loaded()
        self._data[key] = value
        self._dirty = True

    def delete(self, key: str) -> None:
        """Remove a key from in-memory data."""
        self._ensure_loaded()
        if key in self._data:
            del self._data[key]
            self._dirty = True

    def has(self, key: str) -> bool:
        """Return True if the key exists in in-memory data (ignores defaults)."""
        self._ensure_loaded()
        return key in self._data

    def all(self) -> Dict[str, Any]:
        """Return a deep copy of the full in-memory data dict."""
        self._ensure_loaded()
        return copy.deepcopy(self._data)

    def update(self, mapping: Dict[str, Any]) -> None:
        """Bulk-set multiple keys at once."""
        self._ensure_loaded()
        self._data.update(mapping)
        self._dirty = True

    def reset(self) -> None:
        """
        Reset in-memory data to defaults without touching the disk file.

        Call commit() afterwards if you want to persist the reset.
        """
        self._data  = copy.deepcopy(self._defaults)
        self._dirty = True

    # ── Auto-save ────────────────────────────

    def auto_save(self, interval: float) -> None:
        """
        Enable automatic saves every `interval` seconds.

        Requires Save.tick(dt) to be called from your game loop.

        Args:
            interval: Seconds between saves. Pass 0 to disable.
        """
        self._auto_interval = max(0.0, interval)
        self._auto_accum    = 0.0

    def tick(self, dt: float) -> None:
        """
        Advance the auto-save timer by `dt` seconds.

        Call this from your @Game.update or @Game.fixed_update.
        Only writes to disk when the interval elapses AND there are unsaved changes.
        """
        if self._auto_interval <= 0:
            return
        self._auto_accum += dt
        if self._auto_accum >= self._auto_interval:
            self._auto_accum -= self._auto_interval
            if self._dirty:
                self.commit()

    # ── Listing available slots ───────────────

    def list_slots(self) -> list[int]:
        """Return a sorted list of slot numbers that have save files on disk."""
        if not self._base_path.exists():
            return []
        slots = []
        for p in self._base_path.glob("save_*.json"):
            try:
                n = int(p.stem.split("_")[1])
                slots.append(n)
            except (IndexError, ValueError):
                pass
        return sorted(slots)

    def __repr__(self) -> str:
        loaded = "loaded" if self._loaded else "not loaded"
        dirty  = ", dirty" if self._dirty else ""
        return f"SaveSystem(slot={self._slot}, {loaded}{dirty})"


# Global singleton
Save = SaveSystem()
