#!/usr/bin/env bash
# Install the system packages this kit needs and that require administrator rights, plus uv.
# Run it in your own terminal, outside Claude Code: it asks for your password through sudo (or
# through Homebrew's installer). ./setup.sh needs no administrator rights and never calls sudo.
#   ./system-deps.sh [--yes] [--dry-run]
# macOS: Homebrew (installed if missing). Linux: apt-get (Debian, Ubuntu) or dnf (Fedora).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./system-deps.sh [--yes] [--dry-run]

Installs what is missing of: ffmpeg, ripgrep, tmux and the basic tools (curl, tar, unzip, xz);
Mesa's EGL and DRI drivers for rendering without a GPU driver (Linux); the DejaVu and Noto
fonts the renderers fall back on (Linux); the OS libraries Chromium needs for web captures
(Debian and Ubuntu, through Playwright's install-deps); and uv, the Python tool the kit's
environments use. Homebrew is installed first on a Mac that lacks it.

  --yes       do not ask "Continue? [Y/n]"
  --dry-run   print what would be installed and change nothing

Run it in a terminal outside Claude Code. ./setup.sh then needs no administrator rights.
EOF
}

YES=0 DRY=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --yes|-y) YES=1 ;;
    --dry-run) DRY=1 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

die() { echo "system-deps.sh: $*" >&2; exit 1; }

# One line per need: command to look for | apt package | dnf package | brew formula.
# "-" means none for that manager; a line without a command is checked in the package database.
TABLE='ffmpeg|ffmpeg|ffmpeg|ffmpeg
curl|curl|curl|-
tar|tar|tar|-
xz|xz-utils|xz|-
unzip|unzip|unzip|-
rg|ripgrep|ripgrep|ripgrep
tmux|tmux|tmux|tmux
-|libegl1|mesa-libEGL|-
-|libegl-mesa0|-|-
-|libgl1-mesa-dri|mesa-dri-drivers|-
-|fonts-dejavu-core|dejavu-sans-fonts|-
-|-|dejavu-sans-mono-fonts|-
-|fonts-noto-core|-|-
-|fonts-noto-color-emoji|google-noto-color-emoji-fonts|-'

OS="$(uname -s)"
MGR=none
case "$OS" in
  Darwin) MGR=brew ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then MGR=apt
    elif command -v dnf >/dev/null 2>&1; then MGR=dnf; fi ;;
  *) die "$OS is not supported: the kit runs on Linux and macOS" ;;
esac

# pkg_installed MANAGER PACKAGE: is the package in the package database?
pkg_installed() {
  case "$1" in
    apt) dpkg -s "$2" >/dev/null 2>&1 ;;
    dnf) rpm -q "$2" >/dev/null 2>&1 ;;
    brew) command -v brew >/dev/null 2>&1 && brew list --formula "$2" >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}

# missing_packages: the package names of the table that this machine lacks, space separated
missing_packages() {
  local cmd apt dnf brew pkg out=""
  while IFS='|' read -r cmd apt dnf brew; do
    case "$MGR" in apt) pkg="$apt" ;; dnf) pkg="$dnf" ;; brew) pkg="$brew" ;; *) pkg="$apt" ;; esac
    [ "$pkg" != "-" ] || continue
    if [ "$cmd" != "-" ] && command -v "$cmd" >/dev/null 2>&1; then continue; fi
    if [ "$cmd" = "-" ] && pkg_installed "$MGR" "$pkg"; then continue; fi
    out="$out $pkg"
  done <<<"$TABLE"
  echo "${out# }"
}

# playwright_version: the version pinned in fixtures/web/uv.lock, empty if not found
playwright_version() {
  awk '/^name = "playwright"$/ { getline; gsub(/[^0-9.]/, "", $0); print; exit }' \
    "$ROOT/fixtures/web/uv.lock" 2>/dev/null || true
}

PKGS="$(missing_packages)"
NEED_BREW=0 NEED_FUSION=0 NEED_UV=0 NEED_DEPS=0
if [ "$MGR" = brew ] && ! command -v brew >/dev/null 2>&1; then NEED_BREW=1; fi
if ! command -v uv >/dev/null 2>&1; then NEED_UV=1; fi
if [ "$MGR" = apt ]; then NEED_DEPS=1; fi
if [ "$MGR" = dnf ]; then
  # Fedora's own ffmpeg lacks libx264; it comes from RPM Fusion
  case " $PKGS " in *" ffmpeg "*) NEED_FUSION=1; PKGS="$(sed 's/\(^\| \)ffmpeg\( \|$\)/ /; s/^ *//; s/ *$//' <<<"$PKGS")" ;; esac
fi

if [ "$MGR" = none ]; then
  echo "system-deps.sh: no supported package manager (apt-get or dnf) found." >&2
  echo "Ask an administrator to install the equivalents of these Debian packages:" >&2
  echo "  $(missing_packages)" >&2
  echo "  plus uv (https://docs.astral.sh/uv/) and the OS libraries Chromium needs." >&2
  exit 1
fi

if [ -z "$PKGS" ] && [ "$NEED_BREW$NEED_FUSION$NEED_UV$NEED_DEPS" = 0000 ]; then
  echo "Nothing to install: the system dependencies are in place."
  exit 0
fi

echo "System dependencies to install ($MGR):"
if [ "$NEED_BREW" = 1 ]; then echo "  Homebrew (its installer asks for your password)"; fi
if [ "$NEED_FUSION" = 1 ]; then echo "  RPM Fusion (free) repository, then ffmpeg with libx264"; fi
if [ -n "$PKGS" ]; then echo "  packages: $PKGS"; fi
if [ "$NEED_DEPS" = 1 ]; then echo "  Chromium's OS libraries (Playwright install-deps; skips what is installed)"; fi
if [ "$NEED_UV" = 1 ]; then echo "  uv (official installer, into ~/.local/bin, no administrator rights)"; fi
if [ "$DRY" = 1 ]; then echo "Dry run: nothing was changed."; exit 0; fi

if [ "$YES" = 0 ]; then
  [ -t 0 ] || die "no terminal to ask on; rerun with --yes"
  read -r -p "Continue? [Y/n] " ans
  case "$ans" in ""|y|Y|yes|YES) ;; *) die "cancelled" ;; esac
fi

SUDO=""
if [ "$(id -u)" != 0 ] && [ "$MGR" != brew ]; then
  command -v sudo >/dev/null 2>&1 || die "sudo not found: run this script as root, or ask an administrator"
  SUDO="sudo"
fi

install_brew() {
  command -v curl >/dev/null 2>&1 || die "curl is needed to install Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || die "the Homebrew installer failed"
  local b
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$b" ]; then eval "$("$b" shellenv)"; break; fi
  done
  command -v brew >/dev/null 2>&1 || die "Homebrew installed but brew is not on PATH: open a new terminal and rerun"
}

install_packages() {
  # PKGS is split on purpose: one argument per package
  # shellcheck disable=SC2086
  case "$MGR" in
    brew) brew install $PKGS ;;
    apt) $SUDO apt-get update && $SUDO apt-get install -y $PKGS ;;
    dnf) $SUDO dnf install -y $PKGS ;;
  esac
}

install_fusion() {
  local rel
  rel="$(rpm -E %fedora)"
  $SUDO dnf install -y "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$rel.noarch.rpm"
  $SUDO dnf install -y ffmpeg --allowerasing
}

install_uv() {
  command -v curl >/dev/null 2>&1 || die "curl is needed to install uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "the uv installer failed"
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv installed but not on PATH: open a new terminal and rerun"
}

# Playwright's install-deps runs apt-get through sudo itself
install_chromium_deps() {
  local v
  v="$(playwright_version)"
  uvx "playwright${v:+@$v}" install-deps chromium || die "playwright install-deps chromium failed"
}

if [ "$NEED_BREW" = 1 ]; then install_brew; fi
if [ -n "$PKGS" ]; then install_packages || die "installing $PKGS failed"; fi
if [ "$NEED_FUSION" = 1 ]; then install_fusion || die "installing ffmpeg from RPM Fusion failed"; fi
if [ "$NEED_UV" = 1 ]; then install_uv; fi
if [ "$NEED_DEPS" = 1 ]; then install_chromium_deps; fi

echo
echo "System dependencies installed. If uv is not found in an already open terminal, open a new one."
echo "Next: run claude in the project folder; it runs ./setup.sh, which needs no administrator rights."
