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

# `uv sync` below fetches internal dependencies (e.g.
# univention-configuration-registry) from git.knut.univention.de, which is only
# resolvable inside Univention's network and not published in public DNS.
# Containers on Docker's default bridge network cannot resolve it, so the sync
# fails with a DNS error. The host can resolve it (via internal DNS / VPN), so
# resolve it here and inject a static hosts entry into the container; TLS still
# uses the real hostname (SNI/Host header), so the certificate stays valid.
# Override with GIT_KNUT_IP if host resolution is unavailable.
git_knut_host="git.knut.univention.de"
git_knut_ip="${GIT_KNUT_IP:-$(getent hosts "$git_knut_host" | awk '{ print $1; exit }')}"

add_host_args=()
if [[ -n "$git_knut_ip" ]]; then
    add_host_args=(--add-host "${git_knut_host}:${git_knut_ip}")
else
    echo "WARNING: could not resolve ${git_knut_host}; the container may fail to fetch internal dependencies." >&2
fi

docker run --rm \
    "${add_host_args[@]}" \
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
