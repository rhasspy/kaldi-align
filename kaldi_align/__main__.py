#!/usr/bin/env python3
import argparse
import json
import logging
import math
import os
import platform
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

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

    if args.kaldi_dir:
        kaldi_dir = Path(args.kaldi_dir).absolute()
    else:
        kaldi_dir = Path("kaldi").absolute()

    bin_dir = kaldi_dir / "x86_64"
    _LOGGER.debug("Kaldi binaries expected in %s", bin_dir)

    model_dir = _DIR / "models" / args.model
    if not model_dir.is_dir():
        model_dir = Path(args.model).absolute()

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
    steps_dir.symlink_to(kaldi_dir / "steps", target_is_directory=True)
    utils_dir.symlink_to(kaldi_dir / "utils", target_is_directory=True)
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

    # Create text, utt2spk, wav.scp
    data_dir = output_dir / "data"
    align_dir = data_dir / "align"
    lang_dir = model_dir / "data" / "lang"

    metadata_csv = Path(args.metadata_csv)
    wav_dir = metadata_csv.parent
    speaker = "speaker1"
    speakers = [speaker]
    align_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Loading transcriptions from %s", metadata_csv)
    utterances = {}
    kaldi_to_utt = {}
    with open(metadata_csv, "r") as metadata_file:
        for line in metadata_file:
            line = line.strip()
            if not line:
                continue

            utt_id, text = line.split("|", maxsplit=1)
            utterances[utt_id] = text

    sorted_utt_ids = sorted(utterances.keys())
    num_digits = int(math.ceil(math.log10(len(sorted_utt_ids))))

    _LOGGER.debug("Writing Kaldi files to %s", align_dir)
    with open(align_dir / "text", "w") as text_file, open(
        align_dir / "utt2spk", "w"
    ) as utt2spk_file, open(align_dir / "id2utt", "w") as id_file, open(
        align_dir / "wav.scp", "w"
    ) as scp_file:
        for utt_index, utt_id in enumerate(sorted_utt_ids):
            kaldi_utt_id = f"{speaker}-%0{num_digits}d" % utt_index
            kaldi_to_utt[kaldi_utt_id] = utt_id

            print(utt_id, kaldi_utt_id, file=id_file)

            wav_path = wav_dir / (utt_id + ".wav")
            text = utterances[utt_id]

            print(kaldi_utt_id, text, file=text_file)
            print(kaldi_utt_id, speaker, file=utt2spk_file)
            print(
                kaldi_utt_id, f"sox {wav_path} -r 16000 -c 1 -t wav -|", file=scp_file
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
    run("steps/compute_cmvn_stats.sh", str(align_dir), str(mfcc_exp_dir), str(mfcc_dir))
    fix_data_dir()

    # -----
    # Align
    # -----
    src_dir = model_dir / "model"
    exp_dir = output_dir / "exp" / "align"
    num_align_jobs = min(args.num_jobs, len(speakers))

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
    run(str(kaldi_dir / "get_phones.sh"), str(align_dir), str(lang_dir), str(exp_dir))

    _LOGGER.info("Alignment finished")

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

        json.dump({"id": utt_id, "words": utt_words, "ipa": ipas}, sys.stdout)
        print("")


# -----------------------------------------------------------------------------


def get_args():
    parser = argparse.ArgumentParser(prog="kaldi-align")
    parser.add_argument("metadata_csv", help="Path to CSV metadata with id|text")
    # parser.add_argument(
    #     "--speakers", action="store_true", help="Metadata format is id|speaker|text"
    # )
    parser.add_argument("--model", required=True, help="Name or path of Kaldi model")
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
        "--debug", action="store_true", help="Print DEBUG messages to the console"
    )

    return parser.parse_args()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
