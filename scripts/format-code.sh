#!/usr/bin/env bash
set -e

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
src_dir="$(realpath "${this_dir}/..")"

venv="${src_dir}/.venv"
if [[ -d "${venv}" ]]; then
    source "${venv}/bin/activate"
fi

python_files=("${src_dir}/kaldi_align/"*.py "${src_dir}/bin/"*.py)

export PYTHONPATH="${src_dir}"

# -----------------------------------------------------------------------------

black "${python_files[@]}"
isort "${python_files[@]}"

# -----------------------------------------------------------------------------

echo "OK"
