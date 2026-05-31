"""
nestifypy.pyunix.audio
----------------------
Audio system: music streaming, SFX playback, channels, and 3D positional audio.

Usage:
    Audio.play_music("theme.mp3", loop=True, fade_ms=1000)
    Audio.play_sfx("jump.wav")
    Audio.play_sfx("bullet.wav", volume=0.6, pitch_variance=0.15)

    # Positional audio (attenuates by distance)
    Audio.play_positional("footstep.wav", source_x=400, source_y=300,
                          listener_x=player.x, listener_y=player.y,
                          max_distance=600)

    # Global volumes
    Audio.set_music_volume(0.8)
    Audio.set_sfx_volume(0.5)

    # Pause / resume all
    Audio.pause_all()
    Audio.resume_all()
"""
from __future__ import annotations

import random
from typing import Optional

from nestifypy.pyunix.assets import Assets
from nestifypy.pyunix.exceptions import AudioError

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False


class AudioSystem:
    """
    Manages music streaming and sound-effect playback via pygame.mixer.
    """

    def __init__(self) -> None:
        self._music_volume: float = 1.0
        self._sfx_volume:   float = 1.0
        self._paused:       bool  = False
        # Keeps strong references to pitched Sound objects until they finish
        # playing, preventing premature garbage collection.
        self._pitched_sounds: list = []

    # ── Music (streamed) ─────────────────────

    def play_music(
        self,
        path: str,
        loop: bool = True,
        fade_ms: int = 0,
        volume: Optional[float] = None,
    ) -> None:
        """
        Stream background music from a file.

        Args:
            path:     File path to the music track.
            loop:     Loop indefinitely. Defaults to True.
            fade_ms:  Fade-in duration in milliseconds.
            volume:   Override volume (0.0–1.0). Uses global music volume if None.
        """
        if not _HAS_PYGAME:
            return
        resolved = Assets._resolve(path)
        if not resolved.exists():
            raise AudioError(f"Music file not found: {resolved}")
        try:
            pygame.mixer.music.load(str(resolved))
            pygame.mixer.music.play(loops=-1 if loop else 0, fade_ms=fade_ms)
            pygame.mixer.music.set_volume(volume if volume is not None else self._music_volume)
        except Exception as exc:
            raise AudioError(f"Failed to play music '{path}': {exc}") from exc

    def stop_music(self, fade_ms: int = 0) -> None:
        """Stop the currently playing music track."""
        if not _HAS_PYGAME:
            return
        if fade_ms > 0:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()

    def pause_music(self) -> None:
        if _HAS_PYGAME:
            pygame.mixer.music.pause()

    def resume_music(self) -> None:
        if _HAS_PYGAME:
            pygame.mixer.music.unpause()

    def set_music_volume(self, volume: float) -> None:
        """Set global music volume (0.0–1.0)."""
        self._music_volume = max(0.0, min(1.0, volume))
        if _HAS_PYGAME:
            pygame.mixer.music.set_volume(self._music_volume)

    @property
    def music_playing(self) -> bool:
        return _HAS_PYGAME and pygame.mixer.music.get_busy()

    # ── SFX (in-memory) ──────────────────────

    def play_sfx(
        self,
        path: str,
        volume: Optional[float] = None,
        pitch_variance: float = 0.0,
        loops: int = 0,
    ) -> Optional[Any]:
        """
        Play a sound effect.

        Args:
            path:           File path (or alias) to the sound.
            volume:         Override volume (0.0–1.0). Uses global sfx volume if None.
            pitch_variance: Randomly vary pitch by ±this fraction (0.0 = no variance).
                            Implemented by slightly resampling the sound buffer.
            loops:          Number of additional loops (0 = play once, -1 = loop forever).

        Returns:
            The pygame Channel the sound is playing on, or None.
        """
        if not _HAS_PYGAME:
            return None
        snd = Assets.sound(path)
        vol = volume if volume is not None else self._sfx_volume

        if pitch_variance > 0.0:
            # Crude pitch shift: adjust speed via a temporary Sound copy.
            # The pitched object is stored in self._pitched_sounds so the GC
            # cannot collect it while the audio is still playing.
            factor = 1.0 + random.uniform(-pitch_variance, pitch_variance)
            try:
                arr = pygame.sndarray.array(snd)
                import numpy as np
                indices = (np.arange(0, len(arr), factor)).astype(int)
                indices = indices[indices < len(arr)]
                pitched = pygame.sndarray.make_sound(arr[indices])
                pitched.set_volume(vol)
                channel = pitched.play(loops=loops)
                # Purge finished sounds, then track the new one
                self._pitched_sounds = [
                    s for s in self._pitched_sounds
                    if pygame.mixer.find_channel() is not None and s.get_num_channels() > 0
                ]
                self._pitched_sounds.append(pitched)
                return channel
            except Exception:
                pass  # numpy not available — fall through

        snd.set_volume(vol)
        return snd.play(loops=loops)

    def play_positional(
        self,
        path: str,
        source_x: float,
        source_y: float,
        listener_x: float,
        listener_y: float,
        max_distance: float = 800.0,
        base_volume: Optional[float] = None,
    ) -> None:
        """
        Play a sound with volume attenuated by 2D distance.

        Args:
            path:         Sound file path.
            source_x/y:   World position of the sound source.
            listener_x/y: World position of the listener (camera/player).
            max_distance: Distance at which volume reaches zero.
            base_volume:  Maximum volume. Defaults to global sfx volume.
        """
        import math
        dist = math.hypot(source_x - listener_x, source_y - listener_y)
        if dist >= max_distance:
            return
        t = 1.0 - dist / max_distance
        vol = t * (base_volume if base_volume is not None else self._sfx_volume)
        self.play_sfx(path, volume=vol)

    def set_sfx_volume(self, volume: float) -> None:
        """Set global SFX volume (0.0–1.0)."""
        self._sfx_volume = max(0.0, min(1.0, volume))

    # ── Global controls ──────────────────────

    def pause_all(self) -> None:
        """Pause all sound channels and music."""
        if not _HAS_PYGAME:
            return
        pygame.mixer.pause()
        pygame.mixer.music.pause()
        self._paused = True

    def resume_all(self) -> None:
        if not _HAS_PYGAME:
            return
        pygame.mixer.unpause()
        pygame.mixer.music.unpause()
        self._paused = False

    def stop_all(self) -> None:
        """Stop every sound immediately."""
        if _HAS_PYGAME:
            pygame.mixer.stop()
            pygame.mixer.music.stop()

    @property
    def is_paused(self) -> bool:
        return self._paused


Audio = AudioSystem()
