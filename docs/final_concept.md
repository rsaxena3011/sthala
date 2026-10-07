# FINAL Hacktoberfest Week 1 concept: LOCKED 2026-10-07 ~03:50 IST

## Winner: Sthala (स्थल) , stories that only play where they happened
Source: Opus 5.5 Beta (Notion). Beaten: my "NoBars" and GPT's "TouchGrass" (comparison below).

## The concept
An offline, open-source storyteller. It turns OpenStreetMap and Wikipedia into short Hindi or English audio stories, each locked to the exact spot it's about. Your phone stays in your pocket and the city does the talking.

- Outside the 35 m zone around a stop, nothing plays.
- One tap starts the walk. No map: a ghungroo chime gets faster as you near the next stop.
- Stay 60 seconds and the story goes deeper. Walk away and it stops.
- Every story ends with something to do: look, count or touch.

## Why it won (vs the other two)

| Criterion (judging order) | Sthala (Opus) | TouchGrass (GPT) | NoBars (mine) |
|---|---|---|---|
| Writing (weighted most) | Strongest arc: "I make mythology videos for a living. So I built an AI that won't tell a story unless you're standing in it." Dated test runs, the two-Lakshmans Banganga moment | Strong hook too ("I built AI that tells people to stop looking at a screen") | Weakest story, no personal hook |
| Relevance to Touch Grass | Geofence literally enforces it: nothing plays unless you're there | Screenless mission, strong | Screenless, strong |
| Creativity | "An AI that stays quiet until you show up" , place-locked stories, fresh | Photo → invented micro-adventure, very creative | Bird-call ID is close to the challenge's own listed examples , weakest |
| Technical execution | MOST BUILDABLE: heavy work pre-generated on the PC; phone only does GPS + audio playback. No on-device LLM needed | Needs Gemma 4 E2B multimodal running on his OnePlus Nord 2 via LiteRT-LM , GPT itself flagged this as the biggest risk | Needs BirdNET + Ollama on device , heavy |
| Partner stacking | Gemma ($200) + Entire ($100) + Copilot ($100) = $400 potential | Gemma ($200) only | Gemma ($200) only |
| Personal fit | Directly leverages his Amar Gatha mythology work + Hindi TTS app | Generic | Generic |

## Why open innovation matters (paste-ready for the DEV post)
1. Hindi at ₹0 a minute. Cloud voice services charge per character; a library of Hindi walks becomes a monthly bill. Open Indian-language voice models make it an overnight job on a home PC.
2. Fork the whole thing, not an invoice. No API keys: anyone in Varanasi can clone it and add packs/varanasi-ghats tonight. Walks built on Wikipedia stay under CC BY-SA.
3. Sacred stories need a fixed model. A locally pinned Gemma plays the same script next year; no silent model update can rewrite a legend.

## Build plan (new repo `sthala`, Oct 7–11)
PC (Python):
- `harvest.py`: pulls temples/tanks/forts with Wikipedia links from OpenStreetMap, fetches Hindi + English Wikipedia text.
- `write.py`: Gemma 4 E4B via Ollama/llama.cpp writes each story + two deeper layers; every sentence tagged [History]/[Legend]/[Scripture] with source link. A second "skeptic" pass deletes unsourced lines; boss reviews last.
- `voice.py`: AI4Bharat Indic Parler-TTS → MP3s + map file + credits file.
Phone (rooted Android, Termux):
- `walk.py`: one home-screen tap, keeps phone awake, GPS check every 5s, two readings inside a zone before a story plays. Plays audio + chime, saves route.
Demo: earphones, 60-second POV video, Digital Wellbeing screenshot showing screen time.

## Test runs (from Opus's plan)
- Oct 10: Sewri Fort + jetty (flamingo story either way).
- Oct 11 dawn: Banganga–Walkeshwar (avoid Oct 10 , Sarva Pitru Amavasya rites on the steps).
- Hand earphones to one non-techie, film their face.

## DEV post arc
Title: "I make mythology videos for a living. So I built an AI that won't tell a story unless you're standing in it."
Hook → architecture + offline test + privacy reasoning → outside runs with numbers → what broke → why open matters → "make a pack for your street."

## Risks
- GPS drift in narrow lanes: tune zone sizes, get fix before airplane mode, test loop near home first.
- Hallucinated sacred content: skeptic pass + his review; keep stories away from cremation ground/samadhis; never film rituals.
- Android killing background GPS: keep-awake + disable battery optimisation for Termux.
- "It's just MP3s": frame as a tool turning any neighbourhood into a sourced, voiced walk; show the skeptic deleting a made-up line.

## Partner categories
Core: Gemma ($200). Stretch: Entire ($100, log the session where the skeptic was born), GitHub Copilot ($100, Actions workflow validating community walks). Skip ElevenLabs (closed voice contradicts the open argument).

## Deadline
DEV post due Oct 12, 06:59 UTC (12:29 IST). Build Oct 7–11, test runs Oct 10–11, post written Oct 11 night.
