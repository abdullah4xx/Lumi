#!/usr/bin/env bash
# Lumi - build the .deb and (optionally) publish the project to GitHub.
#
#   ./deploy_and_build.sh                                   # tests + build dist/lumi_<ver>_amd64.deb
#   ./deploy_and_build.sh --repo-url git@github.com:abdullah4xx/Lumi.git
#   ./deploy_and_build.sh --repo-url https://github.com/abdullah4xx/Lumi.git --release
#
# Options (or env vars):
#   --repo-url URL   GitHub remote to push to        (GITHUB_REPO_URL)
#   --branch NAME    branch to push, default main    (GIT_BRANCH)
#   --skip-git       only build the package
#   --no-tests       skip the test-suite before building
#   --release        also create a GitHub release with the .deb (needs the `gh` CLI, logged in)
#   ARCH=amd64       package architecture, default all (the app is pure Python)
#   VERSION=1.1.0+build7   override the package version (the GitHub workflow uses this)
#   REPO_SLUG=owner/name   GitHub repo the in-app update check looks at (derived from --repo-url if omitted)
#   MAINTAINER="Name <mail>"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

REPO_URL="${GITHUB_REPO_URL:-}"; BRANCH="${GIT_BRANCH:-main}"
SKIP_GIT=0; RUN_TESTS=1; RELEASE=0
ARCH="${ARCH:-all}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)  REPO_URL="${2:?--repo-url needs a value}"; shift 2 ;;
    --branch)    BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    --skip-git)  SKIP_GIT=1; shift ;;
    --no-tests)  RUN_TESTS=0; shift ;;
    --release)   RELEASE=1; shift ;;
    -h|--help)   sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required ($2)"; }

VERSION="${VERSION:-$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/lumi/__init__.py)}"
REPO_SLUG="${REPO_SLUG:-}"
if [[ -z "$REPO_SLUG" && -n "$REPO_URL" ]]; then
  REPO_SLUG="$(printf '%s' "$REPO_URL" | sed -E 's#^(git@github.com:|https?://github.com/)##; s#\.git$##')"
fi
[[ -n "$VERSION" ]] || die "could not read __version__ from src/lumi/__init__.py"
PKG=lumi
DEB="dist/${PKG}_${VERSION}_${ARCH}.deb"
MAINTAINER="${MAINTAINER:-Lumi Maintainers <noreply@users.noreply.github.com>}"

# ------------------------------------------------------------------ 1. tests
if [[ $RUN_TESTS -eq 1 && -d tests ]]; then
  log "Running tests"
  if ! python3 -m unittest discover -s tests > /tmp/lumi-tests.log 2>&1; then
    cat /tmp/lumi-tests.log >&2
    die "tests failed - not building (use --no-tests to skip)"
  fi
  tail -n 3 /tmp/lumi-tests.log
fi

# ------------------------------------------------------------------ 2. Debian tree
need dpkg-deb "install the dpkg package"
log "Building Debian tree for ${PKG} ${VERSION} (${ARCH})"
STAGE="build/${PKG}_${VERSION}_${ARCH}"
rm -rf "$STAGE"
install -d "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/$PKG" \
           "$STAGE/usr/share/doc/$PKG"

# application code (no caches)
cp -a src/lumi "$STAGE/usr/share/$PKG/"
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +

# stamp the installed copy with the real package version (and repo) so the in-app update check compares correctly
INIT="$STAGE/usr/share/$PKG/lumi/__init__.py"
sed -i "s|^__version__ = .*|__version__ = \"${VERSION}\"|" "$INIT"
if [[ -n "$REPO_SLUG" ]]; then sed -i "s|^REPO = \"[^\"]*\"|REPO = \"${REPO_SLUG}\"|" "$INIT"; fi
find "$STAGE/usr/share/$PKG" -type d -exec chmod 755 {} +
find "$STAGE/usr/share/$PKG" -type f -exec chmod 644 {} +

# /usr/bin/lumi: uses the optional AI venv (torch/transformers) when it exists
cat > "$STAGE/usr/bin/lumi" <<'LAUNCH'
#!/bin/sh
# Lumi launcher. If ~/.local/share/lumi/venv exists (created with
# --system-site-packages, see the README "AI" section) it is used, so CLIP can
# load torch/transformers; otherwise the system python3 is used.
VENV_PY="${XDG_DATA_HOME:-$HOME/.local/share}/lumi/venv/bin/python3"
PY=python3
[ -x "$VENV_PY" ] && PY="$VENV_PY"
PYTHONPATH="/usr/share/lumi${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m lumi "$@"
LAUNCH
chmod 755 "$STAGE/usr/bin/lumi"

[[ -f README.md ]] && install -m 644 README.md "$STAGE/usr/share/doc/$PKG/README.md"

INSTALLED_KB="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: ${PKG}
Version: ${VERSION}
Section: graphics
Priority: optional
Architecture: ${ARCH}
Maintainer: ${MAINTAINER}
Installed-Size: ${INSTALLED_KB}
Depends: python3 (>= 3.10), python3-aiohttp, python3-pil
Recommends: webp-pixbuf-loader
Suggests: python3-venv
Homepage: ${REPO_URL:-https://github.com/abdullah4xx/Lumi}
Description: command-line tools for Lumi
 Lumi provides command-line source checks and an optional local web
 companion for wallpaper discovery.
CONTROL
chmod 755 "$STAGE/DEBIAN"

# ------------------------------------------------------------------ 3. dpkg-deb
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB" >/dev/null
log "Built $DEB ($(du -h "$DEB" | cut -f1))"
dpkg-deb -I "$DEB" | sed -n '1,12p'

# ------------------------------------------------------------------ 4. git / GitHub
if [[ $SKIP_GIT -eq 1 ]]; then
  log "Skipping Git (--skip-git)"
  echo "Install with:  sudo apt install ./$DEB"
  exit 0
fi
need git "install git"
[[ -n "$REPO_URL" ]] || die "no GitHub repository given: use --repo-url <url> (or GITHUB_REPO_URL), or --skip-git"

if [[ ! -d .git ]]; then
  log "git init"
  git init -q -b "$BRANCH"
fi
if ! git rev-parse --verify -q "$BRANCH" >/dev/null; then
  git checkout -q -b "$BRANCH"               # new branch from where we are
elif [[ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]]; then
  git checkout -q "$BRANCH"                  # switch only; never reset an existing branch
fi

write_if_missing() { [[ -e "$1" ]] && { log "$1 exists - keeping it"; return 1; } || return 0; }

if write_if_missing .gitignore; then
  log "Writing .gitignore"
  cat > .gitignore <<'IGNORE'
__pycache__/
*.py[cod]
build/
dist/
*.deb
.venv/
venv/
.idea/
.vscode/
*.egg-info/
.env
config.json
IGNORE
fi

if write_if_missing README.md; then
  log "Writing README.md"
  cat > README.md <<'README'
# Lumi

Lumi is a Python command-line toolkit for checking wallpaper sources and
running an optional local web companion. The GTK/libadwaita desktop interface
has been removed.

```bash
PYTHONPATH=src python3 -m lumi --help
PYTHONPATH=src python3 -m lumi --version
PYTHONPATH=src python3 -m lumi --check-sources
PYTHONPATH=src python3 -m lumi --web-server --port 5910
```

Run tests with `python3 -m unittest discover -s tests -v`.
README
fi

if [[ -n "$REPO_SLUG" ]]; then
  sed -i "s|^REPO = \"[^\"]*\"|REPO = \"${REPO_SLUG}\"|" src/lumi/__init__.py
fi
git add -A
if git diff --cached --quiet; then
  log "Nothing new to commit"
else
  git config user.name >/dev/null 2>&1 || git config user.name "Lumi Builder"
  git config user.email >/dev/null 2>&1 || git config user.email "noreply@users.noreply.github.com"
  git commit -q -m "Lumi ${VERSION}"
  log "Committed Lumi ${VERSION}"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi
log "Pushing to $REPO_URL ($BRANCH)"
git push -u origin "$BRANCH" || die "push failed. If the remote already has commits, run: git pull --rebase origin $BRANCH  and try again (this script never force-pushes)."

if [[ $RELEASE -eq 1 ]]; then
  need gh "https://cli.github.com and 'gh auth login'"
  gh release create "v${VERSION}" "$DEB" --title "Lumi ${VERSION}" --notes "Lumi ${VERSION}. Install: sudo apt install ./$(basename "$DEB")" \
    || die "could not create the release (does v${VERSION} already exist?)"
  log "Release v${VERSION} published"
fi
log "Done."
