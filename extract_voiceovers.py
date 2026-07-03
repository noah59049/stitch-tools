#!/usr/bin/env python3
"""
extract_voiceovers.py — Extract self.voiceover() strings from a manim script,
one per line, in order of appearance.

Usage:
    python extract_voiceovers.py -i scene.py              # prints to stdout
    python extract_voiceovers.py -i scene.py -o lines.txt # writes to file
    python extract_voiceovers.py -i scene.py -o lines.pdf # writes to PDF

Install:
    pip install fpdf2   # only needed for PDF output
"""

import argparse
import re
import sys
from pathlib import Path
import dir_config


def extract_voiceovers(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    pattern = re.compile(r"""self\.voiceover\(\s*(?:"([^"]+)"|'([^']+)')""")
    results = []
    for m in pattern.finditer(text):
        line_start = text.rfind('\n', 0, m.start()) + 1
        if '#' not in text[line_start:m.start()]:
            results.append(m.group(1) or m.group(2))
    return results


_UNICODE_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',   # curly double quotes
    "—": "--", "–": "-",  # em dash, en dash
    "…": "...",                # ellipsis
})


def _asciify(text: str) -> str:
    return text.translate(_UNICODE_TO_ASCII)


def write_pdf(lines: list[str], path: str) -> None:
    from fpdf import FPDF, XPos, YPos  # type: ignore

    stem = Path(path).stem
    pdf = FPDF()
    pdf.set_margins(5,5,5)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _asciify(stem), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.multi_cell(0, 6, _asciify(line))
        pdf.ln(1)

    pdf.output(path)


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-i", "--input", help="Manim Python script")
    p.add_argument("-o", "--output", help="Output file: .txt, .pdf, or omit for stdout")
    p.add_argument("-s", "--stem", help="File stem, e.g. 'intro_with_tables' or 'directional_derivative'")
    p.add_argument("-x", "--extension", help="File extension for transcript, either 'pdf' or 'txt'")
    p.add_argument("-l", "--linebreaks", help="If true, inserts a line break between each voiceover call. If false, does not. Defaults to true for txt and false for pdf")
    args = p.parse_args()

    if args.stem:
        if args.extension:
            extension = "." + args.extension
        else:
            extension = ".pdf"
        args.input = dir_config.path_to_manim_script(args.stem)
        args.output = dir_config.path_to_transcript(args.stem, extension=extension)

    lines = extract_voiceovers(args.input)
    if not lines:
        print("No self.voiceover() calls found.", file=sys.stderr)
        return 1
    

    if args.linebreaks:
        if args.linebreaks.lower() == "false":
            lines = [" ".join(lines)]
        elif args.linebreaks.lower() == "true":
            pass
        else:
            print(f"Invalid value {args.linebreaks} for linebreaks", file=sys.stderr)
            return 1
    elif Path(args.output).suffix.lower() == ".pdf": # linebreaks for txt, not for pdf
        lines = [" ".join(lines)]

    if args.output:
        if Path(args.output).suffix.lower() == ".pdf":
            write_pdf(lines, args.output)
        else:
            Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(lines)} lines to {args.output}", file=sys.stderr)
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
