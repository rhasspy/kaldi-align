# Kaldi Align

A basic forced aligner using Kaldi.

## Installation:

```sh
$ git clone https://github.com/rhasspy/kaldi-align
$ cd kaldi-align
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip3 install --upgrade pip
$ pip3 install --upgrade wheel setuptool
$ pip3 install -r requirements.txt
```

You will also need some system libraries for Kaldi and ffmpeg to convert audio:

```sh
$ sudo apt-get install libopenblas-base libgfortran5 ffmpeg
```

## Alignment

Create a JSONL alignment file from WAV files and a CSV file with the format `id|text`:

```sh
$ bin/kaldi-align \
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
$ bin/align2csv \
    --language <LANG> \
    --alignments alignments.json \
    > /path/to/phonemes.csv
```

where `<LANG>` is one of [gruut's supported languages](https://github.com/rhasspy/gruut#supported-languages).

### Trimmed WAV Files

Trim silence from WAV files:

```sh
$ bin/align2wavs \
    --metadata /path/to/metadata.csv \
    --audio-files <(find /path/to/wavs -name '*.wav' -type f) \
    --alignments alignments.json \
    --output-dir /path/to/aligned/wavs/
```

Trimmed versions of all WAV files *with at least one word* will writen to `--output-dir` along with the metadata from `--metadata`.

If your metadata CSV file has the format `id|speaker|text`, pass `--has-speaker` to `align2wavs`.

## Dependencies

* [gruut](https://github.com/rhasspy/gruut)
* ffmpeg
* [pydub](https://github.com/jiaaro/pydub)
