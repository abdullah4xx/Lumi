"""Command-line helpers that need no GTK: ``lumi --check-sources``."""

from __future__ import annotations

import argparse
import asyncio
import webbrowser
from typing import List, Optional

from . import __version__
from .config import Config
from .engine import Engine
from .local import LocalManager
from .sources import Context
from .store import Store
from .web import WebCompanionServer


async def check_sources(query: str, only: Optional[List[str]]) -> int:
    """Query each source once and report what came back (a live health check)."""
    cfg = Config()                                   # read-only use: never call cfg.set() here,
    engine = Engine(cfg)                             # it would overwrite the user's saved settings
    engine._context = lambda: Context(http=engine.http, cfg={**cfg.snapshot(), "verified_only": False})
    keys = [k for k in engine.sources if not only or k in only]
    unknown = [k for k in (only or []) if k not in engine.sources]
    if unknown or not keys:
        print(f"Unknown source(s): {', '.join(unknown) or '(none given)'}. Valid keys: {', '.join(engine.sources)}")
        await engine.close()
        return 2
    got = {}
    try:
        statuses = await engine.search(query, None, 1, keys, set(), lambda k, w: got.__setitem__(k, w))
    finally:
        await engine.close()
    width = max(len(k) for k in keys)
    failed = 0
    for key in keys:
        st = statuses[key]
        src = engine.sources[key]
        if st.state == "ok":
            known = sum(1 for w in got.get(key, []) if w.width)
            line = f"OK      {st.count} results ({known} with a known size)"
        elif st.state == "skipped":
            line = f"SKIP    {st.message}"
        else:
            failed += 1
            line = f"FAIL    {st.message}"
        print(f"{key:<{width}}  [{src.kind:<12}]  {line}")
    print(f"\n{len(keys)} sources checked, {failed} failed. Experimental sources may fail when a site changes.")
    return 0


def parse(argv=None):
    p = argparse.ArgumentParser(prog="lumi", description="Lumi command-line tools")
    p.add_argument("--version", action="store_true", help="print the version and exit")
    p.add_argument("--check-sources", action="store_true", help="query every source once and report its health")
    p.add_argument("--query", default="", help="search text for --check-sources")
    p.add_argument("--only", nargs="*", help="limit --check-sources to these source keys")
    p.add_argument("--web-server", action="store_true", help="run the local Web Companion server")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser (for desktop wrappers)")
    p.add_argument("--port", type=int, default=5910, help="port for the Web Companion server (default: 5910)")
    return p.parse_known_args(argv)


def run_web_server(port: int = 5910, open_browser: bool = True) -> int:
    """Run the localhost web interface and open it in the default browser."""
    async def _run_web():
        cfg = Config()
        eng = Engine(cfg)
        store = Store()
        local_mgr = LocalManager(cfg)
        srv = WebCompanionServer(cfg, eng, store, local_mgr)
        try:
            url = await srv.start(port=port)
            print(f"Lumi is running at {url}", flush=True)
            if open_browser:
                try:
                    opened = webbrowser.open(url)
                except (webbrowser.Error, OSError) as exc:
                    print(f"Could not open a browser: {exc}")
                    opened = False
                if not opened:
                    print(f"Open this address in your browser: {url}")
            print("Press Ctrl+C to stop.")
            while True:
                await asyncio.sleep(3600)
        finally:
            await srv.stop()
            await eng.close()

    try:
        asyncio.run(_run_web())
    except KeyboardInterrupt:
        pass
    return 0


def run_cli(args) -> Optional[int]:
    """Run the requested CLI action, or start the local web interface."""
    if args.version:
        print(f"Lumi {__version__}")
        return 0
    if args.check_sources:
        return asyncio.run(check_sources(args.query, args.only))
    return run_web_server(args.port, open_browser=not args.no_browser)
