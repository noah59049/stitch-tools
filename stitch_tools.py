#!/usr/bin/env python3
"""
stitch_tools — Project scaffolding for manim+voiceover videos.

Commands:
    stitch_tools init           Set up directory structure for a new video project
    stitch_tools add <stem>     Add a new manim scene file
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import dir_config

SCENES_FILE = "scenes.txt"

GITIGNORE_ENTRIES = ["podcasts/", "raw_voiceovers/", "transcripts/", "cache_dir/", "media/"]

_SCENE_CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(\s*StitcherScene\s*\)\s*:", re.MULTILINE)

SCENE_TEMPLATE = """\
import numpy as np
from manim import *
from stitcher_scene import StitcherScene


class {class_name}(StitcherScene):
    def construct_scene(self):
        pass
"""


def _stem_to_class_name(stem: str) -> str:
    return "".join(word.capitalize() for word in stem.split("_"))


def _read_scenes(scenes_path: Path) -> list[str]:
    if not scenes_path.exists():
        return []
    return [s for s in scenes_path.read_text().splitlines() if s.strip()]


def cmd_init(args):
    wd = Path.cwd()

    for d in ["podcasts", "raw_voiceovers", "transcripts", "cache_dir"]:
        (wd / d).mkdir(exist_ok=True)
        print(f"Created {d}/")

    gitignore_path = wd / ".gitignore"
    existing = gitignore_path.read_text() if gitignore_path.exists() else ""
    to_add = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if to_add:
        with gitignore_path.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for entry in to_add:
                f.write(entry + "\n")
        print(f"Added to .gitignore: {', '.join(to_add)}")
    else:
        print(".gitignore already up to date")

    scenes_path = wd / SCENES_FILE
    if not scenes_path.exists():
        scenes_path.write_text("")
        print(f"Created {SCENES_FILE}")

    _ensure_deps(wd)


def _ensure_deps(wd: Path) -> None:
    """Make sure the scaffolded scenes' imports (manim, manim_voiceover) are installed.

    StitcherService itself needs nothing beyond manim_voiceover: pydub is already
    one of its own dependencies, so there's no third package to add here.
    """
    if shutil.which("uv") is None:
        print(
            "Warning: 'uv' not found on PATH; skipping dependency install. "
            "Install manim and manim_voiceover manually.",
            file=sys.stderr,
        )
        return

    print("Running: uv add manim manim_voiceover")
    result = subprocess.run(["uv", "add", "manim", "manim_voiceover"], cwd=wd)
    if result.returncode != 0:
        print(
            "Warning: 'uv add manim manim_voiceover' failed (no pyproject.toml here?). "
            "Run 'uv init' first, or install manim/manim_voiceover manually.",
            file=sys.stderr,
        )


def cmd_add(args):
    wd = Path.cwd()
    stem = args.stem
    class_name = args.class_name or _stem_to_class_name(stem)

    scene_file = wd / f"{stem}.py"
    if scene_file.exists() and not args.force:
        print(f"Error: {scene_file.name} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    scene_file.write_text(SCENE_TEMPLATE.format(stem=stem, class_name=class_name))
    print(f"Created {stem}.py (class {class_name})")

    scenes_path = wd / SCENES_FILE
    scenes = _read_scenes(scenes_path)

    if stem in scenes:
        print(f"Warning: {stem} already in {SCENES_FILE}", file=sys.stderr)
    else:
        if args.position is None:
            scenes.append(stem)
        else:
            scenes.insert(args.position, stem)
        scenes_path.write_text("\n".join(scenes) + "\n")
        print(f"Added {stem} to {SCENES_FILE} (position {scenes.index(stem)})")

def cmd_prune(args):
    wd = Path.cwd()
    if args.stem:
        stems = [args.stem]
    else:
        stems = _read_scenes(wd / SCENES_FILE)
        if not stems:
            print(
                f"No scenes found in {SCENES_FILE}. Pass a stem explicitly, "
                f"e.g. 'stitch_tools prune my_scene'.",
                file=sys.stderr,
            )
            return 1

    for stem in stems:
        n_podcasts = dir_config.prune_podcasts(stem)
        n_raw = dir_config.prune_raw_voiceovers(stem)
        if n_podcasts or n_raw:
            print(f"{stem}: deleted {n_podcasts} old podcast(s), {n_raw} old raw voiceover(s)")
        else:
            print(f"{stem}: nothing to prune")


def cmd_list(args):
    with open("scenes.txt") as file:
        print(file.read().strip())


def _find_scene_class(scene_file: Path, stem: str) -> str:
    match = _SCENE_CLASS_RE.search(scene_file.read_text())
    if match:
        return match.group(1)
    return _stem_to_class_name(stem)


def cmd_run_all(args):
    wd = Path.cwd()
    scenes = _read_scenes(wd / SCENES_FILE)
    if not scenes:
        print(f"No scenes found in {SCENES_FILE}. Add one with 'stitch_tools add <stem>'.", file=sys.stderr)
        return 1

    media_dir = wd / "media"
    rendered_paths: dict[str, Path] = {}
    failed: list[str] = []

    for stem in scenes:
        scene_file = wd / f"{stem}.py"
        if not scene_file.exists():
            print(f"Error: {scene_file.name} not found. Skipping this scene and continuing.", file=sys.stderr)
            failed.append(stem)
            continue

        class_name = _find_scene_class(scene_file, stem)
        output_name = f"{stem}.mp4"
        print(f"\n=== Rendering {stem} ({class_name}) ===")
        result = subprocess.run(
            [
                sys.executable, "-m", "manim", "render",
                f"-q{args.quality}",
                "-o", output_name,
                str(scene_file), class_name,
            ],
            cwd=wd,
        )
        if result.returncode != 0:
            print(
                f"Error: rendering {stem} failed (manim exited with code {result.returncode}). "
                f"Continuing with the remaining scenes.",
                file=sys.stderr,
            )
            failed.append(stem)
            continue

        matches = sorted(media_dir.rglob(output_name), key=lambda p: p.stat().st_mtime)
        if not matches:
            print(
                f"Error: manim reported success for {stem} but no output file {output_name!r} "
                f"was found under {media_dir}/. Continuing with the remaining scenes.",
                file=sys.stderr,
            )
            failed.append(stem)
            continue
        rendered_paths[stem] = matches[-1]

    if failed:
        print(
            f"\n{len(failed)} scene(s) failed to render: {', '.join(failed)}. "
            f"All other scenes were still rendered, but they will not be combined into one video.",
            file=sys.stderr,
        )
        return 1

    print(f"\nAll {len(scenes)} scene(s) rendered successfully. Concatenating into {args.output}...")
    concat_list = wd / "cache_dir" / "_run_all_concat_list.txt"
    concat_list.parent.mkdir(exist_ok=True)
    with concat_list.open("w") as f:
        for stem in scenes:
            f.write(f"file '{rendered_paths[stem].resolve()}'\n")

    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", args.output],
        cwd=wd,
    )
    concat_list.unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"Error: ffmpeg failed to concatenate the rendered videos (exit code {result.returncode}).", file=sys.stderr)
        return 1

    print(f"Combined video written to {wd / args.output}")
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Set up directory structure for a new project")

    sub.add_parser("list", help="List all the scenes added")

    add_p = sub.add_parser("add", help="Add a new manim scene")
    add_p.add_argument("stem", help="File stem, e.g. 'global_max' if the file is called 'global_max.py'")
    add_p.add_argument("--class-name", help="Override class name (default: CamelCase of stem)")
    add_p.add_argument(
        "--position",
        type=int,
        help="Position in scenes list, 0-based (default: end)",
    )
    add_p.add_argument("--force", action="store_true", help="Overwrite existing .py file")

    prune_p = sub.add_parser(
        "prune",
        help="Delete old podcasts/raw voiceovers, keeping only the most recent (renumbered to 1)",
    )
    prune_p.add_argument(
        "stem", nargs="?", help="File stem to prune (default: every scene in scenes.txt)"
    )

    run_all_p = sub.add_parser(
        "run_all",
        help="Render every scene in scenes.txt in order, then concatenate them into one video",
    )
    run_all_p.add_argument(
        "-q", "--quality",
        choices=["l", "m", "h", "p", "k"],
        default="l",
        help="Manim render quality: l/m/h/p/k (default: l)",
    )
    run_all_p.add_argument(
        "-o", "--output",
        default="full_video.mp4",
        help="Filename for the combined video (default: full_video.mp4)",
    )

    args = p.parse_args()

    if args.command == "init":
        return cmd_init(args)
    if args.command == "list":
        return cmd_list(args)
    elif args.command == "add":
        return cmd_add(args)
    elif args.command == "prune":
        return cmd_prune(args)
    elif args.command == "run_all":
        return cmd_run_all(args)
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
