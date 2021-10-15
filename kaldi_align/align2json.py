#!/usr/bin/env python3
import argparse
import logging
import os
from collections import defaultdict
from pathlib import Path

import jsonlines

from kaldi_align.const import _BREAK_MAJOR, _BREAK_MINOR, _FRAMES_PER_SEC, _WORD_BREAK

_LOGGER = logging.getLogger("kaldi_align")

# -----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir")
    parser.add_argument("output_file")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    exp_dir = output_dir / "exp" / "align"
    kaldi_to_utt = {}
    with open(output_dir / "utt_map.txt", "r", encoding="utf-8") as mapping_file:
        for line in mapping_file:
            line = line.strip()
            if not line:
                continue

            kaldi_utt_id, utt_id = line.split(maxsplit=1)
            kaldi_to_utt[kaldi_utt_id] = utt_id

    utt_words = defaultdict(list)

    _LOGGER.debug("Converting to JSON...")
    with open(exp_dir / "phones.prons", "r", encoding="utf-8") as prons_file:
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

    # Create output directory
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)

    with open(args.output_file, "w", encoding="utf-8") as output_file:
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

if __name__ == "__main__":
    main()
