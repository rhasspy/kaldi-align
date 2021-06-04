"""Utility methods for kaldi_align"""
import logging
import shutil
import tempfile
import typing
from pathlib import Path

import requests
from tqdm.auto import tqdm

_LOGGER = logging.getLogger("kaldi_align.utils")

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
