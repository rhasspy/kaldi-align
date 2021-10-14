# Kaldi Align

A basic forced aligner using [Kaldi](https://kaldi-asr.org/) and [gruut](https://github.com/rhasspy/gruut) for [multiple human languages](#supported-languages).

## Installation:

```sh
git clone https://github.com/rhasspy/kaldi-align
cd kaldi-align

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip3 install --upgrade pip
pip3 install --upgrade wheel setuptool
pip3 install -r requirements.txt

kaldi-align --version
```

You will also need some system libraries for Kaldi and ffmpeg to convert audio:

```sh
$ sudo apt-get install libopenblas-base libgfortran5 ffmpeg
```

## Alignment

Create a JSONL alignment file from WAV files and a CSV file with the format `id|text`:

```sh
kaldi-align \
  --model en-us \
  --metadata /path/to/metadata.csv \
  --audio-files <(find /path/to/wavs -name '*.wav' -type f) \
  --output-file alignments.jsonl
```

Text from your metadata.csv file will be automatically cleaned using [gruut](https://github.com/rhasspy/gruut) (punctuation and non-words removed). You can save the cleaned metadata by providing a path to `--clean-metadata` (optional).

If your metadata CSV file has the format `id|speaker|text`, pass `--has-speaker` to `kaldi-align`.

With the alignment JSONL file, you can create:

* A CSV file with phoneme ids using [gruut](https://github.com/rhasspy/gruut) that is suitable for training a [Larynx](https://github.com/rhasspy/larynx)
* Trimmed versions of your WAV files with silence removed from front and back

### Phonemes CSV File

Create a CSV file with the format `id|P P P` where each `P` is a phoneme id.

```sh
align2csv \
  --language <LANG> \
  --alignments alignments.json \
  --phoneme-ids /path/to/phonemes.txt \
  > /path/to/phonemes.csv
```

where `<LANG>` is one of [gruut's supported languages](https://github.com/rhasspy/gruut#supported-languages). The `align2csv` script runs `python3 -m kaldi_align.align2csv` under the hood.

The `--phoneme-ids` path is optional, but recommended. It will write a text file with the map between IPA text phonemes and the integer ids used in the CSV output.

### Trimmed WAV Files

Trim silence from WAV files:

```sh
align2wavs \
  --metadata /path/to/metadata.csv \
  --audio-files <(find /path/to/wavs -name '*.wav' -type f) \
  --alignments alignments.json \
  --output-dir /path/to/aligned/wavs/
```

Trimmed versions of all WAV files *with at least one word* will writen to `--output-dir` along with the metadata from `--metadata`.  The `align2wavs` script runs `python3 -m kaldi_align.align2wavs` under the hood.

Note that `--audio-files` accepts a *file path* with an audio file path on each line. These paths should not contain spaces.

If your metadata CSV file has the format `id|speaker|text`, pass `--has-speaker` to `align2wavs`.

## Supported languages

Kaldi models will be automatically downloaded on first use and stored in `$HOME/.local/share/kaldi_align`. You may also [manually download them](https://github.com/rhasspy/kaldi-align/releases/tag/v1.0).

* Czech (`cs-cz`)
* German (`de-de`)
* English (`en-us`)
* Spanish (`es-es`)
* Persian/Farsi (`fa`)
* French (`fr-fr`)
* Italian (`it-it`)
* Dutch (`nl`)
* Russian (`ru-ru`)
* Swedish (`sv-se`)

## Dependencies

* [gruut](https://github.com/rhasspy/gruut)
* ffmpeg
* [pydub](https://github.com/jiaaro/pydub)
* [kaldi](http://kaldi-asr.org)
    * [Automatically downloaded](https://github.com/rhasspy/kaldi-align/releases/download/v1.0/kaldi_x86_64.tar.gz) on first use
