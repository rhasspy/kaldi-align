# Kaldi Align

A basic forced aligner using Kaldi.

Install:

```sh
$ pip install kaldi-align
```

Create a JSONL alignment file from WAV files and a CSV file with the format `id|text`:

```sh
$ kaldi-align \
    --model en-us \
    --metadata /path/to/metadata.csv \
    --audio-files <(find /path/to/wavs -name '*.wav' -type f) \
    --output-file alignments.jsonl
```

Clip silence from WAV files:

```sh
$ align2wavs \
    --metadata /path/to/metadata.csv \
    --audio-files <(find /path/to/wavs -name '*.wav' -type f) \
    --alignments alignments.json \
    --output-dir /path/to/aligned/wavs/
```

## Dependencies

* ffmpeg
