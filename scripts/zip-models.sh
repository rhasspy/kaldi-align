#!/usr/bin/env bash
set -e

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
src_dir="$(realpath "${this_dir}/..")"

dist_dir="${src_dir}/dist"
mkdir -p "${dist_dir}/models"

models_dir="${src_dir}/kaldi_align/models"
pushd "${models_dir}" > /dev/null

find "${src_dir}/kaldi_align/models" -mindepth 1 -maxdepth 1 -type d | \
    while read -r model_dir;
    do
        # Create standalone distribution
        lang="$(basename "${model_dir}")"
        tar -czf "${dist_dir}/models/${lang}.tar.gz" "${lang}/"

        echo "${model_dir}"
    done

popd > /dev/null
