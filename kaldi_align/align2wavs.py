#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path

from pydub import AudioSegment

from .utils import load_metadata

_LOGGER = logging.getLogger("align2wavs")

# -----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(prog="align2wavs")
    parser.add_argument("--metadata", required=True, help="Path to metadata CSV file")
    parser.add_argument(
        "--alignments", required=True, help="Path to alignment JSONL file"
    )
    parser.add_argument(
        "--audio-files", required=True, help="File with paths of audio files"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory with output audio files"
    )
    parser.add_argument(
        "--min-sec",
        default=0.5,
        help="Minimum number of seconds for a trimmed audio file (default: 0.5)",
    )
    parser.add_argument(
        "--buffer-sec",
        default=0.1,
        help="Seconds of audio to leave in trimmed file (default: 0.1)",
    )
    parser.add_argument(
        "--has-speaker", action="store_true", help="Metadata has format id|speaker|text"
    )

    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    _LOGGER.debug(args)

    # Convert to paths
    args.metadata = Path(args.metadata)
    args.alignments = Path(args.alignments)
    args.audio_files = Path(args.audio_files)
    args.output_dir = Path(args.output_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------

    # Load metadata
    _LOGGER.debug("Loading metadata from %s", args.metadata)
    texts = load_metadata(args.metadata, has_speaker=args.has_speaker)
    _LOGGER.info("Loaded %s utterance(s)", len(texts))

    # Cache file paths by stem
    audio_paths = {}
    with open(args.audio_files, "r") as audio_files:
        for line in audio_files:
            line = line.strip()
            if not line:
                continue

            audio_path = Path(line)

            # Stem is utterance id
            audio_paths[audio_path.stem] = audio_path

    out_metadata_path = args.output_dir / "metadata.csv"

    with open(out_metadata_path, "w") as out_metadata_file, open(
        args.alignments, "r"
    ) as alignments_file:
        # Read alignments
        for line_idx, line in enumerate(alignments_file):
            line = line.strip()
            if not line:
                continue

            try:
                align_obj = json.loads(line)
                utt_id = align_obj["id"]

                if args.has_speaker:
                    _speaker, utt_text = texts.get(utt_id)
                else:
                    utt_text = texts.get(utt_id)

                if not utt_text:
                    _LOGGER.warning("No text for %s", utt_id)
                    continue

                # Find sentence boundaries (exclude <eps> before and after)
                start_sec = -1
                end_sec = -1
                for word in align_obj["words"]:
                    if word["word"] != "<eps>":
                        if start_sec < 0:
                            start_sec = word["phones"][0]["start"]
                        else:
                            end_sec = (
                                word["phones"][-1]["start"]
                                + word["phones"][-1]["duration"]
                            )

                # Determine sentence audio duration
                start_sec = max(0, start_sec - args.buffer_sec)
                end_sec = end_sec + args.buffer_sec
                if start_sec > end_sec:
                    _LOGGER.warning("start > end: %s", align_obj)
                    continue

                if (end_sec - start_sec) < args.min_sec:
                    _LOGGER.warning("Trimmed audio < %s: %s", args.min_sec, align_obj)
                    continue

                src_path = audio_paths.get(utt_id)
                if src_path is None:
                    _LOGGER.warning("No audio file for id %s", utt_id)
                    continue

                # Load audio
                _LOGGER.debug("Loading audio from %s", src_path)
                audio = AudioSegment.from_file(str(src_path))

                # Write trimmed audio
                dest_path = args.output_dir / f"{utt_id}.wav"

                start_ms = int(start_sec * 1000)
                end_ms = int(end_sec * 1000)
                audio[start_ms:end_ms].export(str(dest_path), format="wav")

                # Write line to metadata
                print(utt_id, utt_text, sep="|", file=out_metadata_file)
            except Exception as e:
                _LOGGER.fatal("Error on line %s: %s", line_idx + 1, line)
                raise e


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
