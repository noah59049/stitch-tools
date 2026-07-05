# stitch-tools

This repo is designed for use with `StitcherService` in Manim. This enables users to record without leaving pauses between voiceover chunks.
`insert_silences` reads the text of the manim script, transcribes the voiceover, and inserts silences in between the spoken words of the voiceover chunks. It is moderately robust to mis-speaking words.
It is currently actively under development.

## How to use

It is strongly recommended to use this repo with `uv`.

1. Create a new directory for your project.
2. Type `uv init`
3. Add this project: `uv add git+https://github.com/noah59049/stitch-tools.git`
4. type `stitch_tools init`

### Create a new scene
Whenever you want to create a new voiceover scene, run the command
`stitch_tools add name_of_scene.py`

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

## Note
the `-s` command is short for `--stem`, and such, do not include any file extensions in the stem.

## Limitations / Future improvements planned
- Both `extract_voiceovers` and `insert_silences` only recognize `with self.voiceover("text") as tracker:` as a valid voiceover line. Therefore, this doesn't work well if the voiceover text is calculated at runtime.
- Detection of mathematical formulae are not very robust; for this reason, it is recommended to write out `cosine of a plus b` rather than `cos(a+b)`, for example.
- I want to create a subclass of `VoiceoverScene` that reduces the amount of boilerplate in a new scene.
- Currently, it is required to have an audio clip to run; however, I want the subclass I make to remove that requirement.
- I plan to create a `stitch_tools run_all` command that runs all the scenes that have been added with `stitch_tools add` in order, then concatenates them into one video. This will use `scenes.txt`.
