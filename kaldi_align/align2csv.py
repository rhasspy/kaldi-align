#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path

from gruut_ipa import IPA

from .utils import LANG_ALIAS, id_to_phonemes

_LOGGER = logging.getLogger("align2csv")

SKIP_PHONES = {"SIL", "SPN", "NSN"}

# -----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(prog="align2csv")
    parser.add_argument("--language", required=True, help="gruut language")
    parser.add_argument(
        "--alignments", required=True, help="Path to alignment JSONL file"
    )
    parser.add_argument(
        "--phoneme-ids", help="Path to write text file with phoneme ids"
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
    args.alignments = Path(args.alignments)

    args.language = LANG_ALIAS.get(args.language, args.language)
    phoneme_ids = id_to_phonemes(args.language)
    phonemes_to_id = {p: i for i, p in enumerate(phoneme_ids)}

    # -------------------------------------------------------------------------

    if args.phoneme_ids:
        # Write text file with format:
        # id phoneme
        # where id is a 0-based index and phoneme a string
        with open(args.phoneme_ids, "w") as ids_file:
            for i, p in enumerate(phoneme_ids):
                print(i, p, file=ids_file)

    # -------------------------------------------------------------------------

    with open(args.alignments, "r") as alignments_file:
        # Read alignments
        for line in alignments_file:
            pron_obj = json.loads(line)

            split_phonemes = []
            for phoneme in pron_obj["ipa"]:
                if not phoneme:
                    continue

                while phoneme and IPA.is_stress(phoneme[0]):
                    split_phonemes.append(phoneme[0])
                    phoneme = phoneme[1:]

                if phoneme:
                    split_phonemes.append(phoneme)

            try:
                pron_ids = [
                    phonemes_to_id[p] for p in split_phonemes if p not in SKIP_PHONES
                ]
                print(pron_obj["id"], end="|")
                print(*pron_ids)
            except Exception:
                _LOGGER.exception(line)


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
