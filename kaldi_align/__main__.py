#!/usr/bin/env python3
import argparse
import csv
import logging
import math
import os
import platform
import subprocess
import sys
import tempfile
import typing
from collections import defaultdict
from pathlib import Path

import gruut
import jsonlines

from .utils import LANG_ALIAS, download_kaldi, download_model

_LOGGER = logging.getLogger("kaldi_align")

_DIR = Path(__file__).parent
_ENV = dict(os.environ)

_TRAIN_CMD = "utils/run.pl"

_WORD_BREAK = "#"

_SILENCE_PHONE = "SIL"

_BREAK_MINOR = "|"
_BREAK_MAJOR = "\u2016"  # ‖

_FRAMES_PER_SEC = 100

# -----------------------------------------------------------------------------


def main():
    """Main entry point"""
    args = get_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    _LOGGER.debug(args)

    # Set download directory for model files
    if args.download_dir:
        args.download_dir = Path(args.download_dir)
    else:
        if "XDG_DATA_HOME" in os.environ:
            share_home = Path(os.environ["XDG_DATA_HOME"])
        else:
            share_home = Path("~/.local/share").expanduser()

        args.download_dir = share_home / "kaldi-align"

    _LOGGER.debug("Download directory: %s", args.download_dir)

    if args.kaldi_dir:
        args.kaldi_dir = Path(args.kaldi_dir).absolute()
    else:
        args.kaldi_dir = (args.download_dir / "kaldi").absolute()

    # Download kaldi
    if not args.kaldi_dir.is_dir():
        _LOGGER.info("Need to download Kaldi")
        download_kaldi(args.url_format, args.kaldi_dir.parent)
        _LOGGER.info("Kaldi downloaded to %s", args.kaldi_dir)

    bin_dir = args.kaldi_dir / "x86_64"
    _LOGGER.debug("Kaldi binaries expected in %s", bin_dir)

    # Download model
    language: typing.Optional[str] = None
    model_dir = Path(args.model)
    if not model_dir.is_dir():
        # Model is a name instead of a directory
        args.model = LANG_ALIAS.get(args.model, args.model)
        language = args.model
        model_dir = args.download_dir / "models" / args.model

        if not model_dir.is_dir():
            _LOGGER.info("Need to download model for %s", args.model)
            download_model(args.url_format, args.model, model_dir.parent)
            _LOGGER.info("Model downloaded to %s", model_dir)

    # -------------------------------------------------------------------------

    temp_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir).absolute()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.TemporaryDirectory()
        output_dir = Path(temp_dir.name)

    steps_dir = output_dir / "steps"
    utils_dir = output_dir / "utils"
    conf_dir = output_dir / "conf"
    model_link_dir = output_dir / "model"

    # Delete existing links
    for link_dir in [steps_dir, utils_dir, conf_dir, model_link_dir]:
        if link_dir.is_dir():
            link_dir.unlink()

    # Create new links
    steps_dir.symlink_to(args.kaldi_dir / "steps", target_is_directory=True)
    utils_dir.symlink_to(args.kaldi_dir / "utils", target_is_directory=True)
    conf_dir.symlink_to(model_dir / "conf", target_is_directory=True)
    model_link_dir.symlink_to(model_dir, target_is_directory=True)

    _ENV["LC_ALL"] = "C"
    _ENV["PATH"] = ":".join([str(bin_dir), str(utils_dir), _ENV["PATH"]])

    def run(*command):
        try:
            output = subprocess.check_output(
                command,
                cwd=output_dir,
                env=_ENV,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )

            if output:
                print(output, file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(e.output, file=sys.stderr)
            raise e

    # -------------------------------------------------------------------------

    # Create text, utt2spk, wav.scp
    data_dir = output_dir / "data"
    align_dir = data_dir / "align"
    lang_dir = model_dir / "data" / "lang"

    metadata_csv = Path(args.metadata)

    if args.clean_metadata:
        args.clean_metadata = Path(args.clean_metadata)
        args.clean_metadata.parent.mkdir(parents=True, exist_ok=True)

    audio_paths = {}

    with open(args.audio_files, "r") as audio_files:
        for line in audio_files:
            line = line.strip()
            if not line:
                continue

            audio_path = Path(line)

            # Stem is utterance id
            audio_paths[audio_path.stem] = audio_path

    align_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Loading transcriptions from %s", metadata_csv)

    tokenizer: typing.Optional[gruut.Tokenizer] = None

    if language is not None:
        tokenizer = gruut.lang.get_tokenizer(language)

    # utt id -> (speaker, text)
    utterances = {}

    # generate utt id -> real utt id
    kaldi_to_utt = {}

    speakers = set()

    clean_writer = (
        csv.writer(args.clean_metadata, delimiter="|") if args.clean_metadata else None
    )

    with open(metadata_csv, "r") as metadata_file:
        for row in csv.reader(metadata_file, delimiter="|"):
            if args.has_speaker:
                utt_id, speaker, text = row[0], row[1], row[2]
            else:
                utt_id, text = row[0], row[1]
                speaker = "speaker1"

            if tokenizer:
                # Clean text with gruut
                clean_words = []
                for sentence in tokenizer.tokenize(text):
                    clean_words.extend(
                        t.text for t in sentence.tokens if tokenizer.is_word(t.text)
                    )

                text = tokenizer.join_str.join(clean_words)

            utterances[utt_id] = (speaker, text)
            speakers.add(speaker)

            if clean_writer:
                if args.has_speaker:
                    writer.writerow((utt_id, speaker, text))
                else:
                    writer.writerow((utt_id, text))

    if clean_writer:
        clean_writer.close()
        clean_writer = None

    sorted_utt_ids = sorted(utterances.keys())
    num_digits = int(math.ceil(math.log10(len(sorted_utt_ids))))

    _LOGGER.debug("Writing Kaldi files to %s", align_dir)
    with open(align_dir / "text", "w") as text_file, open(
        align_dir / "utt2spk", "w"
    ) as utt2spk_file, open(align_dir / "id2utt", "w") as id_file, open(
        align_dir / "wav.scp", "w"
    ) as scp_file:
        for utt_index, utt_id in enumerate(sorted_utt_ids):
            speaker, text = utterances[utt_id]

            # Use a generated utterance id for Kaldi to avoid sorting issues
            kaldi_utt_id = f"{speaker}-%0{num_digits}d" % utt_index
            kaldi_to_utt[kaldi_utt_id] = utt_id

            print(utt_id, kaldi_utt_id, file=id_file)

            audio_path = audio_paths.get(utt_id)
            if audio_path is None:
                audio_path = metadata_csv.parent / f"{utt_id}.wav"
                if not audio_path.is_file():
                    _LOGGER.warning("Missing audio file at %s", audio_path)
                continue

            print(kaldi_utt_id, text, file=text_file)
            print(kaldi_utt_id, speaker, file=utt2spk_file)
            print(
                kaldi_utt_id,
                f"ffmpeg -y -i {audio_path} -ar 16000 -ac 1 -acodec pcm_s16le -f wav -|",
                file=scp_file,
            )

    # Remove existing spk2utt file
    spk2utt_path = align_dir / "spk2utt"
    if spk2utt_path.is_file():
        spk2utt_path.unlink()

    def fix_data_dir():
        # Fix up data dir (creates spk2utt, etc.)
        run("utils/fix_data_dir.sh", str(align_dir))

    # -----
    # MFCC
    # -----
    mfcc_dir = output_dir / "mfcc"
    mfcc_exp_dir = output_dir / "exp" / "make_mfcc"
    num_mfcc_jobs = min(args.num_jobs, len(utterances))

    if not args.skip_mfccs:
        _LOGGER.debug("Creating MFCCs in %s (num_jobs=%s)", mfcc_exp_dir, num_mfcc_jobs)
        fix_data_dir()
        run(
            "steps/make_mfcc.sh",
            "--cmd",
            _TRAIN_CMD,
            "--nj",
            str(num_mfcc_jobs),
            str(align_dir),
            str(mfcc_exp_dir),
            str(mfcc_dir),
        )
        run(
            "steps/compute_cmvn_stats.sh",
            str(align_dir),
            str(mfcc_exp_dir),
            str(mfcc_dir),
        )
        fix_data_dir()

    # -----
    # Align
    # -----
    src_dir = model_dir / "model"
    exp_dir = output_dir / "exp" / "align"
    num_align_jobs = min(args.num_jobs, len(utterances))

    _LOGGER.debug("Aligning in %s (num_jobs=%s)", exp_dir, num_align_jobs)
    _LOGGER.info("Alignment started")
    run(
        "steps/align_fmllr.sh",
        "--cmd",
        _TRAIN_CMD,
        "--nj",
        str(num_align_jobs),
        str(align_dir),
        str(lang_dir),
        str(src_dir),
        str(exp_dir),
    )

    # ------
    # Phones
    # ------
    _LOGGER.debug("Getting word alignments...")
    run(
        str(args.kaldi_dir / "get_phones.sh"),
        str(align_dir),
        str(lang_dir),
        str(exp_dir),
    )

    _LOGGER.info("Alignment finished")

    # Save utterance mapping
    with open(output_dir / "utt_map.txt", "w") as mapping_file:
        for kaldi_utt_id, utt_id in kaldi_to_utt.items():
            print(kaldi_utt_id, utt_id, file=mapping_file)

    # ---------------
    # Convert to JSON
    # ---------------
    utt_words = defaultdict(list)

    _LOGGER.debug("Converting to JSON...")
    with open(exp_dir / "phones.prons", "r") as prons_file:
        for line in prons_file:
            line = line.strip()
            if not line:
                continue

            line_parts = line.split()
            kaldi_utt_id, start_frame, frame_durations, word = (
                line_parts[0],
                int(line_parts[1]),
                [int(f) for f in line_parts[2].split(",")],
                line_parts[3],
            )

            phone_strs = line_parts[4:]
            utt_id = kaldi_to_utt[kaldi_utt_id]

            word_phones = []
            phone_start_frame = start_frame
            for phone_str, phone_frames in zip(phone_strs, frame_durations):
                split_idx = phone_str.rfind("_")

                if split_idx > 0:
                    # X_B -> X
                    phone_str = phone_str[:split_idx]

                word_phones.append(
                    {
                        "start": phone_start_frame / _FRAMES_PER_SEC,
                        "duration": phone_frames / _FRAMES_PER_SEC,
                        "phone": phone_str,
                    }
                )

                phone_start_frame += phone_frames

            utt_words[utt_id].append({"word": word, "phones": word_phones})

    with open(args.output_file, "w") as output_file:
        writer: jsonlines.Writer = jsonlines.Writer(output_file)
        with writer:
            for utt_id, utt_words in utt_words.items():
                ipas = [_WORD_BREAK]
                for word_idx, utt_word in enumerate(utt_words):
                    if utt_word["word"] == "<eps>":
                        if 0 < word_idx < (len(utt_words) - 1):
                            ipas.append(_BREAK_MINOR)
                            ipas.append(_WORD_BREAK)
                    else:
                        ipas.extend(wp["phone"] for wp in utt_word["phones"])
                        ipas.append(_WORD_BREAK)

                ipas.append(_BREAK_MAJOR)

                writer.write({"id": utt_id, "words": utt_words, "ipa": ipas})


# -----------------------------------------------------------------------------


def get_args():
    parser = argparse.ArgumentParser(prog="kaldi-align")
    parser.add_argument(
        "--metadata", required=True, help="Path to read CSV metadata with id|text"
    )
    parser.add_argument("--clean-metadata", help="Path write clean CSV metadata")
    parser.add_argument(
        "--output-file", required=True, help="Path to write alignment JSONL"
    )
    parser.add_argument(
        "--has-speaker", action="store_true", help="Metadata has format id|speaker|text"
    )
    parser.add_argument(
        "--skip-mfccs",
        action="store_true",
        help="Assume MFCCs have already been created",
    )
    parser.add_argument("--model", required=True, help="Name or path of Kaldi model")
    parser.add_argument(
        "--audio-files", required=True, help="File with paths of audio files"
    )
    parser.add_argument(
        "--kaldi-dir", help="Path to Kaldi directory (default: $PWD/kaldi)"
    )
    parser.add_argument("--output-dir", help="Path to output directory (default: temp)")
    parser.add_argument(
        "--num-jobs", type=int, default=12, help="Number of Kaldi jobs (default: 12)"
    )
    parser.add_argument(
        "--machine",
        default=platform.machine(),
        help="CPU architecture (default: platform.machine())",
    )
    parser.add_argument(
        "--frames-per-second",
        type=int,
        default=100,
        help="Number of audio frames per second (default: 100)",
    )
    parser.add_argument(
        "--train-cmd",
        default="utils/run.pl",
        help="Kaldi $train_cmd (default: utils/run.pl)",
    )
    parser.add_argument(
        "--url-format",
        default="https://github.com/rhasspy/kaldi-align/releases/download/v1.0/{file}",
        help="URL format string for downloading models (receives {file})",
    )
    parser.add_argument(
        "--download-dir",
        help="Directory to download models (default: $XDG_DATA_HOME/kaldi-align)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )

    return parser.parse_args()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
