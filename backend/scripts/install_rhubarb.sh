#!/usr/bin/env bash
# Install the pinned Rhubarb release and its recognizer resources after checksum verification.
set -euo pipefail

RHUBARB_VERSION="1.14.0"
RELEASE_BASE_URL="https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v${RHUBARB_VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${RHUBARB_INSTALL_DIR:-${BACKEND_DIR}/.tools/rhubarb}"
PLATFORM=""
EXPECTED_SHA256=""

case "$(uname -s)" in
  Darwin)
    PLATFORM="macOS"
    EXPECTED_SHA256="f991deacac6c973a14a4431a16a58b842f436531e120cfaea142c87c0d3ab4c5"
    if [[ "$(uname -m)" == "arm64" ]] && ! /usr/bin/arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
      echo "Rhubarb v${RHUBARB_VERSION} is x86_64-only on macOS. Install Rosetta first:" >&2
      echo "  softwareupdate --install-rosetta --agree-to-license" >&2
      exit 2
    fi
    ;;
  Linux)
    PLATFORM="Linux"
    EXPECTED_SHA256="a9a9074862cff47b2d59b8bf399a678a3b0b74f9452ad6ad94cb292913dd8667"
    case "$(uname -m)" in
      x86_64|amd64) ;;
      *)
        echo "Official Rhubarb Linux builds require x86_64; found $(uname -m)." >&2
        exit 2
        ;;
    esac
    ;;
  *)
    echo "Unsupported platform: $(uname -s)" >&2
    exit 2
    ;;
esac

for command_name in curl unzip awk; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is missing: ${command_name}" >&2
    exit 2
  fi
done

if command -v shasum >/dev/null 2>&1; then
  HASH_COMMAND=(shasum -a 256)
elif command -v sha256sum >/dev/null 2>&1; then
  HASH_COMMAND=(sha256sum)
else
  echo "Required SHA-256 tool is missing: shasum or sha256sum" >&2
  exit 2
fi

ARCHIVE_NAME="Rhubarb-Lip-Sync-${RHUBARB_VERSION}-${PLATFORM}.zip"
DOWNLOAD_URL="${RELEASE_BASE_URL}/${ARCHIVE_NAME}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lianleme-rhubarb.XXXXXX")"
trap 'rm -rf "${TEMP_DIR}"' EXIT

curl --fail --location --retry 2 --output "${TEMP_DIR}/${ARCHIVE_NAME}" "${DOWNLOAD_URL}"
ACTUAL_SHA256="$("${HASH_COMMAND[@]}" "${TEMP_DIR}/${ARCHIVE_NAME}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  echo "Rhubarb checksum mismatch: expected ${EXPECTED_SHA256}, got ${ACTUAL_SHA256}" >&2
  exit 1
fi

unzip -q "${TEMP_DIR}/${ARCHIVE_NAME}" -d "${TEMP_DIR}/extracted"
SOURCE_DIR="${TEMP_DIR}/extracted/${ARCHIVE_NAME%.zip}"
mkdir -p "${INSTALL_DIR}"
install -m 0755 "${SOURCE_DIR}/rhubarb" "${INSTALL_DIR}/rhubarb"
mkdir -p "${INSTALL_DIR}/res"
cp -R "${SOURCE_DIR}/res/." "${INSTALL_DIR}/res/"

"${INSTALL_DIR}/rhubarb" --version >/dev/null
echo "Installed Rhubarb v${RHUBARB_VERSION}: ${INSTALL_DIR}/rhubarb"
echo "Set RHUBARB_BIN=${INSTALL_DIR}/rhubarb"
