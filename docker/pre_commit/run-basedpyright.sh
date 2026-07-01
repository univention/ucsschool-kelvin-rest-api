#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <baseline|no-baseline|write-baseline> [basedpyright file args...]" >&2
    exit 2
fi

mode="$1"
shift

image="ucsschool-kelvin-precommit-basedpyright:latest"

docker build -f docker/pre_commit/Dockerfile -t "$image" \
    --build-arg UID="$(id -u)" \
    --build-arg GID="$(id -g)" \
    .

case "$mode" in
    baseline)
        baseline_arg="--baselinefile basedpyright-baseline.json --baselinemode=auto"
        ;;
    no-baseline)
        baseline_arg="--baselinefile /tmp/nonexistent-basedpyright-baseline.json"
        ;;
    write-baseline)
        baseline_arg="--baselinefile basedpyright-baseline.json --writebaseline ."
        ;;
    *)
        echo "Unknown mode: $mode" >&2
        exit 2
        ;;
esac

args=""
for arg in "$@"; do
    args+=" $(printf '%q' "$arg")"
done

docker run --rm \
    -v "$PWD:/src" \
    -w /src \
    "$image" \
    bash -lc "
      export UV_CACHE_DIR=/src/.cache/uv/cache
      export HOME=/src/.cache/uv/home
      export XDG_CACHE_HOME=/src/.cache/uv/xdg-cache
      export XDG_DATA_HOME=/src/.cache/uv/xdg-data
      export UV_PROJECT_ENVIRONMENT=/src/.container_venv

      mkdir -p \"\$UV_CACHE_DIR\" \"\$HOME\" \"\$XDG_CACHE_HOME\" \"\$XDG_DATA_HOME\"
      uv sync --dev
      uv pip install --python \$UV_PROJECT_ENVIRONMENT basedpyright==1.39.8
      uv run --python 3.11 basedpyright --project pyrightconfig.json --pythonpath \$UV_PROJECT_ENVIRONMENT/bin/python $baseline_arg$args
    "
