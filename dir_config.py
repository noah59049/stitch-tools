import os

_working_directory: str | None = None

def set_working_directory(path: str) -> None:
    global _working_directory
    _working_directory = path.rstrip("/") + "/"

def _wd() -> str:
    return _working_directory if _working_directory is not None else os.getcwd().rstrip("/") + "/"

def get_abspath(path: str) -> str:
    return _wd() + path

def get_cache_dir():
    return get_abspath("cache_dir")

def path_to_transcript(stem : str, extension : str = ".pdf"):
    return _wd() + "transcripts/" + stem + extension

def path_to_manim_script(stem: str):
    return _wd() + stem + ".py"

def _raw_voiceover_paths(stem: str) -> list[str]:
    """Existing raw voiceover file paths for stem, in increasing number order."""
    directory = get_abspath("raw_voiceovers/")
    paths = []
    for number in range(1, 10000):
        for extension in ".wav", ".mp3", ".m4a":
            path = directory + stem + f"{number}{extension}"
            if os.path.exists(path):
                paths.append(path)
                break
        else:
            break
    return paths


def path_to_raw_voiceover(stem: str):
    paths = _raw_voiceover_paths(stem)
    if not paths:
        directory = get_abspath("raw_voiceovers/")
        raise FileNotFoundError(f"Could not find raw voiceover {directory + stem}1.(wav|mp3|m4a)")
    return paths[-1]


def _podcast_paths(stem: str) -> list[str]:
    """Existing podcast file paths for stem, in increasing number order."""
    directory = get_abspath("podcasts/")
    paths = []
    for number in range(1, 10000):
        path = directory + stem + f"_podcast{number}.wav"
        if os.path.exists(path):
            paths.append(path)
        else:
            break
    return paths


def path_to_podcast(stem : str, mode : str = "existing"):
    """Return the path to a podcast WAV file matching the given stem.

    Scans the podcasts/ directory for files named ``<stem>_podcast<N>.wav`` and
    looks at the one with the largest consecutive N starting from 1.

    Args:
        stem: Base name prefix for the podcast files (e.g. ``"episode1"`` matches
              ``episode1_podcast1.wav``, ``episode1_podcast2.wav``, etc.).
        mode: One of:
          - "existing" (default): the highest existing podcast number. Raises
            FileNotFoundError if none exist yet.
          - "new": one higher than the highest existing podcast number, for creating
            a new podcast without overwriting prior ones.
          - "overwrite": the highest existing podcast number, or 1 if none exist yet,
            so callers overwrite the most recent podcast instead of creating a new one.

    Returns:
        Absolute path to the relevant podcast WAV file.

    Raises:
        FileNotFoundError: If no matching file is found and mode is "existing".
        ValueError: If mode is not one of "existing", "new", or "overwrite".
    """
    if mode not in ("existing", "new", "overwrite"):
        raise ValueError(f"Invalid mode {mode!r}; must be 'existing', 'new', or 'overwrite'")

    directory = get_abspath("podcasts/")
    best_number = len(_podcast_paths(stem))
    if mode == "new":
        best_number += 1
    elif mode == "overwrite":
        best_number = max(best_number, 1)

    if best_number == 0:
        raise FileNotFoundError(f"Could not find podcast {directory + stem + "_podcast1.wav"}")
    else:
        return directory + stem + f"_podcast{best_number}.wav"


def _json_sidecar(wav_path: str) -> str:
    """Path to the JSON file StitcherService writes next to a podcast wav (see
    manim_voiceover's ``_StitcherService.get_json_path``: splitext(source_path) + ".json")."""
    return os.path.splitext(wav_path)[0] + ".json"


def prune_podcasts(stem: str) -> int:
    """Delete all but the most recent podcast for stem (plus its cached JSON sidecar),
    renumbering the survivor to 1.

    Returns the number of podcast files deleted.
    """
    paths = _podcast_paths(stem)
    if len(paths) <= 1:
        return 0
    keep = paths[-1]
    for path in paths[:-1]:
        os.remove(path)
        json_path = _json_sidecar(path)
        if os.path.exists(json_path):
            os.remove(json_path)
    new_path = get_abspath("podcasts/") + stem + "_podcast1.wav"
    if keep != new_path:
        os.replace(keep, new_path)
        keep_json = _json_sidecar(keep)
        if os.path.exists(keep_json):
            os.replace(keep_json, _json_sidecar(new_path))
    return len(paths) - 1


def prune_raw_voiceovers(stem: str) -> int:
    """Delete all but the most recent raw voiceover for stem, renumbering it to 1.

    Returns the number of files deleted.
    """
    paths = _raw_voiceover_paths(stem)
    if len(paths) <= 1:
        return 0
    keep = paths[-1]
    for path in paths[:-1]:
        os.remove(path)
    extension = os.path.splitext(keep)[1]
    new_path = get_abspath("raw_voiceovers/") + f"{stem}1{extension}"
    if keep != new_path:
        os.replace(keep, new_path)
    return len(paths) - 1