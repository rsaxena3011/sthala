#!/usr/bin/env python3
"""
harvest.py — pull candidate stops from OpenStreetMap + Wikipedia article text.

For each demo area it:
  1. Queries the Overpass API for forts, Hindu temples, and tanks/ponds
     that carry a `wikipedia` tag (so every stop has a citable source).
  2. Resolves each wikipedia tag via the MediaWiki API: canonical URL,
     coordinates (used to verify/override the OSM position), and the
     plain-text article extract in English + Hindi.
  3. Writes packs/<pack>/stops.json and packs/<pack>/sources.md.

If Overpass is unreachable, it falls back to a hardcoded stop list whose
coordinates are verified against the Wikipedia API response.

Usage:
    python3 harvest.py --pack mumbai-demo
    python3 harvest.py --pack mumbai-demo --areas sewri,banganga --radius 35

Zero marginal cost: Overpass + MediaWiki APIs are free, no keys needed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# Demo areas (Mumbai). Coordinates are approximate centers; per-stop positions
# come from OSM/Wikipedia and are verified, not from these centers.
# ----------------------------------------------------------------------------
AREAS = {
    "sewri": {
        "label": "Sewri Fort / Sewri jetty",
        "lat": 19.0000,
        "lon": 72.8670,
        "radius_m": 1500,
    },
    "banganga": {
        "label": "Banganga - Walkeshwar",
        "lat": 18.9450,
        "lon": 72.7950,
        "radius_m": 1500,
    },
}

# Fallback stops if Overpass is down: (area, wikipedia tag, default radius_m).
# Coordinates are NOT trusted from here — they are resolved via Wikipedia.
FALLBACK_STOPS = [
    ("sewri", "en:Sewri Fort", 40),
    ("banganga", "en:Banganga Tank", 35),
    ("banganga", "en:Walkeshwar Temple", 35),
]

OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

HEADERS = {"User-Agent": "Sthala/0.1 (DEV Hacktoberfest Week 1; contact: local build)"}
HTTP_TIMEOUT = 30


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "stop"


def http_get(session: requests.Session, url: str, params: dict, tries: int = 3):
    """GET with retries on 429/5xx. Raises on final failure."""
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            resp = session.get(url, params=params, timeout=HTTP_TIMEOUT)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # noqa: BLE001 - retried below
            last_exc = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed after {tries} tries: {url} ({last_exc})")


def http_post(session: requests.Session, url: str, data: dict, tries: int = 2):
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            resp = session.post(url, data=data, timeout=90)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"POST failed after {tries} tries: {url} ({last_exc})")


# ----------------------------------------------------------------------------
# Overpass
# ----------------------------------------------------------------------------
def overpass_query(session: requests.Session, lat: float, lon: float, radius_m: int) -> list[dict]:
    """Return OSM elements (forts, temples, tanks) with a wikipedia tag."""
    ql = f"""
    [out:json][timeout:60];
    (
      nwr["historic"="fort"](around:{radius_m},{lat},{lon});
      nwr["historic"="castle"](around:{radius_m},{lat},{lon});
      nwr["amenity"="place_of_worship"]["religion"="hindu"](around:{radius_m},{lat},{lon});
      nwr["building"="temple"](around:{radius_m},{lat},{lon});
      nwr["natural"="water"]["name"~"Tank|Talao|Talaav",i](around:{radius_m},{lat},{lon});
    );
    out center tags;
    """
    last_err: Exception | None = None
    for base in OVERPASS_URLS:
        try:
            resp = http_post(session, base, {"data": ql})
            elements = resp.json().get("elements", [])
            return [e for e in elements if e.get("tags", {}).get("wikipedia")]
        except Exception as exc:  # noqa: BLE001 - try next mirror
            last_err = exc
            print(f"  overpass mirror failed ({base}): {exc}", file=sys.stderr)
    raise RuntimeError(f"All Overpass mirrors failed (last: {last_err})")


# ----------------------------------------------------------------------------
# Wikipedia
# ----------------------------------------------------------------------------
def parse_wiki_tag(tag: str) -> tuple[str, str]:
    """'en:Sewri Fort' -> ('en', 'Sewri Fort'); 'Sewri Fort' -> ('en', ...)."""
    if ":" in tag:
        lang, title = tag.split(":", 1)
        lang = lang.strip().lower() or "en"
    else:
        lang, title = "en", tag
    return lang, title.strip().replace(" ", "_")


def wiki_page(session: requests.Session, lang: str, title: str) -> dict | None:
    """Fetch extract + coordinates + canonical URL. None if missing."""
    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts|coordinates|info",
        "inprop": "url",
        "explaintext": 1,
        "exsectionformat": "plain",
        "titles": title,
        "format": "json",
        "formatversion": 2,
    }
    try:
        data = http_get(session, api, params).json()
    except RuntimeError as exc:
        print(f"  wikipedia fetch failed ({lang}:{title}): {exc}", file=sys.stderr)
        return None
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    coords = (page.get("coordinates") or [{}])[0]
    return {
        "title": page.get("title"),
        "url": page.get("fullurl"),
        "extract": (page.get("extract") or "")[:4000],
        "lat": coords.get("lat"),
        "lon": coords.get("lon"),
    }


def wiki_hindi_title(session: requests.Session, en_title: str) -> str | None:
    """Follow langlinks from the English article to the Hindi title, if any."""
    api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "langlinks",
        "lllang": "hi",
        "titles": en_title,
        "format": "json",
        "formatversion": 2,
    }
    try:
        data = http_get(session, api, params).json()
    except RuntimeError:
        return None
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return None
    links = pages[0].get("langlinks") or []
    return links[0].get("title") if links else None


# ----------------------------------------------------------------------------
# Stop assembly
# ----------------------------------------------------------------------------
def build_stop(
    session: requests.Session,
    area_key: str,
    name_hint: str,
    wiki_tag: str,
    radius_m: int,
    osm_element: dict | None,
) -> dict | None:
    lang, title = parse_wiki_tag(wiki_tag)
    en_title = title if lang == "en" else None
    if lang != "en":
        # Resolve via langlinks in the other direction is complex; keep tag lang
        # for the primary fetch and still try English separately.
        en_page = None
    else:
        en_page = wiki_page(session, "en", title)
        en_title = title

    if en_page is None and lang == "en":
        print(f"  skip: en article missing for {wiki_tag}", file=sys.stderr)
        return None

    # Hindi: same title on hi.wikipedia, else follow langlinks from en.
    hi_page = None
    if en_title:
        hi_title = wiki_hindi_title(session, en_title)
        if hi_title:
            hi_page = wiki_page(session, "hi", hi_title)
    if hi_page is None and lang == "hi":
        hi_page = wiki_page(session, "hi", title)

    # Coordinates: prefer Wikipedia-verified, fall back to OSM center.
    lat = lon = None
    coord_source = None
    if en_page and en_page.get("lat") is not None:
        lat, lon, coord_source = en_page["lat"], en_page["lon"], "wikipedia"
    elif osm_element:
        tags = osm_element.get("tags", {})
        if "lat" in osm_element:
            lat, lon = osm_element["lat"], osm_element.get("lon")
        elif "center" in osm_element:
            lat, lon = osm_element["center"]["lat"], osm_element["center"]["lon"]
        if lat is not None:
            coord_source = "osm"

    name = (en_page or {}).get("title") or name_hint
    stop_id = f"{area_key}-{slugify(name)}"

    return {
        "id": stop_id,
        "name": name,
        "area": area_key,
        "lat": lat,
        "lon": lon,
        "coord_source": coord_source,
        "radius_m": radius_m,
        "osm": (
            {
                "type": osm_element.get("type"),
                "id": osm_element.get("id"),
                "tags": {
                    k: v
                    for k, v in osm_element.get("tags", {}).items()
                    if k in ("name", "historic", "amenity", "religion",
                             "building", "natural", "wikipedia")
                },
            }
            if osm_element
            else None
        ),
        "wikipedia": {
            "en": (en_page or {}).get("url"),
            "hi": (hi_page or {}).get("url"),
        },
        "excerpt_en": (en_page or {}).get("extract") or "",
        "excerpt_hi": (hi_page or {}).get("extract") or "",
    }


def harvest_area(
    session: requests.Session, area_key: str, area: dict, radius_m: int
) -> list[dict]:
    print(f"[{area_key}] {area['label']} — querying Overpass...")
    try:
        elements = overpass_query(session, area["lat"], area["lon"], area["radius_m"])
    except RuntimeError as exc:
        print(f"  Overpass unavailable, using fallback list: {exc}", file=sys.stderr)
        elements = []

    stops: list[dict] = []
    seen_tags: set[str] = set()

    for el in elements:
        tags = el.get("tags", {})
        wiki_tag = tags.get("wikipedia", "")
        if wiki_tag in seen_tags:
            continue
        seen_tags.add(wiki_tag)
        name_hint = tags.get("name") or wiki_tag
        print(f"  + {name_hint} ({wiki_tag})")
        stop = build_stop(session, area_key, name_hint, wiki_tag, radius_m, el)
        if stop and stop["lat"] is not None:
            stops.append(stop)
        time.sleep(0.3)  # be polite to the MediaWiki API

    # Fallback: hardcoded well-known stops if Overpass gave us nothing usable.
    if not stops:
        print("  no usable Overpass results — falling back to hardcoded stops")
        for fb_area, fb_tag, fb_radius in FALLBACK_STOPS:
            if fb_area != area_key or fb_tag in seen_tags:
                continue
            seen_tags.add(fb_tag)
            print(f"  + fallback {fb_tag}")
            stop = build_stop(session, area_key, fb_tag, fb_tag, fb_radius or radius_m, None)
            if stop and stop["lat"] is not None:
                stops.append(stop)
            time.sleep(0.3)

    return stops


def write_pack(pack_dir: Path, stops: list[dict]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "audio").mkdir(exist_ok=True)

    with open(pack_dir / "stops.json", "w", encoding="utf-8") as fh:
        json.dump({"stops": stops}, fh, ensure_ascii=False, indent=2)

    lines = [
        "# Sources — mumbai-demo pack",
        "",
        "Every story in this pack is written from the articles below, shared",
        "under CC BY-SA 4.0. This file feeds the auto-generated CREDITS.md",
        "(see voice.py).",
        "",
    ]
    for s in stops:
        lines.append(f"## {s['name']}")
        lines.append(f"- Area: {s['area']} — {s['lat']}, {s['lon']} (via {s['coord_source']})")
        if s["wikipedia"].get("en"):
            lines.append(f"- EN: {s['wikipedia']['en']}")
        if s["wikipedia"].get("hi"):
            lines.append(f"- HI: {s['wikipedia']['hi']}")
        lines.append("")
    lines += [
        "Map data: (c) OpenStreetMap contributors, ODbL — https://www.openstreetmap.org/copyright",
        "Article text: Wikipedia contributors, CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/",
    ]
    (pack_dir / "sources.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest OSM + Wikipedia stops")
    parser.add_argument("--pack", default="mumbai-demo")
    parser.add_argument("--areas", default="sewri,banganga",
                        help="comma-separated area keys")
    parser.add_argument("--radius", type=int, default=35,
                        help="default geofence radius in meters")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    all_stops: list[dict] = []
    for area_key in [a.strip() for a in args.areas.split(",") if a.strip()]:
        area = AREAS.get(area_key)
        if not area:
            print(f"unknown area: {area_key}", file=sys.stderr)
            sys.exit(2)
        all_stops.extend(harvest_area(session, area_key, area, args.radius))

    if not all_stops:
        print("ERROR: no stops harvested", file=sys.stderr)
        sys.exit(1)

    pack_dir = Path(__file__).resolve().parent / "packs" / args.pack
    write_pack(pack_dir, all_stops)
    print(f"\nwrote {len(all_stops)} stops -> {pack_dir / 'stops.json'}")
    for s in all_stops:
        hi = "hi" if s["excerpt_hi"] else "no-hi"
        print(f"  - {s['id']}: {s['lat']:.5f},{s['lon']:.5f} r={s['radius_m']}m "
              f"[{s['coord_source']}] en={len(s['excerpt_en'])}ch {hi}")


if __name__ == "__main__":
    main()
