"""Download one meeting from the AMI Meeting Corpus (CC BY 4.0) for a real-model test run.

Run from backend/:  uv run python -m scripts.fetch_ami_sample ES2002b
The headset mix of ES2002b is about 73 MB. Files are saved to data/samples/.
"""

import argparse
import re
import shutil
import urllib.request
from pathlib import Path

from app.pipeline.ingest import probe_audio

AMI_MIRROR = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
SAMPLES_DIR = Path("data/samples")


def sample_url(meeting_id: str) -> str:
    """The headset-mix recording of one AMI meeting, such as ES2002b or IB4001."""
    if not re.fullmatch(r"[A-Z]{2}\d{4}[a-z]?", meeting_id):
        raise ValueError(f"{meeting_id!r} is not an AMI meeting ID such as ES2002b")
    return f"{AMI_MIRROR}/{meeting_id}/audio/{meeting_id}.Mix-Headset.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one AMI meeting recording.")
    parser.add_argument("meeting_id", help="for example ES2002b")
    args = parser.parse_args()
    try:
        url = sample_url(args.meeting_id)
    except ValueError as exc:
        parser.error(str(exc))

    dest = SAMPLES_DIR / f"{args.meeting_id}.wav"
    if dest.exists():
        print(f"Already downloaded: {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(".part")
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.replace(dest)

    duration = probe_audio(dest).duration_s
    length = f"{duration / 60:.1f} minutes" if duration is not None else "unknown length"
    print(f"{dest}: {length}")


if __name__ == "__main__":
    main()
