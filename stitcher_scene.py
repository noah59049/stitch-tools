"""stitcher_scene — a VoiceoverScene subclass that removes StitcherService boilerplate.

Subclasses of `StitcherScene` should override `construct_scene()` instead of
`construct()`. `StitcherScene.construct()` wires up the `StitcherService` speech
service (finding `podcasts/{stem}_podcast*.wav` via `dir_config`) and then calls
`construct_scene()`.

If no podcast audio is found for the scene's stem, no error is raised at setup time:
a warning is printed and the speech service is left unset. The error is deferred
until `self.voiceover(...)` is actually called, since a scene that never calls
`self.voiceover(...)` (e.g. one that's still being written) shouldn't fail just
because the audio hasn't been recorded yet.

Voiceovers can be turned off entirely (no audio, no error even if the podcast file
is missing) either in code, by setting `silent = True` on the scene, or from the
command line, by setting the `STITCH_SILENT` environment variable, e.g.:
    STITCH_SILENT=1 manim -pql my_scene.py MyScene
"""

import os
import re
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from manim_voiceover import VoiceoverScene
from manim_voiceover.helper import remove_bookmarks
from manim_voiceover.services.stitcher import _StitcherService as StitcherService
from manim_voiceover.tracker import VoiceoverTracker

import dir_config

SILENT_ENV_VAR = "STITCH_SILENT"

# Rough narration pace used to estimate spoken duration when there's no audio to
# measure (silenced voiceovers): ~150 words/minute at ~1.5 syllables/word.
SYLLABLES_PER_SECOND = 3.75

_VOWEL_GROUPS_RE = re.compile(r"[aeiouy]+")


def _env_silent_flag_set() -> bool:
    return os.environ.get(SILENT_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def _count_syllables(word: str) -> int:
    """Heuristic syllable count: one per vowel group, minus a silent trailing 'e'."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    count = len(_VOWEL_GROUPS_RE.findall(word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _estimate_speech_duration(text: str) -> float:
    """Estimates the spoken duration of `text`, in seconds, from a syllable heuristic."""
    words = remove_bookmarks(text).split()
    if not words:
        return 0.0
    syllables = sum(_count_syllables(word) for word in words)
    return syllables / SYLLABLES_PER_SECOND


class _SilentVoiceoverTracker:
    """Stand-in for VoiceoverTracker, yielded by `voiceover()` when silenced."""

    duration = 0.0

    def __init__(self, text: str | None = None) -> None:
        self.estimated_duration = _estimate_speech_duration(text) if text else 0.0

    def get_remaining_duration(self, buff: float = 0.0) -> float:
        return 0.0

    def time_until_bookmark(self, mark: str, buff: float = 0.0, limit: float | None = None) -> float:
        return 0.0


class StitcherScene(VoiceoverScene):
    """A VoiceoverScene that wires up StitcherService automatically.

    Subclasses should override `construct_scene()`, not `construct()`.

    Class/instance attributes:
        stem: Basename used to find `podcasts/{stem}_podcast*.wav`. Defaults to the
            stem of the file the subclass is defined in (matching the file created by
            `stitch_tools add <stem>`), so it usually doesn't need to be set explicitly.
        silent: If True, `self.voiceover(...)` becomes a silent no-op and no
            StitcherService is created, even if podcast audio exists. Every scene in a
            run can be silenced without editing code via the STITCH_SILENT env var.
    """

    stem: str | None = None
    silent: bool = False
    _voiceover_unavailable: bool = False
    _voiceover_depth: int = 0

    def construct(self) -> None:
        self._setup_stitcher_speech_service()
        self.construct_scene()

    def construct_scene(self) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} must override construct_scene() (not construct())."
        )

    def _resolve_stem(self) -> str:
        if self.stem is not None:
            return self.stem
        module = sys.modules.get(type(self).__module__)
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            raise RuntimeError(
                f"Could not infer 'stem' for {type(self).__name__}; set it explicitly, "
                'e.g. `stem = "my_scene"`.'
            )
        return Path(module_file).stem

    def _voiceovers_silenced(self) -> bool:
        return self.silent or _env_silent_flag_set()

    def _setup_stitcher_speech_service(self) -> None:
        if self._voiceovers_silenced():
            return

        stem = self._resolve_stem()
        try:
            podcast_path = dir_config.path_to_podcast(stem)
        except FileNotFoundError:
            warnings.warn(
                f"No podcast audio found for stem {stem!r} (looked for "
                f"'{stem}_podcast1.wav' in podcasts/). Voiceovers are unavailable for "
                f"this run; calling self.voiceover() will raise an error. Record audio "
                f"into raw_voiceovers/ and run 'insert_silences -s {stem}' to fix this, "
                f"or set self.silent = True to silence voiceovers on purpose.",
                stacklevel=2,
            )
            self._voiceover_unavailable = True
            return

        self.set_speech_service(StitcherService(
            podcast_path,
            cache_dir=dir_config.get_cache_dir(),
            min_silence_len=2000,
            keep_silence=(0, 0),
        ))

    @contextmanager
    def voiceover(
        self,
        text: str | None = None,
        ssml: str | None = None,
        **kwargs: object,
    ) -> Generator[VoiceoverTracker, None, None]:
        if text is None and ssml is None:
            raise ValueError("Please specify either a voiceover text or SSML string.")

        self._voiceover_depth += 1
        try:
            if self._voiceovers_silenced():
                tracker = _SilentVoiceoverTracker(text)
                self.current_tracker = tracker
                try:
                    yield tracker
                finally:
                    self.wait_for_voiceover()
                return

            if self._voiceover_unavailable:
                stem = self._resolve_stem()
                raise FileNotFoundError(
                    f"self.voiceover() was called, but no podcast audio was found for stem "
                    f"{stem!r}. Record audio into raw_voiceovers/ and run "
                    f"'insert_silences -s {stem}', or set self.silent = True to skip "
                    f"voiceovers."
                )

            with super().voiceover(text=text, ssml=ssml, **kwargs) as tracker:
                yield tracker
        finally:
            self._voiceover_depth -= 1

    def get_current_voiceover_duration(self) -> float:
        """Returns the duration, in seconds, of the voiceover currently active inside a
        `with self.voiceover(...):` block.

        While voiceovers are silenced (`self.silent`, or the STITCH_SILENT env var),
        there's no audio to measure, so the duration is estimated from the spoken text
        using a syllable-count heuristic instead.

        Raises:
            RuntimeError: If called outside of a `with self.voiceover(...):` block.
        """
        if self._voiceover_depth == 0:
            raise RuntimeError(
                "get_current_voiceover_duration() was called outside of a "
                "`with self.voiceover(...):` block."
            )
        tracker = self.current_tracker
        if isinstance(tracker, _SilentVoiceoverTracker):
            return tracker.estimated_duration
        return tracker.duration
