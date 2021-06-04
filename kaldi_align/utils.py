"""Utility methods for kaldi_align"""
import csv
import logging
import shutil
import tempfile
import typing
from pathlib import Path

import requests
from gruut_ipa import IPA, Phonemes
from tqdm.auto import tqdm

_LOGGER = logging.getLogger("kaldi_align.utils")

LANG_ALIAS = {
    "cs": "cs-cz",
    "de": "de-de",
    "en": "en-us",
    "es": "es-es",
    "fr": "fr-fr",
    "it": "it-it",
    "ru": "ru-ru",
    "sv": "sv-se",
}

# -----------------------------------------------------------------------------


def download_kaldi(url_format: str, extract_dir: typing.Union[str, Path]):
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    url = url_format.format(file="kaldi_x86_64.tar.gz")

    try:
        with tempfile.NamedTemporaryFile(mode="wb+", suffix=".tar.gz") as kaldi_file:
            download_file(url, kaldi_file)

            kaldi_file.seek(0)
            _LOGGER.debug("Extracting %s to %s", kaldi_file.name, extract_dir)
            shutil.unpack_archive(kaldi_file.name, extract_dir=extract_dir)
    except Exception as e:
        _LOGGER.fatal("download_kaldi")
        raise e


def download_model(
    url_format: str, model_name: str, extract_dir: typing.Union[str, Path]
):
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    url = url_format.format(file=f"{model_name}.tar.gz")

    try:
        with tempfile.NamedTemporaryFile(mode="wb+", suffix=".tar.gz") as model_file:
            download_file(url, model_file)

            model_file.seek(0)
            _LOGGER.debug("Extracting %s to %s", model_file.name, extract_dir)
            shutil.unpack_archive(model_file.name, extract_dir=extract_dir)
    except Exception as e:
        _LOGGER.fatal("download_model(%s)", model_name)
        raise e


def download_file(url: str, out_file: typing.IO[typing.Any], chunk_size: int = 4096):
    """Download a single file with progress"""
    _LOGGER.debug("Downloading %s", url)

    response = requests.get(url, stream=True)
    assert response.ok, url

    with tqdm.wrapattr(
        out_file,
        "write",
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        miniters=1,
        desc=url.split("/")[-1],
        total=int(response.headers.get("content-length", 0)),
    ) as fout:
        for chunk in response.iter_content(chunk_size=chunk_size):
            fout.write(chunk)


# -----------------------------------------------------------------------------


def load_metadata(
    metadata_path: typing.Union[str, Path], has_speaker: bool = False, delimiter="|"
) -> typing.Dict[str, typing.Union[str, typing.Tuple[str, str]]]:
    """Load a CSV file with id|text or id|speaker|text"""
    texts: typing.Dict[str, typing.Union[str, typing.Tuple[str, str]]] = {}
    with open(metadata_path, "r") as metadata_file:
        for row in csv.reader(metadata_file, delimiter=delimiter):
            if has_speaker:
                utt_id, speaker, text = row[0], row[1], row[2]
                texts[utt_id] = (speaker, text)
            else:
                utt_id, text = row[0], row[1]
                texts[utt_id] = text

    return texts


# -----------------------------------------------------------------------------

_LANG_STRESS = {"en-us": True, "fr-fr": True, "es-es": True, "it-it": True}


def id_to_phonemes(
    lang: str,
    pad: str = "_",
    no_pad: bool = False,
    no_word_break: bool = False,
    no_stress: typing.Optional[bool] = False,
    no_accents: typing.Optional[bool] = None,
    tones: typing.Optional[typing.Iterable[str]] = None,
) -> typing.Sequence[str]:
    """Create an ordered list of phonemes for a language."""
    lang_phonemes = [p.text for p in Phonemes.from_language(lang)]

    if no_stress is None:
        no_stress = not _LANG_STRESS.get(lang, False)

    if no_accents is None:
        # Only add accents for Swedish
        no_accents = lang != "sv-se"

    # Acute/grave accents (' and ²)
    accents = []
    if not no_accents:
        # Accents from Swedish, etc.
        accents = [IPA.ACCENT_ACUTE.value, IPA.ACCENT_GRAVE.value]

    # Primary/secondary stress (ˈ and ˌ)
    # NOTE: Accute accent (0x0027) != primary stress (0x02C8)
    stresses = []
    if not no_stress:
        stresses = [IPA.STRESS_PRIMARY.value, IPA.STRESS_SECONDARY.value]

    # Tones
    tones = list(tones) if tones is not None else []

    # Word break
    word_break = []
    if not no_word_break:
        word_break = [IPA.BREAK_WORD.value]

    # Pad symbol must always be first (index 0)
    phonemes_list = []
    if not no_pad:
        phonemes_list.append(pad)

    # Order here is critical
    phonemes_list = (
        phonemes_list
        + [IPA.BREAK_MINOR.value, IPA.BREAK_MAJOR.value]
        + word_break
        + accents
        + stresses
        + tones
        + sorted(list(lang_phonemes))
    )

    return phonemes_list
