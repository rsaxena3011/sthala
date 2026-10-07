#!/usr/bin/env python3
"""
walk.py — the on-phone player. Runs in Termux on Android.

One tap starts the walk (Termux widget compatible — all args have defaults).
The phone stays in the pocket: no map, just audio.

Behavior (per the locked concept):
  - Holds a Termux wake lock so Android does not kill GPS.
  - Reads GPS every 5 seconds (termux-location).
  - A stop's story plays only after TWO consecutive readings land inside its
    geofence (default 35 m) — this filters GPS drift.
  - A ghungroo chime plays at intervals that shrink as you approach the
    nearest unvisited stop (the closer you get, the faster the chime).
  - Stay 60 s inside a zone -> the story goes deeper (layer 2, then layer 3).
    Walk away -> audio stops.
  - Every stop's story ends with something to do: look, count, or touch
    (that is a writing rule, enforced in write.py).
  - The whole route (fixes + events) is logged to route_<timestamp>.jsonl.

Audio layout (produced by voice.py):
    packs/<pack>/audio/<stop_id>_l<1|2|3>_<hi|en>.mp3
    packs/<pack>/audio/chime.mp3
    packs/<pack>/map.json   (stop list with audio paths)

Requirements on the phone:
    pkg install termux-api python
    (termux-api app installed from F-Droid; battery optimisation OFF for Termux)

Usage:
    python3 walk.py                       # defaults: pack=mumbai-demo, lang=hi
    python3 walk.py --pack mumbai-demo --lang en --replay
    python3 walk.py --demo                # PC testing: simulated GPS trail
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
GPS_INTERVAL_S = 5.0
DWELL_DEEPER_S = 60.0          # stay this long -> next story layer
CONSECUTIVE_FIXES = 2          # fixes inside the zone before a story plays
CHIME_MIN_S = 1.5              # chime interval right at the zone edge
CHIME_MAX_S = 15.0             # chime interval when far away
MAX_ACC_M = 60.0               # ignore fixes worse than this (cell-tower junk)
# Demo mode (PC testing, no GPS): faster loop, shorter dwell so layers flip
# quickly. These NEVER apply to a real walk.
DEMO_INTERVAL_S = 1.0
DEMO_DWELL_S = 10.0
DEMO = False                   # set by --demo


# ----------------------------------------------------------------------------
# Termux helpers
# ----------------------------------------------------------------------------
def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def wake_lock() -> None:
    if have("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"], check=False)


def wake_unlock() -> None:
    if have("termux-wake-unlock"):
        subprocess.run(["termux-wake-unlock"], check=False)


def get_fix() -> dict | None:
    """One GPS fix via termux-location. Returns dict or None."""
    if not have("termux-location"):
        return None
    try:
        proc = subprocess.run(
            ["termux-location", "-p", "gps", "-r", "once"],
            capture_output=True, text=True, timeout=20,
        )
        data = json.loads(proc.stdout or "{}")
        if "latitude" in data and "longitude" in data:
            return {
                "lat": float(data["latitude"]),
                "lon": float(data["longitude"]),
                "acc": float(data.get("accuracy", 999)),
            }
    except Exception as exc:  # noqa: BLE001 - GPS is best-effort
        print(f"  [gps] fix failed: {exc}", file=sys.stderr)
    return None


def play(path: Path) -> None:
    if DEMO:
        print(f"  [demo-audio] would play: {path.name}")
        return
    if have("termux-media-player"):
        subprocess.run(["termux-media-player", "play", str(path)],
                       check=False, capture_output=True)


def stop_audio() -> None:
    if DEMO:
        return
    if have("termux-media-player"):
        subprocess.run(["termux-media-player", "stop"],
                       check=False, capture_output=True)


def stop_audio_for(s: dict, layer: int, lang: str, pack_dir: Path) -> Path | None:
    """Resolve a stop's audio file. map.json nests audio as
    {"1": {"hi": path, "en": path}, ...}; also accepts the flat
    "l1_hi" form defensively."""
    audio = s.get("audio") or {}
    node = audio.get(str(layer)) or {}
    if isinstance(node, dict):
        path = node.get(lang)
    else:
        path = audio.get(f"l{layer}_{lang}")
    if path and (pack_dir / path).exists():
        return pack_dir / path
    return None


# ----------------------------------------------------------------------------
# Geo
# ----------------------------------------------------------------------------
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def chime_interval_s(distance_m: float) -> float:
    """Closer -> faster chime. ~4s at the zone edge, capped at 15s far away."""
    return max(CHIME_MIN_S, min(CHIME_MAX_S, distance_m / 8.0))


# ----------------------------------------------------------------------------
# Pack loading
# ----------------------------------------------------------------------------
def load_pack(pack_dir: Path) -> list[dict]:
    """Prefer voice.py's map.json; fall back to harvest.py's stops.json."""
    map_file = pack_dir / "map.json"
    if map_file.exists():
        data = json.loads(map_file.read_text(encoding="utf-8"))
        return data["stops"]
    stops_file = pack_dir / "stops.json"
    if stops_file.exists():
        data = json.loads(stops_file.read_text(encoding="utf-8"))
        print("[walk] map.json not found — using stops.json (stories not voiced yet).")
        print("[walk] Run voice.py first, then copy the pack to the phone.")
        return [
            {
                "id": s["id"], "name": s["name"],
                "lat": s["lat"], "lon": s["lon"],
                "radius_m": s.get("radius_m", 35),
                "audio": {},  # no voiced audio yet
            }
            for s in data["stops"]
        ]
    raise SystemExit(f"no map.json or stops.json in {pack_dir}")


# ----------------------------------------------------------------------------
# Demo mode: synthetic GPS trail for PC testing (no satellites needed)
# ----------------------------------------------------------------------------
def demo_trail(stops: list[dict], dwell_s: float, interval_s: float):
    """Yield (lat, lon, acc) fixes: approach each stop from the south,
    dwell long enough for deeper layers, walk away mid-story at stop 2
    to exercise the zone-exit path, then finish."""
    import random
    trail: list[tuple[float, float, float]] = []
    for i, s in enumerate(stops):
        lat, lon = s["lat"], s["lon"]
        # Approach: 150m out -> dead center (enters the 35m zone on the way).
        for d in (150, 100, 60, 35, 20, 10, 5, 0):
            trail.append((lat - d / 111320.0, lon, 5.0))
        # Dwell: stop 2 (index 1) gets a short dwell then a walk-away;
        # the others dwell long enough for layer 3.
        if i == 1:
            n_dwell = int(dwell_s / interval_s) + 3   # layer 2 only
        else:
            n_dwell = int(dwell_s * 2 / interval_s) + 4  # reaches layer 3
        for _ in range(n_dwell):
            trail.append((lat + random.uniform(-3, 3) / 111320.0,
                          lon + random.uniform(-3, 3) / 111320.0, 5.0))
        if i == 1:
            print("  [demo] walking away mid-story to test zone exit…")
            for d in (20, 60, 120):
                trail.append((lat - d / 111320.0, lon, 5.0))
    return iter(trail)


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Sthala walk player (Termux)")
    ap.add_argument("--pack", default="mumbai-demo")
    ap.add_argument("--lang", default="hi", choices=["hi", "en"])
    ap.add_argument("--replay", action="store_true",
                    help="allow stories to replay if you re-enter a zone")
    ap.add_argument("--demo", action="store_true",
                    help="PC testing: simulate a GPS trail through all stops, "
                         "no satellites needed. Audio is logged, not played.")
    args = ap.parse_args()
    global DEMO
    DEMO = args.demo
    interval = DEMO_INTERVAL_S if DEMO else GPS_INTERVAL_S
    dwell_needed = DEMO_DWELL_S if DEMO else DWELL_DEEPER_S

    pack_dir = BASE / "packs" / args.pack
    stops = load_pack(pack_dir)
    stops = [s for s in stops if s.get("lat") is not None]
    if not stops:
        raise SystemExit("no stops with coordinates — run harvest.py first")

    chime = pack_dir / "audio" / "chime.mp3"
    if not chime.exists():
        print(f"[walk] warning: {chime} missing — proximity chime disabled")

    route_path = BASE / f"route_{dt.datetime.now():%Y%m%d_%H%M%S}.jsonl"
    route_fh = route_path.open("w", encoding="utf-8")
    print(f"[walk] logging route to {route_path.name}")

    def log(event: str, **kw) -> None:
        route_fh.write(json.dumps(
            {"t": dt.datetime.now().isoformat(timespec="seconds"),
             "event": event, **kw}, ensure_ascii=False) + "\n")
        route_fh.flush()

    # Per-stop runtime state
    state = {
        s["id"]: {"inside_streak": 0, "entered_at": None,
                  "layer": 0, "played": False}
        for s in stops
    }

    print(f"[walk] {len(stops)} stops, lang={args.lang}. Get a GPS fix, then walk.")
    if DEMO:
        print("[demo] SIMULATED GPS trail — approach, dwell, walk-away. "
              f"dwell threshold {dwell_needed:.0f}s (demo only).")
    print("[walk] Press Ctrl-C to end the walk.")
    log("walk_start", pack=args.pack, lang=args.lang, stops=len(stops),
        demo=DEMO)
    wake_lock()
    last_chime_at = 0.0
    demo_iter = demo_trail(stops, dwell_needed, interval) if DEMO else None

    try:
        while True:
            loop_start = time.time()
            if DEMO:
                try:
                    lat, lon, acc = next(demo_iter)
                    fix = {"lat": lat, "lon": lon, "acc": acc}
                except StopIteration:
                    print("[demo] trail complete.")
                    break
            else:
                fix = get_fix()
            if fix is None:
                print("  [gps] no fix — waiting for satellites…")
                time.sleep(GPS_INTERVAL_S)
                continue
            if fix["acc"] > MAX_ACC_M:
                print(f"  [gps] fix too coarse ({fix['acc']:.0f}m) — ignoring")
                log("fix_skipped", **fix)
                time.sleep(GPS_INTERVAL_S)
                continue
            log("fix", demo=DEMO, **fix)

            # Distance to every stop; nearest unvisited drives the chime.
            nearest = None
            for s in stops:
                st = state[s["id"]]
                if st["played"] and not args.replay:
                    continue
                d = haversine_m(fix["lat"], fix["lon"], s["lat"], s["lon"])
                if nearest is None or d < nearest[0]:
                    nearest = (d, s)

            now = time.time()
            if nearest and chime.exists() and now - last_chime_at >= chime_interval_s(nearest[0]):
                play(chime)
                last_chime_at = now

            for s in stops:
                st = state[s["id"]]
                d = haversine_m(fix["lat"], fix["lon"], s["lat"], s["lon"])
                inside = d <= s.get("radius_m", 35)

                if inside:
                    st["inside_streak"] += 1
                else:
                    if st["entered_at"] is not None:
                        # Walked away mid-story: stop audio, reset.
                        print(f"  [walk] left {s['name']} — stopping audio")
                        log("zone_exit", stop=s["id"], distance_m=round(d, 1))
                        stop_audio()
                        st.update(inside_streak=0, entered_at=None, layer=0)
                    else:
                        st["inside_streak"] = 0
                    continue

                # Inside the zone.
                if st["entered_at"] is None and st["inside_streak"] >= CONSECUTIVE_FIXES:
                    if st["played"] and not args.replay:
                        continue
                    st["entered_at"] = now
                    st["layer"] = 1
                    st["played"] = True
                    audio = stop_audio_for(s, 1, args.lang, pack_dir)
                    print(f"  [walk] ENTERED {s['name']} ({d:.0f}m) — playing layer 1")
                    log("zone_enter", stop=s["id"], distance_m=round(d, 1))
                    if audio:
                        play(audio)
                    else:
                        print(f"  [walk] no audio for {s['id']} l1_{args.lang} "
                              f"(run voice.py)")

                elif st["entered_at"] is not None:
                    # Dwell: staying inside -> deeper layer.
                    dwell = now - st["entered_at"]
                    want_layer = 1 + int(dwell // dwell_needed)
                    if want_layer > st["layer"] and want_layer <= 3:
                        st["layer"] = want_layer
                        audio = stop_audio_for(s, want_layer, args.lang, pack_dir)
                        print(f"  [walk] {dwell:.0f}s inside {s['name']} — layer {want_layer}")
                        log("deeper", stop=s["id"], layer=want_layer,
                            dwell_s=round(dwell))
                        if audio:
                            play(audio)

            elapsed = time.time() - loop_start
            time.sleep(max(0.0, interval - elapsed))
    except KeyboardInterrupt:
        print("\n[walk] walk ended.")
        log("walk_end")
    finally:
        stop_audio()
        wake_unlock()
        route_fh.close()
        print(f"[walk] route saved: {route_path}")


if __name__ == "__main__":
    main()
