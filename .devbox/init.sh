#!/usr/bin/env bash

set -u

DEVBOX_DIR="${PWD}/.devbox"
LOCAL_ENV="${DEVBOX_DIR}/local.env"
BIN_DIR="${DEVBOX_DIR}/bin"
LINK_PATH_INOTIFYCOPY="${BIN_DIR}/inotifycopy"

init_paths() {
	mkdir -p "$DEVBOX_DIR" "$BIN_DIR"
	touch "$LOCAL_ENV"
}

load_local_env() {
	# shellcheck disable=SC1090
	. "$LOCAL_ENV"
}

append_local_env_var() {
	local key="$1"
	local value="$2"
	local escaped
	escaped=$(printf '%q' "$value")

	printf '\n%s=%s\n' "$key" "$escaped" >>"$LOCAL_ENV"
}

prompt_for_inotifycopy_source() {
	local input

	if [ -n "${INOTIFYCOPY_SOURCE:-}" ]; then
		return 0
	fi

	if [ ! -t 0 ]; then
		return 0
	fi

	printf 'Path to local inotifycopy file: '
	read -r input

	if [ -n "${input:-}" ]; then
		append_local_env_var "INOTIFYCOPY_SOURCE" "$input"
		INOTIFYCOPY_SOURCE="$input"
	else
		echo "No inotifycopy path configured."
	fi
}

link_inotifycopy() {
	if [ -z "${INOTIFYCOPY_SOURCE:-}" ]; then
		return 0
	fi

	if [ -f "$INOTIFYCOPY_SOURCE" ]; then
		ln -snf "$INOTIFYCOPY_SOURCE" "$LINK_PATH_INOTIFYCOPY"
		chmod +x "$LINK_PATH_INOTIFYCOPY" 2>/dev/null || true
	else
		echo "Warning: INOTIFYCOPY_SOURCE does not exist: $INOTIFYCOPY_SOURCE" >&2
	fi
}

ensure_bin_dir_on_path() {
	case ":$PATH:" in
		*":$BIN_DIR:"*) ;;
		*) export PATH="$BIN_DIR:$PATH" ;;
	esac
}

main() {
	init_paths
	load_local_env
	prompt_for_inotifycopy_source
	link_inotifycopy
	ensure_bin_dir_on_path
}

main "$@"