#!/usr/bin/env python3
"""
insert_silences.py — Take an audio recording plus a multi-line transcript,
find the timestamps at each line break, and splice silence in there.

Useful as a preprocessing step for manim's StitcherService (or any tool that
wants pre-baked silence "slots" in a single audio file).

Usage:
    python insert_silences.py -i audio.wav -t transcript.txt -o out.wav
    python insert_silences.py -i audio.wav -t scene.py -o out.wav   # manim script
    python insert_silences.py -i audio.mp3 -t lines.txt -o out.mp3 --silence 5.0 --model base

Install:
    pip install faster-whisper pydub
    # also needs ffmpeg on your PATH (for pydub)
"""

import argparse
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

from faster_whisper import WhisperModel # type: ignore
from pydub import AudioSegment

import dir_config


def ensure_wav(audio_path: str) -> str:
    """If the file is .m4a or .mp3, convert to .wav via ffmpeg and return the new path."""
    p = Path(audio_path)
    if p.suffix.lower() not in (".m4a", ".mp3"):
        return audio_path
    wav_path = p.with_suffix(".wav")
    if wav_path.exists():
        print(f"Using existing {wav_path.name}", file=sys.stderr)
        return str(wav_path)
    print(f"Converting {p.name} → {wav_path.name} ...", file=sys.stderr)
    subprocess.run(
        ["ffmpeg", "-i", str(p), str(wav_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Converted {p.name} → {wav_path.name} ...", file=sys.stderr)
    print(f"Deleting {p.name}", file = sys.stderr)
    p.unlink()
    print(f"Deleted {p.name}", file = sys.stderr)
    return str(wav_path)


def normalize(word: str) -> str:
    """Lowercase, keep only word chars and apostrophes. Used for matching."""
    return re.sub(r"[^\w']", "", word).lower()


def transcribe(audio_path: str, model_size: str = "base") -> list[dict]:
    """Run faster-whisper and return a flat list of word-level dicts."""
    print(f"Loading whisper model '{model_size}'...", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("Transcribing...", file=sys.stderr)
    segments, _ = model.transcribe(audio_path, word_timestamps=True)

    words = []
    for seg in segments:
        if not seg.words:
            continue
        for w in seg.words:
            n = normalize(w.word)
            if n:
                words.append({"word": w.word, "norm": n, "start": w.start, "end": w.end})
    print(f"  detected {len(words)} words", file=sys.stderr)
    return words


def _parse_lines(raw_lines: list[str]) -> list[list[str]]:
    """Normalize a list of raw strings into lists of normalized words."""
    result = []
    for raw in raw_lines:
        words = [normalize(w) for w in raw.split()]
        words = [w for w in words if w]
        if words:
            result.append(words)
    return result


def load_transcript(path: str) -> list[list[str]]:
    """Read transcript file or manim script -> list of lines, each a list of normalized words."""
    if Path(path).suffix == ".py":
        return _load_manim_transcript(path)
    text = Path(path).read_text(encoding="utf-8")
    return _parse_lines(text.splitlines())


def _load_manim_transcript(path: str) -> list[list[str]]:
    """Extract voiceover strings from a manim script in order."""
    text = Path(path).read_text(encoding="utf-8")
    pattern = re.compile(r"""self\.voiceover\(\s*(?:"([^"]+)"|'([^']+)')""")
    raw_lines = []
    for m in pattern.finditer(text):
        line_start = text.rfind('\n', 0, m.start()) + 1
        if '#' not in text[line_start:m.start()]:
            raw_lines.append(m.group(1) or m.group(2))
    if not raw_lines:
        print("Warning: no self.voiceover(...) calls found in the script.", file=sys.stderr)
    return _parse_lines(raw_lines)


def find_breakpoints(lines: list[list[str]], whisper_words: list[dict]) -> list[dict]:
    """For each line break in the transcript, find the matching whisper word's end time."""
    # Flatten transcript with metadata
    flat = []
    for li, line in enumerate(lines):
        for pi, w in enumerate(line):
            flat.append({"norm": w, "line": li, "pos": pi, "line_len": len(line)})

    transcript_norm = [t["norm"] for t in flat]
    whisper_norm = [w["norm"] for w in whisper_words]

    # Sequence-align transcript -> whisper. Tolerates small mishearings/insertions/deletions.
    matcher = SequenceMatcher(a=transcript_norm, b=whisper_norm, autojunk=False)
    alignment: list[int | None] = [None] * len(flat)  # transcript idx -> whisper idx
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                alignment[i1 + k] = j1 + k

    n_aligned = sum(1 for a in alignment if a is not None)
    print(
        f"Aligned {n_aligned}/{len(flat)} transcript words to whisper output",
        file=sys.stderr,
    )

    # Find line endings (skip the very last line — nothing follows it)
    breakpoints = []
    n_lines = len(lines)
    for i, t in enumerate(flat):
        is_line_end = t["pos"] == t["line_len"] - 1
        if not is_line_end or t["line"] >= n_lines - 1:
            continue

        wi = alignment[i]

        # If this exact word wasn't aligned, walk backwards to nearest aligned word,
        # then forwards. This is a fallback for misheard line-final words.
        if wi is None:
            for back in range(i - 1, -1, -1):
                if alignment[back] is not None:
                    wi = alignment[back]
                    break
        if wi is None:
            for fwd in range(i + 1, len(flat)):
                if alignment[fwd] is not None:
                    wi = alignment[fwd]
                    break
        if wi is None:
            print(
                f"  ! could not locate end of line {t['line']+1} "
                f"(word '{t['norm']}'); skipping",
                file=sys.stderr,
            )
            continue

        ww = whisper_words[wi]
        breakpoints.append(
            {
                "line": t["line"],
                "transcript_word": t["norm"],
                "whisper_word": ww["norm"],
                "end_time": ww["end"],
                "matched": ww["norm"] == t["norm"],
            }
        )
    return breakpoints


def insert_silence(
    audio_path: str,
    output_path: str,
    breakpoints: list[dict],
    silence_seconds: float,
) -> None:
    """Load audio, splice silence in at each breakpoint, write out."""
    audio = AudioSegment.from_file(audio_path)
    silence = AudioSegment.silent(duration=int(silence_seconds * 1000))

    # Insert from latest to earliest so earlier offsets aren't shifted by inserts.
    bps_sorted = sorted(breakpoints, key=lambda b: b["end_time"], reverse=True)
    for bp in bps_sorted:
        cut_ms = int(bp["end_time"] * 1000)
        audio = audio[:cut_ms] + silence + audio[cut_ms:]

    fmt = Path(output_path).suffix.lstrip(".").lower() or "wav"
    audio.export(output_path, format=fmt)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-i", "--input", help="Input audio file (any format ffmpeg can read)")
    p.add_argument("-t", "--transcript", help="Plain-text transcript (one chunk per line) or manim .py script")
    p.add_argument("-o", "--output", help="Output audio file (extension picks format)")
    p.add_argument("-s", "--stem", help="File stem, e.g. 'intro_with_tables' or 'directional_derivative'")
    p.add_argument(
        "--silence",
        type=float,
        default=5.0,
        help="Seconds of silence to insert at each line break (default 5)",
    )
    p.add_argument(
        "--model",
        default="base",
        help="faster-whisper model size: tiny | base | small | medium | large-v3 (default base)",
    )
    args = p.parse_args()

    if args.stem:
        # Calculate input output and transcript from stem
        args.input = dir_config.path_to_raw_voiceover(args.stem)
        args.transcript = dir_config.path_to_manim_script(args.stem)
        args.output = dir_config.path_to_podcast(args.stem, make_new = True)
    if not args.input:
        args.input = input("Input audio file: ").strip()
    if not args.transcript:
        args.transcript = input("Transcript file: ").strip()
    if not args.output:
        args.output = input("Output audio file: ").strip()

    audio_input = ensure_wav(args.input)

    lines = load_transcript(args.transcript)
    print(f"Transcript: {len(lines)} lines", file=sys.stderr)
    if len(lines) < 2:
        print("Need at least 2 lines to have a break between them. Nothing to do.", file=sys.stderr)
        return 1

    words = transcribe(audio_input, args.model)
    breakpoints = find_breakpoints(lines, words)

    print("\nBreakpoints:", file=sys.stderr)
    for bp in breakpoints:
        flag = "✓" if bp["matched"] else "~"  # ~ = used a fallback word
        print(
            f"  {flag} after line {bp['line']+1} "
            f"('{bp['transcript_word']}' → whisper '{bp['whisper_word']}') "
            f"at {bp['end_time']:.3f}s",
            file=sys.stderr,
        )

    insert_silence(audio_input, args.output, breakpoints, args.silence)
    print(f"\nWrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())