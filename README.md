# stitch-tools

This repo is designed for use with `StitcherService` in Manim. This enables users to record without leaving pauses between voiceover chunks.
`insert_silences` reads the text of the manim script, transcribes the voiceover, and inserts silences in between the spoken words of the voiceover chunks. It is moderately robust to mis-speaking words.
It is currently actively under development.

## Prerequisites
- Python >= 3.11
- `ffmpeg` on your PATH (used by `pydub` for audio conversion). Install with `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux).
- It is strongly recommended to use this repo with `uv`.

## How to use

1. Create a new directory for your project.
2. Type `uv init`
3. Add this project:
   - From GitHub: `uv add git+https://github.com/noah59049/stitch-tools.git`
   - From a local clone (e.g. if you're developing stitch-tools itself): clone it as a **sibling** of your video project (not nested inside it), then run `uv add --editable ../stitch-tools` (adjust the path to wherever you cloned it). This installs it in editable mode, so changes to your local clone take effect immediately without reinstalling.
4. Type `stitch_tools init`. This creates the `podcasts/`, `raw_voiceovers/`, `transcripts/`, and `cache_dir/` directories, adds them (plus `media/`) to `.gitignore`, creates an empty `scenes.txt` (a list of scene stems, in order, used by `stitch_tools run_all` — see below), and runs `uv add manim manim_voiceover` for you.

### Create a new scene
Whenever you want to create a new voiceover scene, run the command
`stitch_tools add name_of_scene` (do not include the `.py` extension). This creates `name_of_scene.py` and adds `name_of_scene` to `scenes.txt`.

The generated file subclasses `StitcherScene` (from `stitcher_scene.py`) instead of `VoiceoverScene`. Override `construct_scene(self)` instead of `construct(self)` — `StitcherScene.construct()` finds and loads the matching podcast audio (`podcasts/name_of_scene_podcast*.wav`) and calls `self.set_speech_service(...)` for you before running `construct_scene()`.

If no podcast audio exists yet for the scene, `StitcherScene` doesn't error at startup — it prints a warning and leaves the speech service unset, so you can keep writing/running the scene before you've recorded anything. The error is only raised once you actually call `self.voiceover(...)`.

### Deprecate a scene
To retire a scene without deleting it, run `stitch_tools deprecate name_of_scene`. This removes `name_of_scene` from `scenes.txt` and moves `name_of_scene.py` into a `deprecated/` directory (created if needed). If only one of those applies (e.g. the file exists but isn't in `scenes.txt`), it does that part and warns about the other; if neither applies, it prints an error. It refuses to overwrite an existing file in `deprecated/`. `deprecated/` is not gitignored, so deprecated scenes stay in version control.

#### Silencing voiceovers
You can disable voiceovers entirely (no audio, and no error even if the podcast file is missing) in two ways:
- In code: set `silent = True` on the scene class, or `self.silent = True` before calling `self.voiceover(...)`.
- From the command line: set the `STITCH_SILENT` environment variable, e.g. `STITCH_SILENT=1 manim -pql name_of_scene.py NameOfScene`. This silences every `StitcherScene` in the process, without editing any code.

While silenced, `self.voiceover(...)` still works as a context manager (so your `with self.voiceover(...):` blocks and animation timing stay intact), it just plays no audio and adds no wait time.

### Get a transcript
If you want to get a PDF of the transcript of the scene, run the command `extract_voiceovers -s scene_name`.
The PDF will be in the `transcripts/` directory. For more options of how to run `extract_voiceovers`, type `extract_voiceovers --help`.

### Insert silences
You need an audio file with the words from your voiceovers. It is intended to read from the PDF transcript created by `extract_voiceovers`.
The audio file should be named `scene_name{number}`. For the first audio file, it should be named `scene_name1`, and subsequent audio files should be named `scene_name2`, `scene_name3`, etc.
Supported extensions are `.wav`, `.mp3`, and `.m4a`. However, all files will be converted to `.wav`.

Put the audio file in the `raw_voiceovers` directory, then run the command `insert_silences -s scene_name`.
You are now ready to run your script!
Internally, `insert_silences` creates an audio file with silences inserted in the `podcasts` directory, and they are named `scene_name_podcast{number}.wav`, with the same pattern of increasing numbers as above.

**Warning:** if your raw voiceover is `.mp3` or `.m4a`, `insert_silences` converts it to `.wav` in place and then **deletes the original file**. Since `raw_voiceovers/` is gitignored, that original recording is not recoverable once deleted.

`insert_silences` also accepts `--silence` (seconds of silence to insert at each line break, default 5.0) and `--model` (faster-whisper model size: `tiny`, `base`, `small`, `medium`, or `large-v3`; default `base` — larger models are slower but more accurate). The first time you use a given model size, faster-whisper downloads it, which requires internet access and may take a while. For more options, type `insert_silences --help`.

By default, every run of `insert_silences -s scene_name` creates a new numbered podcast (`scene_name_podcast1.wav`, `_podcast2.wav`, ...) rather than touching the old ones. If you don't need to keep every past take, pass `--overwrite` to have it overwrite the most recent podcast in place instead of creating a new one.

It is not necessary to re-record if the transcript has not changed. For example, if you change
```
with self.voiceover("sine of a plus b is sine a cosine b plus cosine a sine b") as tracker:
  self.play(Write(tex1))
with self.voiceover("cosine of a plus b is cosine a cosine b minus sine a sine b") as tracker:
  self.play(Write(tex2))
```
to 
```
with self.voiceover("sine of a plus b is sine a cosine b plus cosine a sine b. cosine of a plus b is") as tracker:
  self.play(Write(tex1))
with self.voiceover("cosine a cosine b minus sine a sine b") as tracker:
  self.play(Write(tex2))
```
The transcript is not different between these. Therefore, it is possible to simply re-run `insert_silences` without re-recording.

### Run all scenes and stitch them together
Once your scenes are ready, run `stitch_tools run_all` to render every scene listed in `scenes.txt`, in order, and concatenate them into a single video.

Each scene is rendered with `manim` in turn. If a scene fails to render, `run_all` prints the error, leaves the scenes already rendered in `media/` alone, and **keeps going** with the remaining scenes rather than stopping the whole run. However, if any scene failed, the videos are not concatenated into one file — you'll need to fix the failing scene(s) and re-run `stitch_tools run_all` before you get a combined video.

If every scene renders successfully, the individual videos are concatenated (via `ffmpeg`) into one output file.

Options:
- `-q/--quality {l,m,h,p,k}` — manim render quality, same letters as manim's `-q` flag (default: `l`).
- `-o/--output` — filename for the combined video (default: `full_video.mp4`).

### Saving disk space: pruning old podcasts and raw voiceovers
Since every take is kept by default (or via `insert_silences` without `--overwrite`), `podcasts/` and `raw_voiceovers/` can accumulate a lot of old audio over time. Two commands help clean this up:

- `stitch_tools prune [stem]` — for the given scene (or every scene in `scenes.txt` if no stem is given), deletes all but the most recent podcast and raw voiceover, renumbering the survivor back to `1`. Also cleans up the `.json` cache file that `StitcherService` writes next to each podcast wav.
- `stitch_tools prune_all` — does the same for every scene in `scenes.txt`, and additionally **deletes every podcast and raw voiceover file that doesn't belong to any scene listed in `scenes.txt`** (e.g. leftovers from a scene you renamed or removed). Pass `--keep-orphans` to skip that second step and only prune old numbered files for tracked scenes. `prune_all` refuses to run if `scenes.txt` is empty, so it can't accidentally wipe everything.

## Note
the `-s` command is short for `--stem`, and such, do not include any file extensions in the stem.

## Limitations / Future improvements planned
- Both `extract_voiceovers` and `insert_silences` only recognize `with self.voiceover("text") as tracker:` as a valid voiceover line. Therefore, this doesn't work well if the voiceover text is calculated at runtime.
- Detection of mathematical formulae are not very robust; for this reason, it is recommended to write out `cosine of a plus b` rather than `cos(a+b)`, for example.
