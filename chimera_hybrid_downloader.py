#!/usr/bin/env python3
# Chimera Hybrid Map Downloader / Local Compatibility Proxy v3.6
# Priority:
# 1. HaloNet normal locator (.inv/raw payload)
# 2. HaloNet static ZIP fallback
# 3. CE3 archive fallback
# 4. HaloMaps.org fallback
#
# Chimera setting:
#     download_template=http://127.0.0.1:8765/{map}

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, quote, urlencode, urlparse, urljoin
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
import html
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import re
import shutil
import threading
import time
import zipfile
import json
import queue
import os
import sys

HOST = "127.0.0.1"
PORT = 8765

PRIMARY_LOCATOR = "http://maps.halonet.net/halonet/locator.php"
STATIC_ZIP = "https://maps.halonet.net/maps/{map}.zip"

CE3_BASE = "https://haloce3.com"
CE3_WP_SEARCH = CE3_BASE + "/wp-json/wp/v2/search?search={query}&per_page=20"
CE3_SEARCH = CE3_BASE + "/?s={query}"
CE3_FILTER_SEARCH = CE3_BASE + "/ce/?_sf_s={query}"
CE3_CATEGORY_URLS = [
    CE3_BASE + "/category/downloads/multiplayer/original-multiplayer/",
    CE3_BASE + "/category/downloads/multiplayer/modified-multiplayer/",
    CE3_BASE + "/category/downloads/multiplayer/",
    CE3_BASE + "/category/downloads/open-sauce-maps/",
    CE3_BASE + "/category/downloads/singleplayer/",
]

HALOMAPS_BASE = "https://www.halomaps.org"
HALOMAPS_INDEX = HALOMAPS_BASE + "/hce/index.cfm"
HALOMAPS_DETAIL_BASE = HALOMAPS_BASE + "/hce/detail.cfm?fid={fid}"

# Current HaloMaps map categories. Multiplayer categories are tried first.
HALOMAPS_CATEGORY_IDS = [
    24,  # Modified Multiplayer Maps
    10,  # Halo CE Maps
    39,  # Multiplayer Maps w/ AI
    29,  # Maps for Machinima
    40,  # YELO / Open Sauce Maps
    41,  # Lumoria Campaign
    27,  # Modified Single Player Maps
    35,  # CMT Single Player Maps
    37,  # Custom Single Player Maps
]

PRIMARY_CONNECT_TIMEOUT = 12
FALLBACK_CONNECT_TIMEOUT = 15

# Anti-hang controls.
# A socket must produce data within this many seconds during a real file
# download, otherwise that source is treated as stalled.
NETWORK_STALL_TIMEOUT = 15

# Maximum wall-clock time for one upstream map/archive download.
UPSTREAM_FILE_BUDGET = 300

# Absolute maximum for one Chimera map request across ALL sources.
# Even if a third-party server behaves badly, Chimera will eventually get
# an HTTP 504 instead of remaining on "Connecting to map server..." forever.
REQUEST_WATCHDOG_TIMEOUT = 360

# Log transfer activity every ~5 MiB so a large ZIP does not look frozen in
# the helper console while Chimera is still waiting for extraction.
PROGRESS_INTERVAL_BYTES = 5 * 1024 * 1024

# If Chimera disconnects/stops reading the local response, don't leave a
# server thread blocked forever.
LOCAL_CLIENT_TIMEOUT = 15

CE3_LOOKUP_TIMEOUT = 5
CE3_LOOKUP_BUDGET = 12
CE3_DOWNLOAD_TIMEOUT = UPSTREAM_FILE_BUDGET
HALOMAPS_LOOKUP_TIMEOUT = 5
HALOMAPS_LOOKUP_BUDGET = 12
HALOMAPS_DOWNLOAD_TIMEOUT = UPSTREAM_FILE_BUDGET

def runtime_state_dir():
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            path = Path(local_appdata) / "ChimeraHybridMapDownloader"
        else:
            path = Path.home() / "AppData" / "Local" / "ChimeraHybridMapDownloader"
    else:
        path = Path.home() / ".chimera_hybrid_map_downloader"

    path.mkdir(parents=True, exist_ok=True)
    return path

def bundled_resource_path(filename):
    """
    Return a file bundled into a PyInstaller one-file build, or a file beside
    the Python source when running uncompiled.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).resolve().parent / filename

BASE_DIR = runtime_state_dir()
LOG_FILE = BASE_DIR / "chimera_downloader.log"
CACHE_DIR = BASE_DIR / "cache"

# A user/developer can optionally drop a newer index into Local AppData
# without rebuilding. Otherwise the copy embedded in the EXE is used.
HALONET_INDEX_OVERRIDE = BASE_DIR / "halonet_map_index.json"
HALONET_INDEX_BUNDLED = bundled_resource_path("halonet_map_index.json")
CE3_ENTRY_CACHE = CACHE_DIR / "ce3_entries.json"
CE3_RAW_CACHE_DIR = CACHE_DIR / "ce3_raw"
CE3_ZIP_CACHE_DIR = CACHE_DIR / "ce3_zips"
HALOMAPS_FID_CACHE = CACHE_DIR / "halomaps_fids.json"
PRIMARY_CACHE_DIR = CACHE_DIR / "primary"
RAW_MAP_CACHE_DIR = CACHE_DIR / "raw_maps"
ZIP_CACHE_DIR = CACHE_DIR / "zips"
HALOMAPS_RAW_CACHE_DIR = CACHE_DIR / "halomaps_raw"
HALOMAPS_ZIP_CACHE_DIR = CACHE_DIR / "halomaps_zips"

for folder in (
    PRIMARY_CACHE_DIR,
    CE3_RAW_CACHE_DIR,
    CE3_ZIP_CACHE_DIR,
    RAW_MAP_CACHE_DIR,
    ZIP_CACHE_DIR,
    HALOMAPS_RAW_CACHE_DIR,
    HALOMAPS_ZIP_CACHE_DIR,
):
    folder.mkdir(parents=True, exist_ok=True)

locks_guard = threading.Lock()
map_locks = {}

# Fallback progress UI hook.
# The public launcher installs a callback here. Normal HaloNet downloads do
# NOT activate it because Chimera already displays its own progress.
PROGRESS_CALLBACK = None
_progress_local = threading.local()

def set_progress_callback(callback):
    global PROGRESS_CALLBACK
    PROGRESS_CALLBACK = callback

def _emit_progress(event):
    callback = PROGRESS_CALLBACK
    if callback is None:
        return
    try:
        callback(dict(event))
    except Exception:
        pass

def progress_begin(map_name, source, stage="Searching"):
    now = time.monotonic()
    _progress_local.ctx = {
        "active": True,
        "map": map_name,
        "source": source,
        "stage": stage,
        "track_bytes": False,
        "last_emit": 0.0,
        "downloaded": 0,
        "total": None,
    }
    _emit_progress({
        "action": "show",
        "map": map_name,
        "source": source,
        "stage": stage,
        "downloaded": 0,
        "total": None,
        "reset_transfer": True,
        "timestamp": now,
    })

def progress_stage(stage, source=None, track_bytes=False, reset_transfer=False):
    ctx = getattr(_progress_local, "ctx", None)
    if not ctx or not ctx.get("active"):
        return

    if source is not None:
        ctx["source"] = source
    ctx["stage"] = stage
    ctx["track_bytes"] = bool(track_bytes)

    if reset_transfer:
        ctx["downloaded"] = 0
        ctx["total"] = None
        ctx["last_emit"] = 0.0

    _emit_progress({
        "action": "update",
        "map": ctx["map"],
        "source": ctx["source"],
        "stage": ctx["stage"],
        "downloaded": ctx.get("downloaded", 0),
        "total": ctx.get("total"),
        "reset_transfer": bool(reset_transfer),
        "timestamp": time.monotonic(),
    })

def progress_transfer(downloaded, total):
    ctx = getattr(_progress_local, "ctx", None)
    if not ctx or not ctx.get("active") or not ctx.get("track_bytes"):
        return

    ctx["downloaded"] = int(downloaded)
    ctx["total"] = int(total) if total else None

    now = time.monotonic()
    # UI updates at most about 5 times/second, plus the final update.
    final = bool(total and downloaded >= total)
    if not final and now - ctx.get("last_emit", 0.0) < 0.20:
        return

    ctx["last_emit"] = now
    _emit_progress({
        "action": "update",
        "map": ctx["map"],
        "source": ctx["source"],
        "stage": ctx["stage"],
        "downloaded": ctx["downloaded"],
        "total": ctx["total"],
        "reset_transfer": False,
        "timestamp": now,
    })

def progress_complete(message="Ready for Halo"):
    ctx = getattr(_progress_local, "ctx", None)
    if not ctx or not ctx.get("active"):
        return

    _emit_progress({
        "action": "complete",
        "map": ctx["map"],
        "source": ctx["source"],
        "stage": message,
        "downloaded": ctx.get("downloaded", 0),
        "total": ctx.get("total"),
        "timestamp": time.monotonic(),
    })
    ctx["active"] = False

def progress_error(message="Map unavailable"):
    ctx = getattr(_progress_local, "ctx", None)
    if not ctx or not ctx.get("active"):
        return

    _emit_progress({
        "action": "error",
        "map": ctx["map"],
        "source": ctx["source"],
        "stage": message,
        "downloaded": ctx.get("downloaded", 0),
        "total": ctx.get("total"),
        "timestamp": time.monotonic(),
    })
    ctx["active"] = False

def log(message=""):
    line = str(message)

    # Console output still works if someone runs the Python script manually.
    try:
        print(line, flush=True)
    except Exception:
        pass

    # Silent/public launcher has no console, so always retain a small text log.
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{timestamp}] {line}\n")
    except Exception:
        pass

def _content_length(response):
    try:
        value = response.headers.get("Content-Length")
        return int(value) if value else None
    except Exception:
        return None

def read_response_bounded(response, total_timeout, label="download"):
    """
    Read a response with a true wall-clock deadline.

    urllib's timeout is a socket/stall timeout, not a total transfer timeout.
    A server that sends one byte periodically can otherwise keep a request
    alive indefinitely.
    """
    deadline = time.monotonic() + max(0.5, total_timeout)
    total_expected = _content_length(response)
    chunks = []
    downloaded = 0
    next_progress = PROGRESS_INTERVAL_BYTES

    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{label} exceeded {total_timeout}s total transfer budget"
            )

        chunk = response.read(1024 * 1024)
        if not chunk:
            break

        chunks.append(chunk)
        downloaded += len(chunk)
        progress_transfer(downloaded, total_expected)

        if downloaded >= next_progress:
            if total_expected:
                pct = min(100.0, downloaded * 100.0 / total_expected)
                log(
                    f"[TRANSFER] {label}: "
                    f"{downloaded / 1024 / 1024:.1f}/"
                    f"{total_expected / 1024 / 1024:.1f} MiB "
                    f"({pct:.0f}%)"
                )
            else:
                log(
                    f"[TRANSFER] {label}: "
                    f"{downloaded / 1024 / 1024:.1f} MiB received"
                )
            next_progress += PROGRESS_INTERVAL_BYTES

    return b"".join(chunks)

def copy_response_bounded(response, destination_file, total_timeout, label="download", initial=b""):
    """Stream a response to disk with a wall-clock deadline and progress."""
    deadline = time.monotonic() + max(0.5, total_timeout)
    total_expected = _content_length(response)
    downloaded = 0

    if initial:
        destination_file.write(initial)
        downloaded += len(initial)

    next_progress = (
        ((downloaded // PROGRESS_INTERVAL_BYTES) + 1) * PROGRESS_INTERVAL_BYTES
    )

    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{label} exceeded {total_timeout}s total transfer budget"
            )

        chunk = response.read(1024 * 1024)
        if not chunk:
            break

        destination_file.write(chunk)
        downloaded += len(chunk)
        progress_transfer(downloaded, total_expected)

        if downloaded >= next_progress:
            if total_expected:
                pct = min(100.0, downloaded * 100.0 / total_expected)
                log(
                    f"[TRANSFER] {label}: "
                    f"{downloaded / 1024 / 1024:.1f}/"
                    f"{total_expected / 1024 / 1024:.1f} MiB "
                    f"({pct:.0f}%)"
                )
            else:
                log(
                    f"[TRANSFER] {label}: "
                    f"{downloaded / 1024 / 1024:.1f} MiB received"
                )
            next_progress += PROGRESS_INTERVAL_BYTES

    return downloaded

def map_lock(name):
    with locks_guard:
        return map_locks.setdefault(name.lower(), threading.Lock())

def validate_map_name(name):
    name = name.strip()
    if not name:
        raise ValueError("empty map name")
    if "/" in name or "\\" in name or ".." in name or ":" in name or "\x00" in name:
        raise ValueError("invalid map name")
    return name

def safe_filename(name):
    return "".join(c if c.isalnum() or c in "._-()[] " else "_" for c in name)

def looks_like_html(first_bytes, content_type=""):
    ct = (content_type or "").lower()
    head = first_bytes.lstrip().lower()
    return (
        "text/html" in ct
        or head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
    )

def looks_like_zip(first_bytes, content_type=""):
    ct = (content_type or "").lower()
    return (
        first_bytes.startswith(b"PK\x03\x04")
        or first_bytes.startswith(b"PK\x05\x06")
        or first_bytes.startswith(b"PK\x07\x08")
        or "application/zip" in ct
        or "application/x-zip-compressed" in ct
    )

def raw_halo_map_signature_ok(path):
    with open(path, "rb") as f:
        header = f.read(0x800)
    standard = (
        len(header) >= 0x800
        and header[0:4] == b"daeh"
        and header[0x7FC:0x800] == b"toof"
    )
    alternate = (
        len(header) >= 0x5F4
        and header[0x2C0:0x2C4] == b"dehE"
        and header[0x5F0:0x5F4] == b"tofG"
    )
    return standard or alternate

def download_to_file(url, destination, timeout, user_agent):
    temp = destination.with_suffix(destination.suffix + ".part")
    if temp.exists():
        temp.unlink()

    request = Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})

    try:
        # 'timeout' remains the connection/stall limit for the initial request;
        # the entire transfer separately gets UPSTREAM_FILE_BUDGET.
        socket_timeout = min(max(1, timeout), NETWORK_STALL_TIMEOUT)

        with urlopen(request, timeout=socket_timeout) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            final_url = response.geturl()

            if status < 200 or status >= 300:
                raise RuntimeError(f"HTTP {status}")

            with open(temp, "wb") as f:
                first = response.read(4096)

                if looks_like_html(first, content_type):
                    raise RuntimeError(
                        f"upstream returned HTML instead of map data "
                        f"({content_type or 'unknown type'})"
                    )

                copy_response_bounded(
                    response,
                    f,
                    UPSTREAM_FILE_BUDGET,
                    label="HaloNet primary",
                    initial=first,
                )

        if temp.stat().st_size < 0x800:
            raise RuntimeError("download is too small to be a Halo map payload")

        temp.replace(destination)
        return final_url, content_type, destination.stat().st_size

    except Exception:
        if temp.exists():
            temp.unlink()
        raise

def http_get_bytes(url, timeout, user_agent="Chimera-Hybrid-Map-Downloader/3.6"):
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    socket_timeout = min(max(0.5, timeout), NETWORK_STALL_TIMEOUT)

    with urlopen(req, timeout=socket_timeout) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        data = read_response_bounded(
            response,
            timeout,
            label="HTTP request",
        )

    return status, content_type, final_url, data

def http_get_text(url, timeout, user_agent="Chimera-Hybrid-Map-Downloader/3.6"):
    status, content_type, final_url, data = http_get_bytes(url, timeout, user_agent)
    encoding = "utf-8"
    m = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if m:
        encoding = m.group(1).strip("'\"")
    try:
        text = data.decode(encoding, errors="replace")
    except Exception:
        text = data.decode("utf-8", errors="replace")
    return status, content_type, final_url, text

def try_primary(map_name):
    cache_path = PRIMARY_CACHE_DIR / f"{safe_filename(map_name)}.payload"
    if cache_path.exists() and cache_path.stat().st_size >= 0x800:
        log(f"[PRIMARY] Cache hit: {map_name}")
        return cache_path, "primary-cache"
    query = urlencode({"format": "inv", "map": map_name, "type": "halom"})
    url = f"{PRIMARY_LOCATOR}?{query}"
    log(f"[PRIMARY] Trying HaloNet locator for {map_name}")
    try:
        final_url, _, size = download_to_file(
            url, cache_path, PRIMARY_CONNECT_TIMEOUT, "Chimera-Hybrid-Map-Downloader/3.6"
        )
        log(f"[PRIMARY] Success ({size / 1024 / 1024:.1f} MiB)")
        if final_url != url:
            log(f"[PRIMARY] Final source: {final_url}")
        return cache_path, "primary"
    except HTTPError as e:
        log(f"[PRIMARY] HTTP {e.code} - falling back")
    except URLError as e:
        log(f"[PRIMARY] Network error: {e.reason} - falling back")
    except Exception as e:
        log(f"[PRIMARY] Failed: {e} - falling back")
    if cache_path.exists():
        cache_path.unlink()
    return None, None

def find_map_member(zf, requested):
    members = [n for n in zf.namelist() if not n.endswith("/") and n.lower().endswith(".map")]
    if not members:
        raise RuntimeError("ZIP contains no .map file")
    wanted = (requested + ".map").lower()
    for member in members:
        if Path(member).name.lower() == wanted:
            return member
    if len(members) == 1:
        return members[0]
    for member in members:
        basename = Path(member).name.lower()
        if requested.lower() in basename:
            return member
    raise RuntimeError("ZIP contains multiple .map files and none exactly match " + f"{requested}.map")

def extract_map_from_zip(zip_path, map_name, raw_map_path):
    temp_map = raw_map_path.with_suffix(".map.part")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            member = find_map_member(zf, map_name)
            with zf.open(member, "r") as src, open(temp_map, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        if temp_map.stat().st_size < 0x800:
            raise RuntimeError("extracted map is too small")
        if not raw_halo_map_signature_ok(temp_map):
            with open(temp_map, "rb") as f:
                header = f.read(0x800)
            raise RuntimeError(
                "extracted .map failed Halo header validation "
                + f"(start={header[:4]!r}, footer={header[0x7FC:0x800]!r})"
            )
        temp_map.replace(raw_map_path)
        return raw_map_path
    except Exception:
        if temp_map.exists():
            temp_map.unlink()
        raise

_HALONET_INDEX_LOCK = threading.Lock()
_HALONET_INDEX_LOADED = False
_HALONET_STATIC_INDEX = {}
_HALONET_INDEX_META = {}


def load_halonet_static_index():
    """
    Load the shipped HaloNet exact-filename index.

    Format:
        {
          "format_version": 1,
          "complete": true,
          "map_count": 7124,
          "index": {
             "new_mombasa_race": ["New_Mombasa_Race"],
             ...
          }
        }

    Keys are casefolded map names. Values are lists because two historical
    filenames could theoretically differ only by case.
    """
    global _HALONET_INDEX_LOADED
    global _HALONET_STATIC_INDEX
    global _HALONET_INDEX_META

    if _HALONET_INDEX_LOADED:
        return _HALONET_STATIC_INDEX

    with _HALONET_INDEX_LOCK:
        if _HALONET_INDEX_LOADED:
            return _HALONET_STATIC_INDEX

        chosen = None
        for candidate in (HALONET_INDEX_OVERRIDE, HALONET_INDEX_BUNDLED):
            try:
                if candidate.exists() and candidate.is_file():
                    chosen = candidate
                    break
            except Exception:
                continue

        index = {}
        meta = {}

        if chosen is not None:
            try:
                with open(chosen, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                raw_index = payload.get("index", {})
                if not isinstance(raw_index, dict):
                    raise ValueError("index field is not an object")

                for key, values in raw_index.items():
                    folded = str(key).casefold()
                    if isinstance(values, str):
                        values = [values]
                    if not isinstance(values, list):
                        continue

                    cleaned = []
                    for value in values:
                        value = str(value).strip()
                        if value and value not in cleaned:
                            cleaned.append(value)

                    if cleaned:
                        index[folded] = cleaned

                meta = {
                    "path": str(chosen),
                    "map_count": payload.get("map_count"),
                    "complete": bool(payload.get("complete", False)),
                    "generated_utc": payload.get("generated_utc"),
                    "source": payload.get("source"),
                }

                log(
                    "[HALONET-INDEX] Loaded "
                    f"{len(index)} case-insensitive keys / "
                    f"{payload.get('map_count', '?')} filenames "
                    f"from {chosen}"
                )

                if not meta["complete"]:
                    log(
                        "[HALONET-INDEX] WARNING: shipped index is marked "
                        "incomplete; heuristic case probes remain enabled"
                    )

            except Exception as e:
                log(
                    "[HALONET-INDEX] Failed to load "
                    f"{chosen}: {type(e).__name__}: {e}"
                )

        else:
            log(
                "[HALONET-INDEX] No bundled index found; "
                "using capitalization heuristics only"
            )

        _HALONET_STATIC_INDEX = index
        _HALONET_INDEX_META = meta
        _HALONET_INDEX_LOADED = True
        return _HALONET_STATIC_INDEX


def halonet_indexed_names(map_name):
    index = load_halonet_static_index()
    return list(index.get(str(map_name).casefold(), []))


def halonet_static_name_candidates(map_name):
    """
    Build a bounded list of HaloNet static ZIP filename candidates.

    Priority:
      1. Exact map name requested by Chimera.
      2. Exact capitalization from the shipped HaloNet filename index.
      3. Legacy capitalization guesses as a safety net.

    Chimera/Halo commonly lowercases internal map names, while HaloNet's
    /maps/ static URL is case-sensitive. The shipped index removes the need
    to guess names such as BMT_New_Mombasa or New_Mombasa_Race.
    """
    candidates = []

    def add(value):
        value = str(value).strip()
        if value and value not in candidates:
            candidates.append(value)

    # Fast path: many files are already stored lowercase.
    add(map_name)

    # Canonical names from the shipped cache.
    for canonical_name in halonet_indexed_names(map_name):
        add(canonical_name)

    # Heuristic safety net for a newly-added HaloNet map that has not yet made
    # it into our shipped cache.
    add(map_name.title())

    add("_".join(
        part[:1].upper() + part[1:] if part else part
        for part in map_name.split("_")
    ))

    add(map_name[:1].upper() + map_name[1:] if map_name else map_name)
    add(map_name.lower())
    add(map_name.upper())

    return candidates


def try_static_zip_fallback(map_name):
    raw_map = RAW_MAP_CACHE_DIR / f"{safe_filename(map_name)}.map"
    zip_path = ZIP_CACHE_DIR / f"{safe_filename(map_name)}.zip"
    if raw_map.exists() and raw_map.stat().st_size >= 0x800:
        if raw_halo_map_signature_ok(raw_map):
            log(f"[FALLBACK-1] Raw map cache hit: {map_name}")
            return raw_map, "fallback-zip-cache"
        raw_map.unlink()
    if not zip_path.exists():
        temp = zip_path.with_suffix(".zip.part")
        candidates = halonet_static_name_candidates(map_name)
        last_error = None
        downloaded = False

        for index, static_name in enumerate(candidates, start=1):
            url = STATIC_ZIP.format(map=quote(static_name, safe="._-()[] "))
            indexed_names = halonet_indexed_names(map_name)
            candidate_origin = (
                "index"
                if static_name in indexed_names and static_name != map_name
                else "probe"
            )
            log(
                f"[FALLBACK-1] HaloNet ZIP candidate "
                f"{index}/{len(candidates)} ({candidate_origin}): {url}"
            )

            request = Request(url, headers={
                "User-Agent": "Chimera-Hybrid-Map-Downloader/3.6",
                "Accept": "application/zip,*/*",
            })

            try:
                # Only switch the UI into real transfer mode once a response
                # is successfully opened. 404 probes should not reset the
                # displayed transfer speed/percentage repeatedly.
                with urlopen(
                    request,
                    timeout=min(FALLBACK_CONNECT_TIMEOUT, NETWORK_STALL_TIMEOUT),
                ) as response:
                    progress_stage(
                        "Downloading",
                        source="HaloNet ZIP",
                        track_bytes=True,
                        reset_transfer=True,
                    )
                    with open(temp, "wb") as f:
                        copy_response_bounded(
                            response,
                            f,
                            UPSTREAM_FILE_BUDGET,
                            label=f"HaloNet ZIP {static_name}",
                        )

                temp.replace(zip_path)
                log(
                    f"[FALLBACK-1] HaloNet static filename matched: "
                    f"{static_name}.zip"
                )
                downloaded = True
                break

            except HTTPError as e:
                last_error = e
                if temp.exists():
                    temp.unlink()

                if e.code == 404:
                    log(
                        f"[FALLBACK-1] Static filename not found "
                        f"({static_name}.zip); trying next case variant"
                    )
                    continue

                # Other HTTP errors are source/server errors rather than a
                # capitalization miss.
                raise

            except Exception as e:
                last_error = e
                if temp.exists():
                    temp.unlink()
                raise

        if not downloaded:
            if last_error is not None:
                raise RuntimeError(
                    f"HaloNet static ZIP was not found for {map_name} "
                    f"after trying {len(candidates)} capitalization variants"
                ) from last_error
            raise RuntimeError(
                f"HaloNet static ZIP was not found for {map_name}"
            )
    else:
        log(f"[FALLBACK-1] ZIP cache hit: {map_name}")
        progress_stage("Using cached archive", source="HaloNet ZIP", track_bytes=False)
    log(f"[FALLBACK-1] Extracting {map_name}.map")
    progress_stage("Extracting map", source="HaloNet ZIP", track_bytes=False)
    raw = extract_map_from_zip(zip_path, map_name, raw_map)
    log(f"[FALLBACK-1] Ready ({raw.stat().st_size / 1024 / 1024:.1f} MiB)")
    return raw, "fallback-zip"


# ---------------------------------------------------------------------------
# CE3 fallback
# ---------------------------------------------------------------------------

def load_json_cache(path):
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_json_cache(path, data):
    try:
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as e:
        log(f"[CE3] Warning: could not save cache: {e}")

class SimpleLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self._href = attrs.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            label = " ".join("".join(self._text).split())
            self.links.append((self._href, label))
            self._href = None
            self._text = []

class SimpleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())

    def text(self):
        return " ".join(self.parts)

def ce3_session():
    return build_opener(HTTPCookieProcessor(CookieJar()))

def ce3_get_bytes(opener, url, timeout, referer=None):
    headers = {
        "User-Agent": "Chimera-Hybrid-Map-Downloader/3.6",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer

    request = Request(url, headers=headers)
    socket_timeout = min(max(0.5, timeout), NETWORK_STALL_TIMEOUT)

    with opener.open(request, timeout=socket_timeout) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        data = read_response_bounded(
            response,
            timeout,
            label="CE3 request",
        )

    return status, content_type, final_url, data

def ce3_get_text(opener, url, timeout, referer=None):
    status, content_type, final_url, data = ce3_get_bytes(
        opener, url, timeout, referer
    )
    encoding = "utf-8"
    m = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if m:
        encoding = m.group(1).strip("'\"")
    try:
        body = data.decode(encoding, errors="replace")
    except Exception:
        body = data.decode("utf-8", errors="replace")
    return status, content_type, final_url, body

def ce3_visible_text(html_text):
    parser = SimpleTextParser()
    parser.feed(html_text)
    return " ".join(parser.text().split())

def ce3_extract_map_names(html_text):
    """
    CE3 entries explicitly expose a 'Map Name:' field. It can contain one
    filename or a comma-separated list of maps.
    """
    visible = ce3_visible_text(html_text)
    names = []

    # Grab the field until a normal CE3 metadata boundary.
    match = re.search(
        r"Map\s+Name:\s*(.+?)(?=\s+(?:Size:|Based\s+On:|Download(?:s)?:|"
        r"Description:|Original\s+Release\s+Date:|Category:|Section:)|$)",
        visible,
        re.I,
    )
    if match:
        field = match.group(1)
        for item in re.findall(r"([^,;]+?\.map)\b", field, re.I):
            cleaned = " ".join(item.strip(" -–—").split())
            if cleaned and cleaned.lower() not in [n.lower() for n in names]:
                names.append(cleaned)

    # Backup extraction for odd templates where field boundaries are missing.
    if not names:
        idx = visible.lower().find("map name:")
        if idx >= 0:
            sample = visible[idx:idx + 700]
            for item in re.findall(
                r"([A-Za-z0-9_\-\[\]\(\) .']+?\.map)\b", sample, re.I
            ):
                cleaned = " ".join(item.strip(" -–—").split())
                cleaned = re.sub(r"^Map\s+Name:\s*", "", cleaned, flags=re.I)
                if cleaned and cleaned.lower() not in [n.lower() for n in names]:
                    names.append(cleaned)

    return names

def ce3_entry_matches(map_name, html_text, title=""):
    requested = normalize_map_key(map_name)
    map_names = ce3_extract_map_names(html_text)

    for filename in map_names:
        base = filename[:-4] if filename.lower().endswith(".map") else filename
        if normalize_map_key(base) == requested:
            return True, map_names

    # A few CE3 entries may omit Map Name. Only allow an exact normalized
    # title match in that case; archive extraction still validates the map.
    if not map_names and title and normalize_map_key(title) == requested:
        return True, map_names

    return False, map_names

def ce3_parse_entry_links(page_url, html_text):
    parser = SimpleLinkParser()
    parser.feed(html_text)
    results = []
    seen = set()

    for href, label in parser.links:
        if not href:
            continue
        absolute = urljoin(page_url, html.unescape(href))
        parsed = urlparse(absolute)
        if parsed.netloc.lower().endswith("haloce3.com") and "/downloads/" in parsed.path:
            # Ignore category paths; actual entries continue after /downloads/.
            if "/category/" in parsed.path:
                continue
            key = absolute.split("#", 1)[0]
            if key not in seen:
                seen.add(key)
                results.append((key, label))

    return results

def ce3_extract_download_links(page_url, html_text, map_name):
    parser = SimpleLinkParser()
    parser.feed(html_text)

    requested_key = normalize_map_key(map_name)
    ranked = []
    seen = set()

    for href, label in parser.links:
        if not href:
            continue
        absolute = urljoin(page_url, html.unescape(href))
        label_clean = " ".join(label.split())
        lower_label = label_clean.lower()
        lower_url = absolute.lower()

        direct_ext = bool(re.search(r"\.(?:zip|map)(?:$|[?#])", lower_url))
        says_download = "download" in lower_label
        known_download_path = (
            "download" in lower_url
            or "/dl/" in lower_url
            or "dl." in urlparse(absolute).netloc.lower()
        )

        if not (direct_ext or says_download or known_download_path):
            continue

        # Never treat the CE3 detail page itself as its own download.
        if absolute.rstrip("/") == page_url.rstrip("/"):
            continue

        score = 0
        if normalize_map_key(label_clean).find(requested_key) >= 0:
            score += 100
        if says_download:
            score += 30
        if direct_ext:
            score += 20

        key = absolute.split("#", 1)[0]
        if key not in seen:
            seen.add(key)
            ranked.append((score, key, label_clean))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [(url, label) for _, url, label in ranked]

def ce3_find_exact_map_member(zf, requested):
    requested_key = normalize_map_key(requested)
    members = [
        n for n in zf.namelist()
        if not n.endswith("/") and n.lower().endswith(".map")
    ]

    for member in members:
        base = Path(member).name[:-4]
        if normalize_map_key(base) == requested_key:
            return member

    raise RuntimeError(
        f"CE3 archive does not contain the requested {requested}.map"
    )

def ce3_save_payload(data, content_type, final_url, map_name):
    safe = safe_filename(map_name)
    raw_target = CE3_RAW_CACHE_DIR / f"{safe}.map"
    zip_target = CE3_ZIP_CACHE_DIR / f"{safe}.zip"

    # ZIP
    if looks_like_zip(data[:16], content_type) or final_url.lower().split("?")[0].endswith(".zip"):
        temp_zip = zip_target.with_suffix(".zip.part")
        with open(temp_zip, "wb") as f:
            f.write(data)
        temp_zip.replace(zip_target)

        temp_map = raw_target.with_suffix(".map.part")
        try:
            with zipfile.ZipFile(zip_target, "r") as zf:
                member = ce3_find_exact_map_member(zf, map_name)
                with zf.open(member, "r") as src, open(temp_map, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)

            if temp_map.stat().st_size < 0x800 or not raw_halo_map_signature_ok(temp_map):
                raise RuntimeError("CE3 archive contained an invalid Halo map")

            temp_map.replace(raw_target)
            return raw_target, "fallback-ce3"
        except Exception:
            if temp_map.exists():
                temp_map.unlink()
            raise

    # Raw .map
    temp_map = raw_target.with_suffix(".map.part")
    with open(temp_map, "wb") as f:
        f.write(data)

    if temp_map.stat().st_size >= 0x800 and raw_halo_map_signature_ok(temp_map):
        temp_map.replace(raw_target)
        return raw_target, "fallback-ce3"

    temp_map.unlink(missing_ok=True)

    lower_final = final_url.lower().split("?")[0]
    if lower_final.endswith(".7z") or lower_final.endswith(".rar"):
        raise RuntimeError("CE3 download is 7z/RAR; this build only auto-extracts ZIP")

    raise RuntimeError(
        f"CE3 returned unsupported data ({content_type or 'unknown content type'})"
    )

def discover_ce3_entry(map_name, opener):
    requested_key = normalize_map_key(map_name)
    cache = load_json_cache(CE3_ENTRY_CACHE)

    cached = cache.get(requested_key)
    if isinstance(cached, dict) and cached.get("url"):
        log(
            f"[FALLBACK-2] CE3 cache hit: "
            f"{cached.get('title', map_name)}"
        )
        return cached["url"], cached.get("title", map_name)

    deadline = time.monotonic() + CE3_LOOKUP_BUDGET

    def remaining():
        return deadline - time.monotonic()

    def req_timeout():
        left = remaining()
        if left <= 0:
            raise TimeoutError("CE3 lookup budget exhausted")
        return max(0.5, min(CE3_LOOKUP_TIMEOUT, left))

    search_terms = []
    for term in (
        map_name,
        map_name.replace("_", " "),
        re.sub(r"[\[\]_-]+", " ", map_name),
    ):
        term = " ".join(term.split())
        if term and term.lower() not in [x.lower() for x in search_terms]:
            search_terms.append(term)

    candidates = []
    seen_candidates = set()

    log(f"[FALLBACK-2] Searching CE3 for {map_name}")
    log(
        f"[FALLBACK-2] CE3 lookup budget: {CE3_LOOKUP_BUDGET}s "
        f"(max {CE3_LOOKUP_TIMEOUT}s/request)"
    )

    # WordPress REST search first: fast and structured when enabled.
    for term in search_terms[:2]:
        if remaining() <= 0:
            break
        try:
            url = CE3_WP_SEARCH.format(query=quote(term))
            status, content_type, final_url, data = ce3_get_bytes(
                opener, url, req_timeout()
            )
            if status >= 200 and status < 300 and "json" in (content_type or "").lower():
                results = json.loads(data.decode("utf-8", errors="replace"))
                if isinstance(results, list):
                    for item in results:
                        entry_url = item.get("url")
                        title = item.get("title", "")
                        if entry_url and "/downloads/" in entry_url:
                            key = entry_url.split("#", 1)[0]
                            if key not in seen_candidates:
                                seen_candidates.add(key)
                                candidates.append((key, html.unescape(title)))
        except Exception as e:
            log(f"[FALLBACK-2] CE3 REST search unavailable: {e}")
            break

    # Standard WordPress/search-filter pages.
    for term in search_terms:
        if remaining() <= 0:
            break
        for template in (CE3_SEARCH, CE3_FILTER_SEARCH):
            if remaining() <= 0:
                break
            try:
                url = template.format(query=quote(term))
                _, _, final_url, page_html = ce3_get_text(
                    opener, url, req_timeout()
                )

                # Cloudflare/anti-bot pages are not useful for automated lookup.
                visible = ce3_visible_text(page_html).lower()
                if "please wait while your request is being verified" in visible:
                    log("[FALLBACK-2] CE3 returned a verification page")
                    continue

                for entry_url, title in ce3_parse_entry_links(final_url, page_html):
                    if entry_url not in seen_candidates:
                        seen_candidates.add(entry_url)
                        candidates.append((entry_url, title))
            except Exception as e:
                log(f"[FALLBACK-2] CE3 search request failed: {e}")

    # Verify candidates by the actual CE3 Map Name field.
    for entry_url, title in candidates[:12]:
        if remaining() <= 0:
            break
        try:
            _, _, final_url, detail_html = ce3_get_text(
                opener, entry_url, req_timeout()
            )
            matched, names = ce3_entry_matches(map_name, detail_html, title)
            if matched:
                cache[requested_key] = {
                    "url": final_url,
                    "title": title,
                    "map_names": names,
                }
                save_json_cache(CE3_ENTRY_CACHE, cache)
                log(
                    f"[FALLBACK-2] CE3 match: "
                    f"{title or map_name} ({', '.join(names) if names else 'title match'})"
                )
                return final_url, title
        except Exception as e:
            log(f"[FALLBACK-2] CE3 candidate failed: {e}")

    # Small bounded catalog fallback. No deep crawling.
    log("[FALLBACK-2] CE3 search did not match; trying bounded category pages")
    for category_url in CE3_CATEGORY_URLS:
        if remaining() <= 0:
            break
        try:
            _, _, final_url, page_html = ce3_get_text(
                opener, category_url, req_timeout()
            )
            for entry_url, title in ce3_parse_entry_links(final_url, page_html):
                if remaining() <= 0:
                    break
                if entry_url in seen_candidates:
                    continue
                seen_candidates.add(entry_url)
                try:
                    _, _, detail_final, detail_html = ce3_get_text(
                        opener, entry_url, req_timeout()
                    )
                    matched, names = ce3_entry_matches(
                        map_name, detail_html, title
                    )
                    if matched:
                        cache[requested_key] = {
                            "url": detail_final,
                            "title": title,
                            "map_names": names,
                        }
                        save_json_cache(CE3_ENTRY_CACHE, cache)
                        log(
                            f"[FALLBACK-2] CE3 catalog match: "
                            f"{title or map_name}"
                        )
                        return detail_final, title
                except Exception:
                    continue
        except Exception as e:
            log(f"[FALLBACK-2] CE3 category request failed: {e}")

    raise RuntimeError(
        f"CE3 could not locate '{map_name}' within {CE3_LOOKUP_BUDGET}s"
    )

def try_ce3_fallback(map_name):
    progress_stage("Searching CE3", source="CE3", track_bytes=False, reset_transfer=True)
    raw_map = CE3_RAW_CACHE_DIR / f"{safe_filename(map_name)}.map"
    if (
        raw_map.exists()
        and raw_map.stat().st_size >= 0x800
        and raw_halo_map_signature_ok(raw_map)
    ):
        log(f"[FALLBACK-2] CE3 raw cache hit: {map_name}")
        return raw_map, "fallback-ce3-cache"

    opener = ce3_session()
    detail_url, title = discover_ce3_entry(map_name, opener)

    log(f"[FALLBACK-2] Opening CE3 entry: {title or detail_url}")
    _, _, final_detail, detail_html = ce3_get_text(
        opener, detail_url, CE3_LOOKUP_TIMEOUT
    )

    matched, map_names = ce3_entry_matches(map_name, detail_html, title)
    if not matched:
        # Stale cache or page changed.
        cache = load_json_cache(CE3_ENTRY_CACHE)
        cache.pop(normalize_map_key(map_name), None)
        save_json_cache(CE3_ENTRY_CACHE, cache)
        raise RuntimeError("CE3 cached entry no longer matches requested map")

    links = ce3_extract_download_links(final_detail, detail_html, map_name)
    if not links:
        raise RuntimeError("CE3 entry has no detectable Download link")

    log(f"[FALLBACK-2] CE3 found {len(links)} download candidate(s)")

    # Follow a bounded chain of HTML landing pages (e.g. an external mirror).
    queue = [(url, label, final_detail, 0) for url, label in links[:8]]
    visited = set()
    errors = []

    while queue:
        url, label, referer, depth = queue.pop(0)
        if depth > 2 or url in visited:
            continue
        visited.add(url)

        # If CE3 simply points to HaloMaps, let the dedicated HaloMaps
        # fallback handle it rather than scraping it twice here.
        host = urlparse(url).netloc.lower()
        if host.endswith("halomaps.org"):
            errors.append(f"{url}: points to HaloMaps; deferred")
            continue

        try:
            progress_stage("Downloading", source="CE3", track_bytes=True, reset_transfer=True)
            log(
                f"[FALLBACK-2] CE3 download: "
                f"{label or '(unlabelled)'} -> {url}"
            )
            status, content_type, final_url, data = ce3_get_bytes(
                opener, url, CE3_DOWNLOAD_TIMEOUT, referer=referer
            )

            if status < 200 or status >= 300:
                errors.append(f"{url}: HTTP {status}")
                continue

            if looks_like_html(data[:4096], content_type):
                try:
                    page_html = data.decode("utf-8", errors="replace")
                    next_links = ce3_extract_download_links(
                        final_url, page_html, map_name
                    )
                    for next_url, next_label in next_links[:6]:
                        queue.append(
                            (next_url, next_label, final_url, depth + 1)
                        )
                except Exception as e:
                    errors.append(f"{url}: HTML landing page parse failed: {e}")
                continue

            result = ce3_save_payload(
                data, content_type, final_url, map_name
            )
            path, _ = result
            log(
                f"[FALLBACK-2] CE3 success "
                f"({path.stat().st_size / 1024 / 1024:.1f} MiB)"
            )
            return result

        except Exception as e:
            errors.append(f"{url}: {e}")

    if errors:
        raise RuntimeError(
            "CE3 entry found but download failed. Last errors: "
            + " | ".join(errors[-5:])
        )

    raise RuntimeError("CE3 entry found but no usable map download was produced")

def normalize_map_key(name):
    """Normalize Chimera/internal names and HaloMaps display titles for matching."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())

def load_halomaps_fid_cache():
    try:
        if HALOMAPS_FID_CACHE.exists():
            data = json.loads(HALOMAPS_FID_CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_halomaps_fid_cache(data):
    try:
        HALOMAPS_FID_CACHE.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception as e:
        log(f"[FALLBACK-3] Warning: could not save FID cache: {e}")

class HaloMapsLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self._href = attrs.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            title = " ".join("".join(self._text).split())
            self.links.append((self._href, title))
            self._href = None
            self._text = []

class HaloMapsFormParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.current = None
        self.current_button = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()

        if tag == "form":
            self.current = {
                "action": attrs.get("action", ""),
                "method": attrs.get("method", "GET").upper(),
                "fields": [],
                "button_text": [],
            }

        elif self.current is not None and tag == "input":
            name = attrs.get("name")
            if name:
                input_type = attrs.get("type", "text").lower()
                value = attrs.get("value", "")
                # Submit inputs matter because the server may branch on the button value.
                if input_type in ("hidden", "text", "search", "submit"):
                    self.current["fields"].append((name, value))
                    if input_type == "submit":
                        self.current["button_text"].append(value)

        elif self.current is not None and tag == "button":
            self.current_button = {
                "name": attrs.get("name"),
                "value": attrs.get("value", ""),
                "text": [],
            }

    def handle_data(self, data):
        if self.current_button is not None:
            self.current_button["text"].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "button" and self.current_button is not None and self.current is not None:
            text = " ".join("".join(self.current_button["text"]).split())
            if self.current_button["name"]:
                self.current["fields"].append(
                    (self.current_button["name"], self.current_button["value"] or text)
                )
            self.current["button_text"].append(text)
            self.current_button = None

        elif tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None
            self.current_button = None

def halomaps_session():
    return build_opener(HTTPCookieProcessor(CookieJar()))

def opener_get_bytes(opener, url, timeout=HALOMAPS_LOOKUP_TIMEOUT, referer=None):
    headers = {
        "User-Agent": "Chimera-Hybrid-Map-Downloader/3.6",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer

    req = Request(url, headers=headers)
    socket_timeout = min(max(0.5, timeout), NETWORK_STALL_TIMEOUT)

    with opener.open(req, timeout=socket_timeout) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        data = read_response_bounded(
            response,
            timeout,
            label="HaloMaps request",
        )

    return status, content_type, final_url, data

def opener_get_text(opener, url, timeout=HALOMAPS_LOOKUP_TIMEOUT, referer=None):
    status, content_type, final_url, data = opener_get_bytes(
        opener, url, timeout, referer
    )
    encoding = "utf-8"
    m = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if m:
        encoding = m.group(1).strip("'\"")
    try:
        body = data.decode(encoding, errors="replace")
    except Exception:
        body = data.decode("utf-8", errors="replace")
    return status, content_type, final_url, body

def parse_halomaps_catalog_entries(page_url, html_text):
    parser = HaloMapsLinkParser()
    parser.feed(html_text)

    entries = []
    for href, title in parser.links:
        absolute = urljoin(page_url, html.unescape(href or ""))
        m = re.search(r"(?:detail\.cfm|index\.cfm)\?fid=(\d+)", absolute, re.I)
        if m and title:
            entries.append({
                "fid": m.group(1),
                "title": title,
                "url": HALOMAPS_DETAIL_BASE.format(fid=m.group(1)),
            })
    return entries

def discover_halomaps_detail(map_name, opener):
    requested_key = normalize_map_key(map_name)
    cache = load_halomaps_fid_cache()

    cached = cache.get(requested_key)
    if cached:
        fid = str(cached.get("fid", cached) if isinstance(cached, dict) else cached)
        title = cached.get("title", map_name) if isinstance(cached, dict) else map_name
        log(f"[FALLBACK-3] FID cache hit: {title} (fid={fid})")
        return HALOMAPS_DETAIL_BASE.format(fid=fid), title, fid

    deadline = time.monotonic() + HALOMAPS_LOOKUP_BUDGET

    def remaining():
        return deadline - time.monotonic()

    def request_timeout():
        left = remaining()
        if left <= 0:
            raise TimeoutError(
                f"HaloMaps lookup exceeded {HALOMAPS_LOOKUP_BUDGET}s budget"
            )
        return max(0.5, min(HALOMAPS_LOOKUP_TIMEOUT, left))

    log(f"[FALLBACK-3] Searching HaloMaps for {map_name}")
    log(
        f"[FALLBACK-3] Lookup budget: {HALOMAPS_LOOKUP_BUDGET}s "
        f"(max {HALOMAPS_LOOKUP_TIMEOUT}s per request)"
    )

    # Try several sensible search strings. HaloMaps historically accepted
    # search=<text>&B1=Search. Current versions may process it as POST.
    search_terms = []
    for term in (
        map_name.replace("_", " "),
        re.sub(r"[\[\]_-]+", " ", map_name),
        re.sub(r"[^A-Za-z0-9.]+", " ", map_name),
    ):
        term = " ".join(term.split())
        if term and term.lower() not in [x.lower() for x in search_terms]:
            search_terms.append(term)

    for search_term in search_terms:
        if remaining() <= 0:
            break

        try:
            post_data = urlencode({
                "search": search_term,
                "B1": "Search",
            }).encode("utf-8")

            req = Request(
                HALOMAPS_INDEX,
                data=post_data,
                headers={
                    "User-Agent": "Chimera-Hybrid-Map-Downloader/3.6",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "text/html,*/*",
                    "Referer": HALOMAPS_INDEX,
                },
                method="POST",
            )

            log(f"[FALLBACK-3] Site search: {search_term}")

            current_timeout = request_timeout()
            with opener.open(
                req,
                timeout=min(current_timeout, NETWORK_STALL_TIMEOUT),
            ) as response:
                page_url = response.geturl()
                body = read_response_bounded(
                    response,
                    current_timeout,
                    label="HaloMaps search",
                ).decode("utf-8", errors="replace")

            entries = parse_halomaps_catalog_entries(page_url, body)

            if "no records found" in body.lower():
                log(f"[FALLBACK-3] HaloMaps returned no records for: {search_term}")

            exact = [
                e for e in entries
                if normalize_map_key(e["title"]) == requested_key
            ]

            if exact:
                found = exact[0]
                cache[requested_key] = {
                    "fid": found["fid"],
                    "title": found["title"],
                }
                save_halomaps_fid_cache(cache)
                log(
                    f"[FALLBACK-3] Matched search result: "
                    f"{found['title']} (fid={found['fid']})"
                )
                return found["url"], found["title"], found["fid"]

            # Loose match for cases such as:
            # sidewinder_2.0 -> Sidewinder 2.0
            loose = []
            for entry in entries:
                ek = normalize_map_key(entry["title"])
                if requested_key in ek or ek in requested_key:
                    loose.append(entry)

            if len(loose) == 1:
                found = loose[0]
                cache[requested_key] = {
                    "fid": found["fid"],
                    "title": found["title"],
                }
                save_halomaps_fid_cache(cache)
                log(
                    f"[FALLBACK-3] Matched search result: "
                    f"{found['title']} (fid={found['fid']})"
                )
                return found["url"], found["title"], found["fid"]

        except TimeoutError:
            break
        except Exception as e:
            log(f"[FALLBACK-3] Search request failed: {e}")

    # Do a SMALL bounded catalog fallback. Older v3.1 builds attempted
    # hundreds/thousands of catalog requests and appeared to hang.
    log("[FALLBACK-3] Search did not match; trying bounded catalog lookup")

    catalog_requests = 0
    MAX_CATALOG_REQUESTS = 8

    # Multiplayer sections first because Chimera auto-downloads are normally
    # encountered when joining multiplayer servers.
    category_order = [24, 10, 39, 29, 40, 41, 27, 35, 37]

    for sid in category_order:
        if remaining() <= 0 or catalog_requests >= MAX_CATALOG_REQUESTS:
            break

        # Only inspect the first alphabetical page for each category during
        # this fail-fast fallback. We deliberately do NOT deep-crawl.
        page_url = f"{HALOMAPS_INDEX}?sid={sid}&sort=6"

        try:
            timeout = request_timeout()
            catalog_requests += 1
            log(
                f"[FALLBACK-3] Catalog check {catalog_requests}/"
                f"{MAX_CATALOG_REQUESTS}: sid={sid}"
            )
            _, _, final_url, page_html = opener_get_text(
                opener, page_url, timeout=timeout
            )
            entries = parse_halomaps_catalog_entries(final_url, page_html)

            for entry in entries:
                entry_key = normalize_map_key(entry["title"])
                if entry_key == requested_key:
                    cache[requested_key] = {
                        "fid": entry["fid"],
                        "title": entry["title"],
                    }
                    save_halomaps_fid_cache(cache)
                    log(
                        f"[FALLBACK-3] Matched catalog title: "
                        f"{entry['title']} (fid={entry['fid']}, sid={sid})"
                    )
                    return entry["url"], entry["title"], entry["fid"]

        except TimeoutError:
            break
        except Exception as e:
            log(f"[FALLBACK-3] Catalog sid={sid} failed: {e}")

    elapsed = HALOMAPS_LOOKUP_BUDGET - max(0, remaining())
    raise RuntimeError(
        f"HaloMaps could not locate '{map_name}' within "
        f"{min(elapsed, HALOMAPS_LOOKUP_BUDGET):.1f}s; giving up instead of hanging"
    )

def extract_download_actions(page_url, page_html):
    actions = []

    # Direct file links and obvious download links.
    link_parser = HaloMapsLinkParser()
    link_parser.feed(page_html)
    for href, title in link_parser.links:
        if not href:
            continue
        absolute = urljoin(page_url, html.unescape(href))
        haystack = (absolute + " " + title).lower()
        if (
            "download" in haystack
            or "dl.cfm" in haystack
            or re.search(r"\.(zip|map)(?:$|\?)", absolute, re.I)
        ):
            actions.append(("GET", absolute, None))

    # Submit the actual download form rather than guessing endpoints.
    form_parser = HaloMapsFormParser()
    form_parser.feed(page_html)
    for form in form_parser.forms:
        descriptor = (
            form.get("action", "")
            + " "
            + " ".join(form.get("button_text", []))
            + " "
            + " ".join(f"{k}={v}" for k, v in form.get("fields", []))
        ).lower()

        if "download" not in descriptor and "dl." not in descriptor and "fid" not in descriptor:
            continue

        action_url = urljoin(page_url, html.unescape(form.get("action") or page_url))
        fields = list(form.get("fields", []))
        actions.append((form.get("method", "GET").upper(), action_url, fields))

    # Deduplicate.
    seen = set()
    result = []
    for method, url, fields in actions:
        key = (method, url, tuple(fields or []))
        if key not in seen:
            seen.add(key)
            result.append((method, url, fields))
    return result

def request_halomaps_action(opener, method, url, fields, referer):
    headers = {
        "User-Agent": "Chimera-Hybrid-Map-Downloader/3.6",
        "Accept": "*/*",
        "Referer": referer,
    }

    if method == "POST":
        payload = urlencode(fields or []).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = Request(url, data=payload, headers=headers, method="POST")
    else:
        if fields:
            sep = "&" if "?" in url else "?"
            url = url + sep + urlencode(fields)
        req = Request(url, headers=headers, method="GET")

    with opener.open(
        req,
        timeout=min(HALOMAPS_DOWNLOAD_TIMEOUT, NETWORK_STALL_TIMEOUT),
    ) as response:
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        data = read_response_bounded(
            response,
            HALOMAPS_DOWNLOAD_TIMEOUT,
            label="HaloMaps download",
        )

    return status, content_type, final_url, data

def save_halomaps_payload(data, content_type, final_url, map_name):
    safe = safe_filename(map_name)
    raw_target = HALOMAPS_RAW_CACHE_DIR / f"{safe}.map"
    zip_target = HALOMAPS_ZIP_CACHE_DIR / f"{safe}.zip"

    if looks_like_zip(data[:16], content_type) or final_url.lower().split("?")[0].endswith(".zip"):
        temp = zip_target.with_suffix(".zip.part")
        with open(temp, "wb") as f:
            f.write(data)
        temp.replace(zip_target)
        progress_stage("Extracting map", source="CE3", track_bytes=False)
        progress_stage("Extracting map", source="HaloMaps.org", track_bytes=False)
        raw = extract_map_from_zip(zip_target, map_name, raw_target)
        return raw, "fallback-halomaps"

    # Some mirrors may serve a raw map.
    temp_map = raw_target.with_suffix(".map.part")
    with open(temp_map, "wb") as f:
        f.write(data)

    if temp_map.stat().st_size >= 0x800 and raw_halo_map_signature_ok(temp_map):
        temp_map.replace(raw_target)
        return raw_target, "fallback-halomaps"

    temp_map.unlink(missing_ok=True)
    raise RuntimeError(
        f"HaloMaps returned unsupported data ({content_type or 'unknown content type'})"
    )

def try_halomaps_fallback(map_name):
    progress_stage("Searching HaloMaps", source="HaloMaps.org", track_bytes=False, reset_transfer=True)
    raw_map = HALOMAPS_RAW_CACHE_DIR / f"{safe_filename(map_name)}.map"
    if (
        raw_map.exists()
        and raw_map.stat().st_size >= 0x800
        and raw_halo_map_signature_ok(raw_map)
    ):
        log(f"[FALLBACK-3] HaloMaps raw cache hit: {map_name}")
        return raw_map, "fallback-halomaps-cache"

    opener = halomaps_session()
    detail_url, display_title, fid = discover_halomaps_detail(map_name, opener)

    log(f"[FALLBACK-3] Opening HaloMaps: {display_title} (fid={fid})")
    _, _, final_detail_url, detail_html = opener_get_text(opener, detail_url, timeout=HALOMAPS_LOOKUP_TIMEOUT)

    # Follow download forms/links. If the first action returns another HTML
    # interstitial, parse it again (HaloMaps historically generated signed
    # mirror URLs after pressing Download).
    queue = [(final_detail_url, detail_html, 0)]
    visited_pages = set()
    errors = []

    while queue:
        page_url, page_html, depth = queue.pop(0)
        if depth > 3 or page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        actions = extract_download_actions(page_url, page_html)
        log(f"[FALLBACK-3] Found {len(actions)} download action(s) on page")

        for method, action_url, fields in actions:
            try:
                progress_stage("Downloading", source="HaloMaps.org", track_bytes=True, reset_transfer=True)
                log(f"[FALLBACK-3] {method} {action_url}")
                status, content_type, final_url, data = request_halomaps_action(
                    opener, method, action_url, fields, page_url
                )

                if status < 200 or status >= 300:
                    errors.append(f"{action_url}: HTTP {status}")
                    continue

                if looks_like_html(data[:4096], content_type):
                    encoding = "utf-8"
                    m = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
                    if m:
                        encoding = m.group(1).strip("'\"")
                    next_html = data.decode(encoding, errors="replace")
                    queue.append((final_url, next_html, depth + 1))
                    continue

                result = save_halomaps_payload(
                    data, content_type, final_url, map_name
                )
                path, _ = result
                log(
                    f"[FALLBACK-3] Success via HaloMaps "
                    f"({path.stat().st_size / 1024 / 1024:.1f} MiB)"
                )
                return result

            except Exception as e:
                errors.append(f"{action_url}: {e}")

    if errors:
        raise RuntimeError(
            "HaloMaps entry was found, but download failed. Last errors: "
            + " | ".join(errors[-5:])
        )

    raise RuntimeError(
        "HaloMaps entry was found, but no usable Download form/link was detected"
    )

def resolve_map(map_name):
    map_name = validate_map_name(map_name)

    with map_lock(map_name):
        # Normal HaloNet path: NO custom popup. Chimera already displays
        # native progress when this route works.
        primary_path, method = try_primary(map_name)
        if primary_path is not None:
            return primary_path, method

        # Native locator failed. From this point onward users would otherwise
        # sit on "Connecting to map server...", so activate our own progress UI.
        progress_begin(map_name, "HaloNet ZIP", "Checking fallback sources")

        try:
            try:
                log(f"[FALLBACK-1] Using HaloNet static ZIP for {map_name}")
                result = try_static_zip_fallback(map_name)
                progress_complete("Complete - handing map to Halo")
                return result
            except Exception as e:
                log(f"[FALLBACK-1] Failed: {e}")

            try:
                progress_stage("Searching CE3", source="CE3", track_bytes=False, reset_transfer=True)
                log(f"[FALLBACK-2] Trying CE3 for {map_name}")
                result = try_ce3_fallback(map_name)
                progress_complete("Complete - handing map to Halo")
                return result
            except Exception as e:
                log(f"[FALLBACK-2] Failed: {e}")

            progress_stage("Searching HaloMaps", source="HaloMaps.org", track_bytes=False, reset_transfer=True)
            log(f"[FALLBACK-3] Trying HaloMaps.org for {map_name}")
            result = try_halomaps_fallback(map_name)
            progress_complete("Complete - handing map to Halo")
            return result

        except Exception as e:
            progress_error("Map unavailable")
            raise

def resolve_map_with_watchdog(map_name):
    """
    Absolute final safety net.

    Network libraries can occasionally get stuck below Python's normal socket
    timeout (DNS/OS/TLS edge cases). Run the resolver in a daemon thread and
    stop making Chimera wait after REQUEST_WATCHDOG_TIMEOUT seconds.
    """
    result_queue = queue.Queue(maxsize=1)

    def worker():
        try:
            result_queue.put(("ok", resolve_map(map_name)))
        except BaseException as e:
            try:
                result_queue.put(("error", e))
            except Exception:
                pass

    thread = threading.Thread(
        target=worker,
        name=f"map-resolver-{map_name}",
        daemon=True,
    )
    thread.start()

    try:
        status, value = result_queue.get(timeout=REQUEST_WATCHDOG_TIMEOUT)
    except queue.Empty:
        raise TimeoutError(
            f"map lookup exceeded hard {REQUEST_WATCHDOG_TIMEOUT}s watchdog; "
            f"aborting request instead of hanging"
        )

    if status == "ok":
        return value

    raise value

class Handler(BaseHTTPRequestHandler):
    server_version = "ChimeraHybridMapDownloader/3.6"
    def log_message(self, fmt, *args):
        log("[HTTP] " + (fmt % args))
    def requested_map(self):
        path = unquote(urlparse(self.path).path).strip("/")
        if path.lower().endswith(".map"):
            path = path[:-4]
        return validate_map_name(path)
    def serve_map(self, send_body):
        response_started = False

        try:
            map_name = self.requested_map()

            log("")
            log("=" * 70)
            log(f"[REQUEST] Chimera requested: {map_name}")

            payload, method = resolve_map_with_watchdog(map_name)
            size = payload.stat().st_size

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Chimera-Download-Method", method)
            self.end_headers()
            response_started = True

            if send_body:
                # Localhost should never need long blocking writes. If Chimera
                # cancels/disconnects, stop this handler instead of hanging it.
                try:
                    self.connection.settimeout(LOCAL_CLIENT_TIMEOUT)
                except Exception:
                    pass

                with open(payload, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)

            log(f"[DONE] Served {map_name} via {method}")

        except TimeoutError as e:
            log(f"[TIMEOUT] {e}")
            if not response_started:
                try:
                    self.send_error(504, str(e))
                except Exception:
                    pass

        except HTTPError as e:
            log(f"[ERROR] Upstream HTTP {e.code}: {e.reason}")
            if not response_started:
                self.send_error(502, f"Map source returned HTTP {e.code}")

        except URLError as e:
            log(f"[ERROR] Network error: {e}")
            if not response_started:
                self.send_error(502, "Could not reach map source")

        except (ValueError, RuntimeError, zipfile.BadZipFile) as e:
            log(f"[ERROR] {e}")
            if not response_started:
                self.send_error(404, str(e))

        except (BrokenPipeError, ConnectionResetError):
            log("[HTTP] Client disconnected")

        except Exception as e:
            log(f"[ERROR] Unexpected {type(e).__name__}: {e}")
            if not response_started:
                try:
                    self.send_error(500, "Local downloader error")
                except Exception:
                    pass

    def do_GET(self):
        self.serve_map(True)
    def do_HEAD(self):
        self.serve_map(False)

def print_banner():
    print()
    print("=" * 70)
    print("  Chimera Hybrid Map Downloader v3.6")
    print("=" * 70)
    print(f"  Local address: http://{HOST}:{PORT}/")
    print()
    print("  Priority order:")
    print("  1. HaloNet normal locator.php (.inv/raw)")
    print("  2. HaloNet static ZIP fallback")
    print("  3. CE3 archive fallback")
    print("  4. HaloMaps.org catalog + download-form fallback")
    print()
    print("  chimera.ini setting:")
    print(f"  download_template=http://{HOST}:{PORT}/{{map}}")
    print()
    print("  Anti-hang protection:")
    print(f"  - Network stall timeout: {NETWORK_STALL_TIMEOUT}s")
    print(f"  - File transfer budget: {UPSTREAM_FILE_BUDGET}s/source (5 minutes)")
    print(f"  - Hard request watchdog: {REQUEST_WATCHDOG_TIMEOUT}s")
    print()
    print("  Leave this window open while Halo Custom Edition is running.")
    print("  Press Ctrl+C to stop.")
    print("=" * 70)
    print()

def main():
    print_banner()
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        print(f"Could not bind to {HOST}:{PORT}: {e}")
        print("Another copy may already be running.")
        input("Press Enter to exit...")
        return 1
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Chimera Hybrid Map Downloader...")
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
