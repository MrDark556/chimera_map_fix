#!/usr/bin/env python3
"""
Update the exact HaloNet static ZIP filename cache.

This script uses only the Python standard library.

It downloads HaloNet's full map listing and extracts the exact filename from
every /maps/<name>.zip link. The resulting JSON is case-insensitive for lookup
while preserving the exact capitalization needed by HaloNet's static server.
"""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import Request, urlopen
from datetime import datetime, timezone
import html
import json
import re
import sys

OUTPUT = Path(__file__).resolve().parent / "halonet_map_index.json"

SOURCE_URLS = [
    "https://maps.halonet.net/maplist.php?fulllist=y",
    "https://maps.halonet.net/index.php?fulllist=y",
]

# Jina Reader is only a maintenance fallback. It fetches the official HaloNet
# page from outside the local region and normally preserves the ZIP links.
JINA_SOURCE_URLS = [
    "https://r.jina.ai/https://maps.halonet.net/maplist.php?fulllist=y",
    "https://r.jina.ai/https://maps.halonet.net/index.php?fulllist=y",
]

MIN_EXPECTED_FILENAMES = 5000
USER_AGENT = (
    "Mozilla/5.0 (compatible; Chimera-Hybrid-Map-Downloader-Cache-Updater/1.0)"
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)
                break


def filename_stem_from_url(value):
    value = html.unescape(str(value).strip())
    try:
        parsed = urlparse(value)
        path = unquote(parsed.path)
    except Exception:
        return None

    path_lower = path.lower()
    if "/maps/" not in path_lower or not path_lower.endswith(".zip"):
        return None

    filename = path.rsplit("/", 1)[-1]
    if len(filename) <= 4:
        return None

    return filename[:-4]


def extract_from_html(text):
    parser = LinkParser()
    parser.feed(text)

    names = []
    seen = set()

    for href in parser.hrefs:
        stem = filename_stem_from_url(href)
        if stem and stem not in seen:
            seen.add(stem)
            names.append(stem)

    return names


def extract_from_markdown(text):
    # Jina markdown normally keeps destination URLs in (...) form. Also accept
    # bare URLs to make this tolerant of output-format changes.
    url_pattern = re.compile(
        r"https?://maps\.halonet\.net/maps/[^\s\)\]<>\"']+?\.zip",
        flags=re.IGNORECASE,
    )

    names = []
    seen = set()

    for match in url_pattern.findall(text):
        stem = filename_stem_from_url(match)
        if stem and stem not in seen:
            seen.add(stem)
            names.append(stem)

    return names


def fetch_text(url, timeout=90):
    print(f"Fetching: {url}")
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        print(f"  HTTP {getattr(response, 'status', 200)} "
              f"({len(raw):,} bytes; {content_type})")
        return raw.decode("utf-8", errors="replace")


def fetch_names():
    errors = []

    for url in SOURCE_URLS:
        try:
            text = fetch_text(url)
            names = extract_from_html(text)
            print(f"  Found {len(names):,} ZIP filenames")
            if len(names) >= MIN_EXPECTED_FILENAMES:
                return url, names
            errors.append(
                f"{url}: only {len(names)} ZIP links were found"
            )
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")

    for url in JINA_SOURCE_URLS:
        try:
            text = fetch_text(url)
            names = extract_from_markdown(text)
            print(f"  Found {len(names):,} ZIP filenames through reader")
            if len(names) >= MIN_EXPECTED_FILENAMES:
                return url, names
            errors.append(
                f"{url}: only {len(names)} ZIP links were found"
            )
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")

    raise RuntimeError(
        "Could not retrieve a complete HaloNet map list.\n\n"
        + "\n".join(" - " + item for item in errors)
    )


def build_index(names):
    index = {}
    for exact_name in names:
        key = exact_name.casefold()
        values = index.setdefault(key, [])
        if exact_name not in values:
            values.append(exact_name)

    # Stable ordering makes Git diffs clean.
    return {
        key: values
        for key, values in sorted(index.items(), key=lambda item: item[0])
    }


def existing_payload():
    if not OUTPUT.exists():
        return None
    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    source, names = fetch_names()
    index = build_index(names)

    old = existing_payload()
    if (
        isinstance(old, dict)
        and old.get("complete") is True
        and old.get("index") == index
    ):
        print(
            f"No changes: existing cache already contains "
            f"{len(names):,} exact filenames."
        )
        return 0

    payload = {
        "format_version": 1,
        "complete": True,
        "source": source,
        "generated_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        "map_count": len(names),
        "key_count": len(index),
        "index": index,
    }

    temp = OUTPUT.with_suffix(".json.tmp")
    with open(temp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        f.write("\n")

    temp.replace(OUTPUT)

    print(
        f"Wrote {OUTPUT.name}: {len(names):,} exact filenames, "
        f"{len(index):,} case-insensitive keys."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
