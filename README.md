# Lumi

Lumi is a Python wallpaper browser with a local web interface and command-line
tools. Its wallpaper gallery uses a WebGL carousel and serves previews through
the local Python service.

## Project layout

The project root is the canonical development tree. The active Python package
is `src/lumi/`, and the desktop application ID is
`io.github.abdullah4xx.Lumi`. The `ui/` folder contains the Lumi gallery
preview; `lumi-web/` contains the public landing page.

## Usage

Run from the source tree:

```bash
PYTHONPATH=src python3 -m lumi --help
PYTHONPATH=src python3 -m lumi --version
PYTHONPATH=src python3 -m lumi
PYTHONPATH=src python3 -m lumi --check-sources
PYTHONPATH=src python3 -m lumi --check-sources --query nature --only wallhaven reddit
PYTHONPATH=src python3 -m lumi --web-server --port 5910
```

Running without a command starts the local web interface at `127.0.0.1:5910`
and opens it in your default browser. `--web-server` is an explicit alias, and
`--port` changes the listening port. Open the Lumi server URL, not a static
file preview such as a `/preview/lumi/` route; static previews cannot serve
the `/api/*` endpoints used by the gallery. Provider API keys are read from
`~/.config/lumi/config.json`. On first launch, Lumi migrates existing
VapourWall configuration, cache, and downloaded data folders when possible.
Respect each provider's terms and rate limits.

The desktop gallery supports Arabic and the bundled Almotlaq font. The font
files were supplied from arfonts.net. The project maintainer confirms permission
to distribute them with Lumi; see `ui/fonts/README.txt` for the source.

## Sources

Public API sources include Wallhaven, Reddit, Wikimedia Commons, Bing Image of
the Day, NASA, The Met, Art Institute of Chicago, Openverse,
AniList, and Kitsu. Rijksmuseum, TMDB, and fanart.tv require API keys; fanart.tv
also requires a TMDB key; Openverse requires an OAuth client ID and secret.
Existing Unsplash, Pexels, Pixabay, Alpha Coders, and Flickr integrations
require their own keys. Experimental feeds can be enabled in Settings; they use
unofficial endpoints and may occasionally fail. Sources without a supported
public API are shown as website links instead of being scraped automatically.
Desktoppr's former public API is no longer available and is shown as a website link.
Check each provider's image license and attribution requirements.

### Custom Python scrapers

Open **Settings → Sources** to add or remove a scraper `.py` file. Lumi imports
it and enables it immediately. A scraper must define `SOURCE_NAME`,
`SOURCE_URL` (HTTPS), and `search(query, category, page)`, returning a list of
dictionaries with `title`, `thumb_url`, `full_url`, `width`, `height`, `source`,
`category`, and `page_url`. Image and page URLs must use HTTPS and a host
declared by `SOURCE_URL` or optional `SOURCE_HOSTS`. Lumi filters results below
1920×1080, caches search results for 30 minutes, and caches downloaded images by
their URL-derived identity. Anime scrapers must set `SOURCE_CATEGORY = "Anime"`
and `SAFE_RATING = True`; every result must then include `rating` set to
`safe`, `general`, or `s`.

Image classification can run locally with the heuristic or optional CLIP
engine, or use Gemini when selected in Smart Categories. Gemini sends the
selected wallpaper to Google's API and may use the configured API key's quota.

## Development

Run the application with `PYTHONPATH=src python3 -m lumi`. The source registry
is in `src/lumi/sources/`; `engine.py` coordinates search and downloads, while
`cli.py` provides command-line entry points.

## Electron desktop app

The Electron desktop app is named `lumi` and uses the `ui/` gallery with the existing Python
wallpaper service, settings, favourites, downloads, and on-device category
classifier. This release is version 1.14.5 and keeps Lumi's existing data and
configuration compatible. Increment the app version for each shipped update.
Gemini models are loaded from the configured API key, wallpaper sources have a
30-second response window, and the carousel rendering resolution can be set to
4, 8, or 12 million pixels (8 million by default).
The Linux Debian package keeps the `lumi-desktop` package identity, desktop
application ID, and icon name so 1.14.5 upgrades 1.14.4 and older releases in place.
Web wallpapers are shown by default; local images have a separate gallery
section.
Right-click a wallpaper to set it, save it, favourite it, or identify its
category. The maximized window can be hidden to the system tray, whose menu
includes opening Lumi, changing the wallpaper, opening settings, and exiting.

Install Node.js/npm plus the Python dependencies, then run:

```bash
npm install
npm start
```

Build Linux `.deb` and AppImage packages with `npm run dist`. The packaged app
uses the system Python 3, `aiohttp`, and Pillow; the Debian package declares
these dependencies. Set `LUMI_PYTHON` if Python is installed under another
executable name. Electron's renderer has Node integration disabled and uses a
small preload bridge only for native file dialogs and opening application
folders. The AppImage checks GitHub Releases for updates from the About panel
and can download and install them in place. Debian packages can be downloaded
from the same release and installed with the system package manager.

## Packaging

`npm run dist` builds the desktop Debian package and AppImage. Pushing a `v*`
version tag runs the release workflow and publishes both packages plus
`latest-linux.yml` to GitHub Releases; AppImage installations use that manifest
for in-app updates. The separate
`deploy_and_build.sh` script is for the Python command-line package, not the
Electron desktop release.
