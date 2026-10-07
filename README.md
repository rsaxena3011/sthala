# Sthala (स्थल): stories that only play where they happened

An offline, open-source, location-locked audio storyteller. It turns
OpenStreetMap and Wikipedia into short Hindi or English audio stories, each
tied to the exact spot it is about. Your phone stays in your pocket and the
city does the talking.

- Outside the ~35 m zone around a stop, nothing plays.
- One tap starts the walk. No map on screen: a ghungroo chime gets faster as
  you near the next stop.
- Stay 60 seconds and the story goes deeper, layer by layer. Walk away and it
  stops.
- Every story ends with something to do: look, count, or touch.

Built for DEV Hacktoberfest Week 1 (2026), theme **Touch Grass**.

## The Mumbai demo

Three stops, nine stories (three layers each, Hindi and English):

| Stop | What you hear |
|---|---|
| Sewri Fort | The fort's history, the flamingo season at Sewri jetty, and what to look for from the walls |
| Banganga Tank | The tank's legend, its rituals, and the details most visitors walk past |
| Walkeshwar Temple | The temple's story, its architecture, and the quiet corners around it |

Watch the demo: `sthala-demo-v6.mp4` (76 seconds, locked final).

## How it works

All the heavy work happens on a PC beforehand. The phone only does GPS plus
audio playback. No API keys, no cloud, no per-minute voice bills.

```
harvest.py  →  write.py  →  voice.py  →  walk.py (on phone, Termux)
   OSM +        Gemma 4      Indic          GPS zones +
   Wikipedia    via Ollama   Parler-TTS     audio playback
```

1. **harvest.py** pulls temples, tanks, and forts that have Wikipedia links
   from OpenStreetMap (Overpass API) near the demo areas, then fetches the
   Hindi and English Wikipedia article text. Output: `packs/<pack>/stops.json`
   and `packs/<pack>/sources.md`.
2. **write.py** runs Gemma 4 E4B locally via Ollama/llama.cpp. It writes each
   story plus two deeper layers, tags every sentence `[History]` / `[Legend]` /
   `[Scripture]` with its source link. A second "skeptic" pass deletes any line
   the sources do not support. Human review last.
3. **voice.py** voices the scripts with AI4Bharat's Indic Parler-TTS. It writes
   the MP3s, a map file of the stops, and an automatic credits file.
4. **walk.py** runs on a rooted Android phone in Termux. One home-screen tap
   starts it. It holds a wake lock, checks GPS every 5 seconds, and needs two
   readings inside a zone before a story plays. It plays the story audio plus
   the proximity chime, and saves the walk route.

## Try the demo on your PC (no phone needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Simulated GPS trail: approach, dwell, walk away (demo only)
python3 walk.py --pack mumbai-demo --demo
```

## Run it for real (phone)

```bash
# 1. On the PC: build the pack
python3 harvest.py --pack mumbai-demo
python3 write.py --pack mumbai-demo        # needs Ollama + Gemma 4 E4B locally
python3 voice.py --pack mumbai-demo --voices hi,en   # needs parler-tts + torch

# 2. Copy packs/mumbai-demo/ to the phone (Termux ~/sthala/)

# 3. On the phone, in Termux (needs termux-api installed)
python3 walk.py --pack mumbai-demo --lang hi
```

## Make a pack for your street

The pipeline is pack-based. Point `harvest.py` at your area, run the same
three steps, and you get a voiced walk for your own neighbourhood. Walks built
on Wikipedia stay under CC BY-SA; see per-pack `sources.md` and the
auto-generated `CREDITS.md`.

## Repo layout

```
walk.py                 phone runtime (Termux)
harvest.py write.py voice.py   PC pipeline
packs/mumbai-demo/      the demo pack: 18 story MP3s + chime, scripts,
                        map, stops, sources, credits, skeptic log
audio_src/              narration MP3s used in the demo video
sthala-demo-v6.mp4      locked demo video (76 s)
make_demo_video_v6.py   script that built the demo video
docs/final_concept.md   the locked concept and build plan
docs/LOCKED.md          demo video lock record
```

## Open-source AI at its core

| Piece | Tool | Cost |
|---|---|---|
| Map data | OpenStreetMap (Overpass API) | free, open |
| Article text | Wikipedia (MediaWiki API, CC BY-SA) | free, open |
| Story writing | Gemma 4 E4B via Ollama / llama.cpp, local | free, open weights |
| Voice | AI4Bharat Indic Parler-TTS, local | free, open |
| Phone runtime | Termux + termux-api | free |

Why open matters here: cloud voice services charge per character, so a
library of Hindi walks becomes a monthly bill. Local open voice models make it
an overnight job on a home PC. And a locally pinned model plays the same
script next year; no silent model update can rewrite a legend.

## License

- Code: MIT.
- Story text and audio derive from Wikipedia content and are shared under
  CC BY-SA 4.0 (see per-pack `sources.md` and `CREDITS.md`).
