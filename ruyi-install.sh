#!/bin/sh

set -u

PRIMARY_RELEASES_URL="https://api.ruyisdk.cn/releases/latest-pm"
FALLBACK_RELEASES_URL="https://ruyisdk.org/data/api/api_ruyisdk_cn/releases_latest_pm.json"
DEFAULT_CHANNEL="stable"

CHANNEL=${RUYI_CHANNEL:-$DEFAULT_CHANNEL}
INSTALL_DIR=${RUYI_INSTALL_DIR:-/usr/local/bin}
DRY_RUN=0
TMP_ROOT=
STAGED_FILE=
USE_SUDO=0

log() {
  printf '%s\n' "$*"
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
RuyiSDK installer

Usage:
  sh install.sh [OPTIONS]
  curl --proto '=https' --tlsv1.2 -fL https://ruyisdk.org/install.sh | sh

Options:
  --channel CHANNEL      Install from stable or testing. Default: stable
  --install-dir DIR      Install ruyi into DIR. Default: /usr/local/bin
  --dry-run              Print the selected download URLs without installing
  -h, --help             Show this help message

Environment:
  RUYI_CHANNEL           Default channel when --channel is not provided
  RUYI_INSTALL_DIR       Default install directory when --install-dir is not provided
EOF
}

cleanup() {
  if [ -n "${STAGED_FILE:-}" ] && [ -e "$STAGED_FILE" ]; then
    run_privileged rm -f "$STAGED_FILE" >/dev/null 2>&1 || :
  fi
  if [ -n "${TMP_ROOT:-}" ] && [ -d "$TMP_ROOT" ]; then
    rm -rf "$TMP_ROOT"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --channel)
      [ "$#" -ge 2 ] || die "--channel requires a value"
      CHANNEL=$2
      shift 2
      ;;
    --channel=*)
      CHANNEL=${1#*=}
      shift
      ;;
    --install-dir)
      [ "$#" -ge 2 ] || die "--install-dir requires a value"
      INSTALL_DIR=$2
      shift 2
      ;;
    --install-dir=*)
      INSTALL_DIR=${1#*=}
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$CHANNEL" in
  stable|testing) ;;
  *) die "unsupported channel: $CHANNEL" ;;
esac

case "$INSTALL_DIR" in
  /*) ;;
  *) die "install directory must be an absolute path: $INSTALL_DIR" ;;
esac

if [ "$INSTALL_DIR" != / ]; then
  INSTALL_DIR=${INSTALL_DIR%/}
fi

RAW_SYSTEM=$(uname -s 2>/dev/null || printf unknown)
RAW_ARCH=$(uname -m 2>/dev/null || printf unknown)
LEGACY_PLATFORM_KEY=
TARGET_NAME=ruyi

case "$RAW_SYSTEM" in
  Linux)
    case "$RAW_ARCH" in
      x86_64|amd64) PLATFORM_KEY=linux/x86_64 ;;
      aarch64|arm64) PLATFORM_KEY=linux/aarch64 ;;
      riscv64) PLATFORM_KEY=linux/riscv64 ;;
      *) die "no official Linux ruyi binary is published for architecture $RAW_ARCH" ;;
    esac
    ;;
  Darwin)
    case "$RAW_ARCH" in
      arm64|aarch64)
        PLATFORM_KEY=darwin/aarch64
        LEGACY_PLATFORM_KEY=linux/macos-arm64
        ;;
      *) die "no official macOS ruyi binary is published for architecture $RAW_ARCH" ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*)
    case "$RAW_ARCH" in
      x86_64|amd64)
        PLATFORM_KEY=windows/x86_64
        TARGET_NAME=ruyi.exe
        ;;
      *) die "no official Windows ruyi binary is published for architecture $RAW_ARCH" ;;
    esac
    ;;
  *) die "unsupported operating system: $RAW_SYSTEM" ;;
esac

TARGET_FILE=$INSTALL_DIR/$TARGET_NAME
if [ "$DRY_RUN" -eq 0 ] && { [ -e "$TARGET_FILE" ] || [ -L "$TARGET_FILE" ]; }; then
  die "$TARGET_FILE already exists; this installer does not perform upgrades"
fi

if command -v mktemp >/dev/null 2>&1; then
  TMP_PARENT=${TMPDIR:-/tmp}
  TMP_ROOT=$(mktemp -d "${TMP_PARENT%/}/ruyi-install.XXXXXX") || die "failed to create temporary directory"
else
  die "mktemp is required"
fi

trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if command -v curl >/dev/null 2>&1; then
  FETCH_TOOL=curl
elif command -v wget >/dev/null 2>&1; then
  FETCH_TOOL=wget
else
  die "curl or wget is required"
fi

fetch_to_stdout() {
  url=$1
  case "$FETCH_TOOL" in
    curl)
      curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fL "$url"
      ;;
    wget)
      wget -O - "$url"
      ;;
    *)
      die "unsupported download tool: $FETCH_TOOL"
      ;;
  esac
}

download_to_file() {
  url=$1
  output=$2
  case "$FETCH_TOOL" in
    curl)
      curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fL "$url" -o "$output"
      ;;
    wget)
      wget -O "$output" "$url"
      ;;
    *)
      die "unsupported download tool: $FETCH_TOOL"
      ;;
  esac
}

is_allowed_download_url() {
  case "$1" in
    https://mirror.iscas.ac.cn/ruyisdk/ruyi/*) return 0 ;;
    https://github.com/ruyisdk/ruyi/releases/download/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_install_dir_on_path() {
  case ":${PATH:-}:" in
    *":$INSTALL_DIR:"*) return 0 ;;
    *) return 1 ;;
  esac
}

show_path_guidance() {
  {
    printf 'warning: install directory is not in PATH: %s\n' "$INSTALL_DIR"
    printf 'After installation, your shell may not find the ruyi command automatically.\n'
    printf 'Add the install directory to PATH, for example:\n'
    printf '\n'
    printf '  export PATH="%s:$PATH"\n' "$INSTALL_DIR"
    printf '\n'
    printf 'Then restart your shell, or reload the profile file where you added it.\n'
  } >&2
}

confirm_path_guidance() {
  if is_install_dir_on_path; then
    return 0
  fi

  show_path_guidance

  if [ "$DRY_RUN" -eq 1 ]; then
    warn "dry run requested; skipping interactive PATH confirmation"
    return 0
  fi

  if printf 'Continue installing to %s anyway? [Y/n] ' "$INSTALL_DIR" 2>/dev/null > /dev/tty; then
    if IFS= read -r answer 2>/dev/null < /dev/tty; then
      case "$answer" in
        ""|y|Y|yes|YES|Yes) return 0 ;;
        *) die "installation cancelled" ;;
      esac
    fi
  fi

  warn "no interactive terminal detected; continuing without confirmation"
}

extract_urls() {
  awk -v channel="$CHANNEL" -v platform="$PLATFORM_KEY" \
    -v legacy="$LEGACY_PLATFORM_KEY" -v error_file="$PARSE_ERROR" '
    function fail(message) {
      print message > error_file
      exit 1
    }
    {
      gsub(/[[:space:]]/, "", $0)
      json = json $0
    }
    END {
      channel_key = "\"" channel "\":{"
      channel_start = index(json, channel_key)
      if (channel_start == 0) fail("channel " channel " is missing")

      object_start = channel_start + length("\"" channel "\":")
      depth = 0
      channel_object = ""
      for (i = object_start; i <= length(json); i++) {
        ch = substr(json, i, 1)
        if (ch == "{") depth++
        if (ch == "}") depth--
        if (depth == 0) {
          channel_object = substr(json, object_start, i - object_start + 1)
          break
        }
      }
      if (channel_object == "") fail("channel " channel " is malformed")

      version_key = "\"version\":\""
      version_start = index(channel_object, version_key)
      if (version_start == 0) fail("version is missing from channel " channel)
      version_tail = substr(channel_object, version_start + length(version_key))
      version_end = index(version_tail, "\"")
      if (version_end <= 1) fail("version is empty or malformed")
      version = substr(version_tail, 1, version_end - 1)
      semver = "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)"
      prerelease = "(-[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?"
      build = "(\\+[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$"
      if (version !~ semver prerelease build) fail("invalid semantic version: " version)

      platform_key = "\"" platform "\":["
      platform_start = index(channel_object, platform_key)
      selected_platform = platform
      if (platform_start == 0 && legacy != "") {
        platform_key = "\"" legacy "\":["
        platform_start = index(channel_object, platform_key)
        selected_platform = legacy
      }
      if (platform_start == 0) fail("platform " platform " is missing")

      array_start = platform_start + length("\"" selected_platform "\":")
      depth = 0
      array_body = ""
      for (i = array_start; i <= length(channel_object); i++) {
        ch = substr(channel_object, i, 1)
        if (ch == "[") depth++
        if (ch == "]") depth--
        if (depth == 0) {
          array_body = substr(channel_object, array_start + 1, i - array_start - 1)
          break
        }
      }
      if (array_body == "") fail("download URL list for " platform " is empty or malformed")

      print version
      count = split(array_body, urls, ",")
      for (i = 1; i <= count; i++) {
        url = urls[i]
        gsub(/^"/, "", url)
        gsub(/"$/, "", url)
        if (url != "") print url
      }
    }
  ' "$1"
}

install_binary() {
  source_file=$1
  target_file=$INSTALL_DIR/$TARGET_NAME

  if ! mkdir -p "$INSTALL_DIR" 2>/dev/null || [ ! -w "$INSTALL_DIR" ]; then
    request_sudo
    run_privileged mkdir -p "$INSTALL_DIR" || die "failed to create install directory: $INSTALL_DIR"
  fi
  [ -d "$INSTALL_DIR" ] || die "install path is not a directory: $INSTALL_DIR"
  if [ -e "$target_file" ] || [ -L "$target_file" ]; then
    die "$target_file appeared during installation; refusing to replace it"
  fi

  if [ "$USE_SUDO" -eq 1 ]; then
    STAGED_FILE=$(run_privileged mktemp "$INSTALL_DIR/.ruyi.install.XXXXXX") \
      || die "failed to create a staging file in $INSTALL_DIR"
  else
    STAGED_FILE=$(mktemp "$INSTALL_DIR/.ruyi.install.XXXXXX" 2>/dev/null) || {
      request_sudo
      STAGED_FILE=$(run_privileged mktemp "$INSTALL_DIR/.ruyi.install.XXXXXX") \
        || die "failed to create a staging file in $INSTALL_DIR"
    }
  fi
  run_privileged cp "$source_file" "$STAGED_FILE" || die "failed to stage the ruyi binary"
  run_privileged chmod 0755 "$STAGED_FILE" || die "failed to set installed permissions"
  if ! run_privileged ln "$STAGED_FILE" "$target_file" 2>/dev/null; then
    die "failed to install $target_file without replacing an existing path"
  fi
  run_privileged rm -f "$STAGED_FILE" || die "failed to remove the staging file"
  STAGED_FILE=
}

fetch_release_data() {
  for release_url in "$PRIMARY_RELEASES_URL" "$FALLBACK_RELEASES_URL"; do
    log "Fetching release metadata from $release_url"
    rm -f "$API_JSON" "$RELEASE_DATA" "$PARSE_ERROR"
    if fetch_to_stdout "$release_url" > "$API_JSON"; then
      : > "$PARSE_ERROR"
      if extract_urls "$API_JSON" > "$RELEASE_DATA" && [ -s "$RELEASE_DATA" ]; then
        VERSION=$(sed -n '1p' "$RELEASE_DATA")
        return 0
      fi
      parse_error=$(sed -n '1p' "$PARSE_ERROR")
      [ -n "$parse_error" ] || parse_error="response contains no release data"
      warn "release metadata from $release_url is unavailable or invalid: $parse_error"
    else
      warn "release metadata from $release_url is unavailable or invalid: download failed"
    fi
  done
  return 1
}

sort_download_urls() {
  urls_file=$1
  if ! command -v ping >/dev/null 2>&1; then
    warn "ping is unavailable; keeping the fallback download order"
    return 0
  fi
  if ! command -v sort >/dev/null 2>&1; then
    warn "sort is unavailable; keeping the fallback download order"
    return 0
  fi

  ping_data=$TMP_ROOT/urls.ping
  sorted_data=$TMP_ROOT/urls.sorted
  sorted_urls=$TMP_ROOT/urls.sorted-only
  : > "$ping_data"
  url_order=0
  while IFS= read -r url; do
    [ -n "$url" ] || continue
    url_order=$((url_order + 1))
    host=${url#https://}
    host=${host%%/*}
    case "$RAW_SYSTEM" in
      Darwin) ping_output=$(LC_ALL=C ping -c 1 -W 1000 "$host" 2>/dev/null) || ping_output= ;;
      MINGW*|MSYS*|CYGWIN*) ping_output=$(LC_ALL=C ping -n 1 -w 1000 "$host" 2>/dev/null) || ping_output= ;;
      *) ping_output=$(LC_ALL=C ping -c 1 -W 1 "$host" 2>/dev/null) || ping_output= ;;
    esac
    latency=$(printf '%s\n' "$ping_output" | awk '
      !found && match($0, /time[=<][0-9]+([.][0-9]+)?/) {
        value = substr($0, RSTART, RLENGTH)
        sub(/^time[=<]/, "", value)
        print value
        found = 1
      }
    ')
    case "$latency" in
      ""|*[!0-9.]*|.*|*.)
        warn "could not measure latency for $host; trying it after responsive URLs"
        printf '1\t0\t%s\t%s\n' "$url_order" "$url" >> "$ping_data"
        ;;
      *)
        log "Ping $host: $latency ms"
        printf '0\t%s\t%s\t%s\n' "$latency" "$url_order" "$url" >> "$ping_data"
        ;;
    esac
  done < "$urls_file"

  tab=$(printf '\t')
  if ! LC_ALL=C sort -t "$tab" -k1,1n -k2,2n -k3,3n "$ping_data" > "$sorted_data"; then
    warn "failed to order download URLs by latency"
    return 1
  fi
  if ! awk -F '\t' '{ print $4 }' "$sorted_data" > "$sorted_urls"; then
    warn "failed to read latency-sorted download URLs"
    return 1
  fi
  cat "$sorted_urls" > "$urls_file"
}

verify_binary() {
  binary_file=$1
  download_url=$2
  if ! chmod 0755 "$binary_file"; then
    warn "failed to mark downloaded binary executable: $download_url"
    return 1
  fi
  rm -f "$VERSION_OUTPUT"
  if ! RUYI_TELEMETRY_OPTOUT=1 "$binary_file" version > "$VERSION_OUTPUT" 2>&1; then
    warn "downloaded binary failed its version check: $download_url"
    return 1
  fi
  reported_version=$(sed -n '1p' "$VERSION_OUTPUT")
  if [ "$reported_version" != "Ruyi $VERSION" ]; then
    warn "downloaded binary reports '$reported_version', expected 'Ruyi $VERSION'"
    return 1
  fi
  return 0
}

run_privileged() {
  if [ "$USE_SUDO" -eq 1 ]; then
    sudo "$@"
  else
    "$@"
  fi
}

request_sudo() {
  [ "$USE_SUDO" -eq 1 ] && return 0
  if [ "$(id -u 2>/dev/null)" = 0 ]; then
    return 0
  fi
  command -v sudo >/dev/null 2>&1 || die "sudo is required to install into $INSTALL_DIR"

  if ! printf 'Install Ruyi into %s with sudo? [y/N] ' "$INSTALL_DIR" > /dev/tty 2>/dev/null; then
    die "installation into $INSTALL_DIR requires interactive sudo consent"
  fi
  if ! IFS= read -r answer < /dev/tty; then
    die "installation cancelled"
  fi
  case "$answer" in
    y|Y|yes|YES|Yes) ;;
    *) die "installation cancelled" ;;
  esac

  sudo -v || die "sudo authorization failed"
  USE_SUDO=1
}

confirm_path_guidance

API_JSON=$TMP_ROOT/latest-pm.json
RELEASE_DATA=$TMP_ROOT/release.data
PARSE_ERROR=$TMP_ROOT/release.error
RAW_URLS=$TMP_ROOT/urls.raw
VALID_URLS=$TMP_ROOT/urls.valid
CANDIDATE_URLS=$TMP_ROOT/urls.candidates
VERSION_OUTPUT=$TMP_ROOT/version.out

fetch_release_data || die "failed to fetch valid release metadata from the official endpoints"
sed -n '2,$p' "$RELEASE_DATA" > "$RAW_URLS"

: > "$VALID_URLS"
while IFS= read -r url; do
  [ -n "$url" ] || continue
  if is_allowed_download_url "$url"; then
    printf '%s\n' "$url" >> "$VALID_URLS"
  else
    warn "ignored unexpected download URL: $url"
  fi
done < "$RAW_URLS"

if [ ! -s "$VALID_URLS" ]; then
  die "no trusted download URLs found for channel $CHANNEL and $PLATFORM_KEY"
fi

: > "$CANDIDATE_URLS"
while IFS= read -r url; do
  case "$url" in
    https://mirror.iscas.ac.cn/*) printf '%s\n' "$url" >> "$CANDIDATE_URLS" ;;
  esac
done < "$VALID_URLS"
while IFS= read -r url; do
  case "$url" in
    https://github.com/*) printf '%s\n' "$url" >> "$CANDIDATE_URLS" ;;
  esac
done < "$VALID_URLS"

if [ "$DRY_RUN" -eq 1 ]; then
  log "Selected platform: $PLATFORM_KEY"
  log "Selected channel: $CHANNEL"
  log "Selected version: $VERSION"
  log "Install path: $TARGET_FILE"
  log "Download candidates:"
  sed 's/^/  /' "$CANDIDATE_URLS"
  log "Dry run requested; no files were downloaded or installed."
  exit 0
fi

sort_download_urls "$CANDIDATE_URLS" || die "failed to sort download URLs by latency"
log "Selected platform: $PLATFORM_KEY"
log "Selected channel: $CHANNEL"
log "Selected version: $VERSION"
log "Install path: $TARGET_FILE"
log "Download candidates (lowest latency first):"
sed 's/^/  /' "$CANDIDATE_URLS"

BINARY_FILE=$TMP_ROOT/$TARGET_NAME
SELECTED_URL=

while IFS= read -r url; do
  [ -n "$url" ] || continue
  log "Downloading $url"
  rm -f "$BINARY_FILE"
  if download_to_file "$url" "$BINARY_FILE" && verify_binary "$BINARY_FILE" "$url"; then
    SELECTED_URL=$url
    break
  fi
  warn "ignoring unusable download: $url"
done < "$CANDIDATE_URLS"

if [ -z "$SELECTED_URL" ]; then
  die "all API-provided downloads failed validation"
fi

install_binary "$BINARY_FILE"

log "Ruyi $VERSION was installed successfully: $TARGET_FILE"
sed -n '1,5p' "$VERSION_OUTPUT"

case ":${PATH:-}:" in
  *":$INSTALL_DIR:"*) ;;
  *) warn "install directory is not in PATH: $INSTALL_DIR" ;;
esac
