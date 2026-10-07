#!/usr/bin/env python3
"""
write.py — turns harvested article text into layered audio stories using a
LOCAL open-weight model via Ollama. Nothing here calls a cloud API.

Pipeline per stop (from packs/<pack>/stops.json):
  1. FIRST DRAFT — prompt the model with the stop's en+hi article excerpts.
     Ask for a ~90-second spoken story + TWO deeper layers (~60s each),
     in Hindi AND English. Every sentence carries a tag:
         [History]   — verifiable from the Wikipedia article
         [Legend]    — traditional story, marked as legend in the article
         [Scripture] — from a named religious text cited in the article
     plus its source link.
  2. SKEPTIC PASS — second model call with ONLY the article text + the draft.
     Instruction: "Delete any sentence the article text does not support.
     Do not soften, do not rewrite, delete." Every deletion is logged with
     its reason to skeptic_log.json.
  3. Scripts are written to packs/<pack>/scripts/ as plain .txt files
     (what voice.py reads). Stories default to status "draft" — a human
     flips them to "approved" after review.

Story rules (from the locked concept):
  - Every story ends with something to do: look, count, or touch.
  - Sacred sites stay respectful: no invented miracles, no claims the
    skeptic pass cannot source, nothing about cremation grounds/samadhis.
  - Hindi first (Hindi at Rs.0/minute is the whole point of the open stack).

Usage:
    python3 write.py --pack mumbai-demo [--model gemma3:4b]
                     [--ollama-url http://localhost:11434] [--langs hi,en]
                     [--skip-skeptic]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

DRAFT_SYSTEM = (
    "You are a respectful audio-story writer for walking tours at real "
    "historical and sacred places in Mumbai, India. You write ONLY what the "
    "provided source text supports. Output strict JSON only, no other text."
)

DRAFT_PROMPT = """Write spoken-word audio tour stories for this place, in {lang_name}.

SOURCE MATERIAL (Wikipedia article text — your ONLY source of facts):
--- ENGLISH ---
{en_text}
--- HINDI ---
{hi_text}
---
Official article URLs: EN {en_url} | HI {hi_url}

Write THREE layers:
- layer1: the main story, about 90 seconds spoken (~{w1} words in {lang_name}).
- layer2: a deeper layer for visitors who stay 60+ seconds (~{w2} words).
- layer3: the deepest layer (~{w2} words).

Rules:
1. EVERY sentence ends with EXACTLY ONE tag, placed AFTER the final full
   stop, like this: "The fort was built in 1680. [History]" Never put a tag
   in the middle of a sentence. Use ONLY these three tags, never invent
   others:
   [History] = stated in the article text above. [Legend] = the article
   presents it as legend/tradition. [Scripture] = the article cites a named
   religious text. When in doubt, use [Legend] and keep it clearly framed
   as tradition, never as fact.
2. Each layer ENDS with one concrete thing for the visitor to do: look at
   something, count something, or touch something real at the site.
3. Respectful tone throughout. No invented miracles, no horror, no claims
   about cremation grounds or samadhis. This is a heritage walk, not a
   ghost tour.
4. If the Hindi article text is missing, write the Hindi story from the
   English article, but tag sentences [History] ONLY where the English
   article supports them.
5. Never pad with unverifiable detail. Fewer strong, supported sentences
   beat more weak ones. If the article is thin, write thin.

Return STRICT JSON only:
{{"layers": {{
  "1": [{{"text": "First sentence. [History]", "tag": "History"}}, ...],
  "2": [...],
  "3": [...]
}}}}"""

SKEPTIC_SYSTEM = (
    "You are a careful fact-checker. You are conservative: you flag a "
    "sentence ONLY when you are sure its factual claim is not in the "
    "source. Output strict JSON only, no other text."
)

SKEPTIC_PROMPT = """Fact-check the numbered draft sentences below against the source article text.

SOURCE ARTICLE TEXT:
--- ENGLISH ---
{en_text}
--- HINDI ---
{hi_text}
---

DRAFT SENTENCES (n = sentence number, L = story layer):
{numbered}

Your job: list the numbers of sentences that make SPECIFIC checkable claims
(a date, a person's name, a number, an event, a cause, a quotation) which are
NOT stated in the source article text above, or which CONTRADICT it.

Rules:
- Layer 1 sentences are tagged [History]: check these strictly.
- Layer 2 [Legend] and Layer 3 [Scripture] tell traditional/religious stories.
  NEVER flag them for being non-factual. Flag one ONLY if it presents a
  legend as documented history.
- Scene-setting and atmosphere ("the stones are warm at dawn") are ALWAYS
  fine. Never flag them.
- A sentence that paraphrases the article in different words is SUPPORTED.
  Do not demand word-for-word matches.
- The draft may be in Hindi while the source article is in English (or vice
  versa). Judge whether the MEANING is supported across languages. Never
  flag a sentence merely for being in a different language than the source.
- When in doubt, DO NOT flag the sentence. An empty list is a perfectly
  good answer and means the draft is clean.

Return STRICT JSON only:
{{"unsupported": [3, 17]}}  (sentence numbers, or [] if none)"""


def ollama_chat(url: str, model: str, system: str, prompt: str,
                 tries: int = 3) -> dict:
    last_err = ""
    for attempt in range(1, tries + 1):
        try:
            body = json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2, "num_ctx": 16384},
            }).encode()
            req = urllib.request.Request(
                f"{url}/api/chat", data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as resp:
                data = json.loads(resp.read().decode())
            return json.loads(data["message"]["content"])
        except Exception as exc:  # noqa: BLE001 — retry then surface
            last_err = str(exc)
            print(f"    ollama attempt {attempt}/{tries} failed: {last_err}",
                  file=sys.stderr)
            time.sleep(5)
    raise RuntimeError(f"ollama /api/chat failed after {tries} tries: {last_err}")


def check_ollama(url: str, model: str) -> None:
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=15) as resp:
            models = [m["name"] for m in json.loads(resp.read())["models"]]
    except Exception as exc:
        raise SystemExit(f"cannot reach ollama at {url}: {exc}\n"
                         "start it with: ollama serve")
    want = model.split(":")[0]
    if not any(want in m for m in models):
        print(f"WARNING: model '{model}' not in ollama list {models}; "
              "continuing anyway", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="Draft layered stories (Ollama)")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--model", default="gemma3:4b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--langs", default="hi,en")
    ap.add_argument("--skip-skeptic", action="store_true")
    args = ap.parse_args()

    pack_dir = Path("packs") / args.pack
    stops = json.loads((pack_dir / "stops.json").read_text(encoding="utf-8"))["stops"]
    scripts_dir = pack_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)

    check_ollama(args.ollama_url, args.model)
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    lang_names = {"hi": "Hindi (Devanagari script)", "en": "English"}
    lang_words = {"hi": (120, 90), "en": (140, 100)}  # (layer1, deeper)

    stories: dict = {"pack": args.pack, "model": args.model, "stops": {}}
    skeptic_log: dict = {"pack": args.pack, "model": args.model, "stops": {}}

    for stop in stops:
        sid = stop["id"]
        print(f"== {sid} ({stop['name']})", flush=True)
        en_text = stop.get("excerpt_en", "")[:6000]
        hi_text = stop.get("excerpt_hi", "")[:6000]
        en_url = stop.get("wikipedia", {}).get("en", "")
        hi_url = stop.get("wikipedia", {}).get("hi", "")

        stop_out: dict = {"name": stop["name"], "status": "draft", "layers": {}}
        stop_skeptic: dict = {"deleted": [], "kept_counts": {}}

        for lang in langs:
            w1, w2 = lang_words.get(lang, (195, 125))
            print(f"  [{lang}] drafting...", flush=True)
            draft = ollama_chat(
                args.ollama_url, args.model, DRAFT_SYSTEM,
                DRAFT_PROMPT.format(
                    lang_name=lang_names.get(lang, lang),
                    en_text=en_text or "(none)", hi_text=hi_text or "(none)",
                    en_url=en_url, hi_url=hi_url, w1=w1, w2=w2))

            if args.skip_skeptic:
                kept = draft.get("layers", {})
                deleted = []
            else:
                print(f"  [{lang}] skeptic pass...", flush=True)
                layers = draft.get("layers", {})
                numbered, idx = [], {}
                n = 0
                for layer in ("1", "2", "3"):
                    for s in layers.get(layer, []) or []:
                        if not isinstance(s, dict):
                            continue
                        n += 1
                        idx[n] = (layer, s)
                        numbered.append(
                            f"{n}. [L{layer}/{s.get('tag', '?')}] "
                            f"{s.get('text', '').strip()}")
                verdict = ollama_chat(
                    args.ollama_url, args.model, SKEPTIC_SYSTEM,
                    SKEPTIC_PROMPT.format(
                        en_text=en_text or "(none)",
                        hi_text=hi_text or "(none)",
                        numbered="\n".join(numbered) or "(no sentences)"))
                bad = {int(x) for x in verdict.get("unsupported", [])
                       if str(x).isdigit()}
                kept = {"1": [], "2": [], "3": []}
                deleted = []
                for num in sorted(idx):
                    layer, s = idx[num]
                    if num in bad:
                        deleted.append({"lang": lang, "layer": layer,
                                        "text": s.get("text", ""),
                                        "tag": s.get("tag", "")})
                    else:
                        kept[layer].append(s)

            stop_out["layers"][lang] = kept
            stop_skeptic["deleted"].extend(
                {"lang": lang, **d} for d in deleted
                if isinstance(d, dict))
            for layer, sents in kept.items():
                if isinstance(sents, list):
                    stop_skeptic["kept_counts"][f"{lang}/layer{layer}"] = len(sents)
                    lines = [f"{s.get('text', '').strip()} [{s.get('tag', '?')}]"
                             for s in sents if isinstance(s, dict)]
                    (scripts_dir / f"{sid}_l{layer}_{lang}.txt").write_text(
                        "\n".join(lines) + "\n", encoding="utf-8")

        stories["stops"][sid] = stop_out
        skeptic_log["stops"][sid] = stop_skeptic
        print(f"  skeptic deleted {len(stop_skeptic['deleted'])} sentence(s)",
              flush=True)

    (pack_dir / "stories.json").write_text(
        json.dumps(stories, ensure_ascii=False, indent=1), encoding="utf-8")
    (pack_dir / "skeptic_log.json").write_text(
        json.dumps(skeptic_log, ensure_ascii=False, indent=1), encoding="utf-8")
    n_scripts = len(list(scripts_dir.glob("*.txt")))
    print(f"wrote {pack_dir / 'stories.json'} + "
          f"{pack_dir / 'skeptic_log.json'} + {n_scripts} scripts")


if __name__ == "__main__":
    main()
