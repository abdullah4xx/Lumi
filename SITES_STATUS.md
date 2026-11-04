# Wallpaper source status

Live checks and image-download verification performed 2026-11-03 and 2026-11-04. “Working” means listing and a real full-size image download both succeeded; listing-only results are not counted as working.

| Site | Status | Method | Live result | Notes |
|---|---|---|---|---|
| WallpapersCraft | Working | Playwright + HTML | 15 Nature items on each of pages 1 and 2, 30 unique; downloaded original JPEG verified as 4912x7360 (7,722,007 bytes). | Playwright confirmed listing/detail structure and direct image link. The detail page exposes resolution routes; each route reveals the direct original. `robots.txt` allows `/` and sets a 1s crawl delay but disallows `/search`; category browsing works, free-text search is disabled. |
| WallpapersWide | Working | HTML | 12 items on each of pages 1 and 2, no overlap; downloaded JPEG verified as 5120x2880 (5,319,589 bytes). | Listing pagination is `/page/N`; detail page exposes resolution-specific original links. |
| Bing Images | Working | Public search endpoint | 8 results for `nature wallpaper`; downloaded JPEG verified as 3840x2160 (3,711,105 bytes). | Live listing and full-size image verified. |
| Wallhaven | Working | API | 24 results for `nature`; downloaded JPEG verified as 7680x4320 (14,861,102 bytes). | API works without a key for this query; optional API key support remains available. |
| Wallhaven (website scraper) | Working | HTML | 23 results on page 1 and 21 on page 2 at a 1920px minimum; 44 unique IDs. Downloaded an original JPEG verified as 7680x4320 (14,861,102 bytes). | Search always requests `purity=100`; detail resolver requires an explicit SFW label. `robots.txt` allows the listing and detail paths. |
| Konachan (website scraper) | Working | HTML | 39 safe results on page 1 and 34 on page 2 at a 1920px minimum; 73 unique IDs. Downloaded an original JPEG verified as 3840x2160 (7,011,784 bytes). | Search forces `rating:s`; listing rating text is checked and the full-resolution image link is taken from the observed `directlink largeimg` element. |
| Yande.re (website scraper) | Working | HTML | 23 safe results on page 1 and 27 on page 2; 50 unique IDs. Downloaded an original JPEG verified as 7828x3694 (17,125,776 bytes). | Search forces `rating:s`; verified listing card exposes a direct original URL and original dimensions. `robots.txt` contains no blocking rules. |
| Safebooru (website scraper) | Working | HTML | 33 General-rated results on page 1 and 24 on page 2; 57 unique IDs. Downloaded an original JPEG verified as 4096x2304 (1,816,775 bytes). | Search forces `highres` and `rating:general`; each detail page is checked for its rating, original URL and dimensions. Observed pagination uses `pid` with 42 items per page; `robots.txt` allows the searched paths. |
| Gelbooru (website scraper) | Working | Playwright + HTML | 5 General-rated results on page 1 at the configured 3840px long-side minimum. Downloaded an original JPEG verified as 4327x2064 (2,259,810 bytes). | Search forces `highres` and `rating:general`; each detail page is checked for its rating, original URL and dimensions. Listing images have no `.preview` class; observed pagination uses `pid` with 42 items per page. `img4.gelbooru.com` has no `robots.txt` (404), so no image-host rule applies. |
| Danbooru | Working | Public JSON API | 3 General-rated results for `landscape` at the configured 3840px minimum. Downloaded an original JPEG verified as 4327x2064 (2,259,810 bytes). | Search always includes `rating:g`; tags, dimensions, and CDN hosts are validated. |
| Picsum | Working (opt-in) | Public JSON API | 16 browse-only results at the configured 3840px minimum. Downloaded an original JPEG response (490,823 bytes); API dimensions are 5000x3333. | Random photos only; no text search or wallpaper-specific filtering, so the source is disabled by default. |
| 4K Wallpapers | Blocked | Playwright / Cloudflare | Homepage and `/search/?q=landscape` both returned HTTP 403 with a Cloudflare “Performing security verification” page; zero result cards were available. | Existing HTML scraper cannot be validated against the current site response. No selectors or image links inferred from challenge markup. |
| HDWallpapers | Partial | HTML | 20 results on each of pages 1 and 2, no overlap; detail page's `Original` download returned JPEG 2560x1440 (489,333 bytes). | Below the current 3840px long-edge default; only useful when the user lowers the resolution threshold. |
| Simple Desktops | Partial | HTML | 28 results on pages 1 and 2, no overlap; original PNG verified as 2880x1800 (99,805 bytes). | Below the current 3840px long-edge default. |
| WallpaperFlare | Partial | HTML | 80 search results on each of pages 1 and 2, no overlap. | Its resolution route returns an HTML page requiring interactive download verification, not an image; original-image download is not automated. |
| Wikimedia Commons | Partial | API | 30 results for `nature wallpaper`; image download returned HTTP 429. | Listing works; image-host rate limiting prevented download verification. |
| Pinterest | Blocked | HTML / challenge | No usable listing data in the unauthenticated page response. | No scraper or automated challenge handling added. |
| Magnific | Blocked | HTML / challenge | Direct request returned a verification page rather than listing results. | No scraper or automated challenge handling added. |
| Unsplash | Partial | API | Not live-tested. | Requires an API key; source contract tests pass. |
| Pexels | Partial | API | Not live-tested. | Requires an API key; public search page returned HTTP 403; source contract tests pass. |
| Alpha Coders | Partial | API | Not live-tested. | Requires an API key; source contract tests pass. |
| Zerochan | Blocked | Playwright / HTML | `https://www.zerochan.net/` returned HTTP 503 in the browser. | No listing structure or image links could be inspected; no scraper added. |
| Minitokyo | Blocked | Playwright | HTTPS navigation failed with `ERR_CERT_AUTHORITY_INVALID`; HTTP fallback returned 503 Service Temporarily Unavailable (nginx). | No page structure was available to validate; no scraper added. |
| Yande.re | Working | Playwright + HTML | 23 + 27 safe results across two pages with no duplicates; downloaded original JPEG verified at 7828x3694 (17,125,776 bytes). | Search forces `rating:s`; listing rating and original-size link are validated. `robots.txt` contains no blocking rules. |

## Implementation notes

- The HTML scraper uses a shared anchor/image parser that tolerates relative links and different HTML attribute order.
- WallpaperFlare listing extraction now matches the page structure, but its download route is an interactive verification page, so the resolver fails explicitly instead of returning HTML as an image.
- HDWallpapers and WallpapersWide resolve detail-page download links rather than guessing image URLs or using thumbnails.
- Wallhaven's website-only source uses the observed HTML listing/detail structure, enforces SFW both in search parameters and on detail pages, and checks cached `robots.txt` rules before requests.
- Konachan's website-only source uses the observed post-list HTML, forces safe-rated search results, filters on the listing's rating and original dimensions, and checks cached `robots.txt` rules.
- Yande.re's website-only source uses the verified Booru listing structure, always forces `rating:s`, filters safe-rated results and full-size dimensions, and checks cached `robots.txt` rules.
- Safebooru's website-only source forces `rating:general` and `highres`, validates rating and original image dimensions on each detail page, and obeys observed `robots.txt` rules.
- Gelbooru's website-only source forces `rating:general` and `highres`, validates each post's rating and original image dimensions, and handles its observed `pid` pagination. Its original image host returned HTTP 404 for `robots.txt`, which is treated as no published rules.
- Danbooru's public API source forces General (`rating:g`), rejects non-image/unknown-size results, and filters against Lumi's configured minimum resolution.
- Picsum's random-photo source has no text search and is disabled by default; it only returns images meeting Lumi's configured minimum resolution.
- Experimental sources remain disabled by default.
- CAPTCHA/challenge pages are recorded as unavailable; no automated challenge bypass is implemented.

## Requested 50-site scraper progress

| Site | Status | Playwright / live result |
|---|---|---|
| Zerochan | Blocked | `https://www.zerochan.net/` returned HTTP 503. |
| WallpaperAccess | Blocked | Playwright reached the site, which returned HTTP 403 with an `Attention Required! | Cloudflare` page. No scraper added. |
| Unsplash | Blocked | Playwright loaded the search URL and received HTTP 403 (`Something went wrong`). The website-only scraper was not implemented. |
| Anime-Pictures | Blocked | Playwright opened the homepage and showed post links with dimensions. Opening a post and the posts listing both returned HTTP 403 (`Just a moment...`), so safe-rating and original-image behavior could not be verified and no scraper was added. |
| Konachan | Working | Playwright inspected listing and detail pages; 39 + 34 safe results across two pages with no duplicates at the 1920px minimum. Downloaded an original JPEG verified at 3840x2160 (7,011,784 bytes). Search forces `rating:s`; the listing's safe rating and original-size link are validated. |
| Yande.re | Working | Playwright inspected safe listing and detail pages; 23 + 27 results across two pages with no duplicates, all safe-rated. Downloaded original JPEG verified at 7828x3694 (17,125,776 bytes). Search forces `rating:s`; `robots.txt` contains no blocking rules. |
| Minitokyo | Blocked | Playwright reported `ERR_CERT_AUTHORITY_INVALID` over HTTPS; HTTP fallback rendered an nginx 503 Service Temporarily Unavailable page. No selectors or image URLs could be verified; scraper skipped. |
| Safebooru | Working | Playwright inspected listing and detail markup; 33 General-rated results on page 1 and 24 on page 2, 57 unique. Downloaded original JPEG verified at 4096x2304 (1,816,775 bytes). Search enforces `rating:general` + `highres`; detail pages are checked for rating and original image dimensions. |
| Gelbooru | Working | Playwright inspected listing/details; live scraper returned 5 General-rated images at the configured 3840px minimum. Downloaded an original JPEG verified at 4327x2064 (2,259,810 bytes). |
| MoeWalls | Not inspected | Pending. |
| Wallpapers Den | Not inspected | Pending. |
| Wall Alphacoders | Not inspected | Pending. |
| HD Wallpapers | Unverified | Playwright CLI failed with `TypeError: Cannot read properties of undefined (reading 'url')`; the existing HTML scraper is partial and was not upgraded in this run. |
| WallpaperAccess | Not inspected | Pending. |
| Wallpapers.com | Not inspected | Pending. |
| HDQWalls | Not inspected | Pending. |
| 4K Wallpapers | Blocked | Playwright opened the homepage and `/search/?q=landscape`; both returned HTTP 403 with a Cloudflare “Performing security verification” challenge. No listing cards were available, so selectors, pagination, and original-image links cannot be inspected. Existing HTML parser remains unverified against the live page. |
| Wallpaper Safari | Not inspected | Pending. |
| WallpaperFlare | Not inspected | Existing listing scraper is partial; no Playwright inspection in this run. |
| Peakpx | Not inspected | Pending. |
| Wallpaperup | Not inspected | Pending. |
| Wallpapersmug | Not inspected | Pending. |
| WallpapersCraft | Working | Playwright listing/detail inspected; 30 unique Nature items across two pages; original JPEG verified at 4912x7360. |
| Wallpapers Wide | Unverified | Playwright CLI failed with `TypeError: Cannot read properties of undefined (reading 'url')`; the existing HTML scraper has prior live-download tests, but this run could not inspect its page structure in the browser. |
| Desktop Nexus | Not inspected | Pending. |
| Pixelstalk | Not inspected | Pending. |
| Wallpaper Cave | Not inspected | Pending. |
| Wallhaven | Working | Playwright inspected listing and detail pages; website-only HTML scraper returned 23 + 21 results across two pages with no duplicates at the 1920px minimum. Downloaded original JPEG verified at 7680x4320 (14,861,102 bytes). Always requests SFW results and validates the detail-page SFW label; obeys the observed robots.txt allow rules. |
| Unsplash | Not inspected | Existing source is API-based and is not counted for this website-only task. |
| Pexels | Not inspected | Existing source is API-based and is not counted for this website-only task. |
| Pixabay | Not inspected | Existing source is API-based and is not counted for this website-only task. |
| Desktopography | Not inspected | Pending. |
| Simple Desktops | Unverified | Chrome page closed during navigation before a snapshot was available. |
| Reddit r/MinimalWallpaper | Not inspected | Existing source is API-based and is not counted for this website-only task. |
| WallpaperHub | Unverified | Playwright CLI failed with `TypeError: Cannot read properties of undefined (reading 'url')` before a page snapshot was available. |
| GNOME Look | Not inspected | Pending. |
| Gradienta | Not inspected | Pending. |
| Digital Blasphemy | Not inspected | Pending. |
| Vladstudio | Not inspected | Pending. |
| 500px | Not inspected | Pending. |
| ArtStation | Not inspected | Pending. |
| Wallpaperbetter | Not inspected | Pending. |
| DeviantArt | Not inspected | Existing source is API-based and is not counted for this website-only task. |
| Wallpaper Kiwi | Not inspected | Pending. |
| Mocah | Not inspected | Pending. |
| WallpaperTag | Not inspected | Pending. |
| Backiee | Not inspected | Pending. |
| Free Wallpaper | Not inspected | Pending. |
| Wallpapers.net | Not inspected | Pending. |
| WallpaperDog | Not inspected | Pending. |
| HDWallpapers.net | Not inspected | Pending. |
| Behance | Not inspected | Pending. |
