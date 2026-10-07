#!/usr/bin/env python3
"""
voice.py — voices story scripts with Meta's MMS-TTS (Massively Multilingual
Speech), fully open weights (Apache 2.0) for Hindi (facebook/mms-tts-hin)
and English (facebook/mms-tts-eng). Nothing here calls a paid cloud voice
API: Hindi at Rs.0/minute, on the user's own GPU.

NOTE on model choice: the original plan was AI4Bharat's Indic Parler-TTS,
but that checkpoint is a *gated* Hugging Face repo — downloading it needs
an approved access request on a logged-in HF account, which breaks the
zero-human-effort build. MMS-TTS is ungated, Apache-2.0, and runs offline.
Caveat: Hindi and English use different single-speaker MMS voices (not one
consistent voice across languages). If gated access is ever approved,
swap MODEL_IDS below back to ai4bharat/indic-parler-tts with parler-tts.

Pipeline (from packs/<pack>/stories.json + packs/<pack>/scripts/*.txt):
  1. For each stop x layer (1/2/3) x language (hi, en): synthesize to WAV,
     then encode to MP3 (ffmpeg) at 96k mono.
     Output: packs/<pack>/audio/<stop_id>_l<1|2|3>_<hi|en>.mp3
  2. Write packs/<pack>/map.json — the file walk.py reads on the phone.
  3. Write packs/<pack>/CREDITS.md — from sources.md + voice model credit.

Needs: torch, transformers, soundfile, ffmpeg on PATH.

Usage:
    python3 voice.py --pack mumbai-demo [--langs hi,en] [--device auto]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MODEL_IDS = {
    "hi": "facebook/mms-tts-hin",
    "en": "facebook/mms-tts-eng",
}

LANG_NAMES = {"hi": "Hindi", "en": "English"}


def clean_for_tts(text: str) -> str:
    """Strip ALL [Tag] markers (drafts sometimes tag mid-sentence too)."""
    text = re.sub(r"\s*\[(?:History|Legend|Scripture|\?|Action)\]", "", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return " ".join(lines)


def chunk_text(text: str, max_chars: int = 380) -> list[str]:
    """Split into sentence-ish chunks the VITS model handles well."""
    sents = re.split(r"(?<=[.!?।])\s+", text)
    chunks, cur = [], ""
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) + 1 > max_chars and cur:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur)
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Voice stories (MMS-TTS)")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--langs", default="hi,en")
    ap.add_argument("--device", default="auto",
                    help="auto|cpu|cuda (auto prefers cuda when available)")
    args = ap.parse_args()

    import torch
    from transformers import VitsModel, AutoTokenizer
    import soundfile as sf
    import numpy as np

    pack_dir = Path("packs") / args.pack
    audio_dir = pack_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    scripts_dir = pack_dir / "scripts"

    stories = json.loads((pack_dir / "stories.json").read_text(
        encoding="utf-8"))["stops"]
    stops = json.loads((pack_dir / "stops.json").read_text(
        encoding="utf-8"))["stops"]
    coord = {s["id"]: s for s in stops}
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    print(f"device: {device}", flush=True)

    models = {}
    for lang in langs:
        mid = MODEL_IDS[lang]
        print(f"loading {mid} ...", flush=True)
        models[lang] = (
            VitsModel.from_pretrained(mid).to(device).eval(),
            AutoTokenizer.from_pretrained(mid),
        )

    manifest: dict = {"pack": args.pack, "stops": []}

    for sid, sdata in stories.items():
        entry = {
            "id": sid,
            "name": sdata.get("name", sid),
            "lat": coord.get(sid, {}).get("lat"),
            "lon": coord.get(sid, {}).get("lon"),
            "radius_m": coord.get(sid, {}).get("radius_m", 35),
            "status": sdata.get("status", "draft"),
            "audio": {},
        }
        for lang in langs:
            model, tokenizer = models[lang]
            sr = model.config.sampling_rate
            for layer in ("1", "2", "3"):
                script_path = scripts_dir / f"{sid}_l{layer}_{lang}.txt"
                if not script_path.exists():
                    print(f"  SKIP {script_path.name} (missing)", flush=True)
                    continue
                text = clean_for_tts(
                    script_path.read_text(encoding="utf-8"))
                if not text.strip():
                    print(f"  SKIP {script_path.name} (empty)", flush=True)
                    continue
                out_mp3 = audio_dir / f"{sid}_l{layer}_{lang}.mp3"
                print(f"  synth {out_mp3.name} ...", flush=True)
                wavs = []
                for i, ch in enumerate(chunk_text(text)):
                    inputs = tokenizer(ch, return_tensors="pt").to(device)
                    with torch.no_grad():
                        wav = model(**inputs).waveform
                    wavs.append(wav.cpu().numpy().squeeze())
                    wavs.append(np.zeros(int(sr * 0.35), dtype=np.float32))
                    print(f"    chunk {i + 1}", flush=True)
                full = np.concatenate(wavs).astype(np.float32)
                wav_path = out_mp3.with_suffix(".wav")
                sf.write(str(wav_path), full, sr)
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path),
                     "-ac", "1", "-b:a", "96k", str(out_mp3)],
                    check=True)
                wav_path.unlink()
                entry["audio"].setdefault(layer, {})[lang] = \
                    f"audio/{out_mp3.name}"
        manifest["stops"].append(entry)

    (pack_dir / "map.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    sources = (pack_dir / "sources.md").read_text(encoding="utf-8") \
        if (pack_dir / "sources.md").exists() else ""
    credits = [
        f"# Credits — {args.pack}", "",
        "## Story sources",
        sources.strip(), "",
        "Text: Wikipedia contributors, CC BY-SA 4.0 "
        "(https://creativecommons.org/licenses/by-sa/4.0/).", "",
        "## Voice",
        "Synthesized locally with Meta MMS-TTS open weights (Apache 2.0): "
        + ", ".join(f"{LANG_NAMES[l]} ({MODEL_IDS[l]})" for l in langs)
        + " — no cloud voice API, Hindi at Rs.0/minute. "
        "Hindi and English use MMS's separate single-speaker voices.",
        "",
        "## Proximity chime",
        "packs/mumbai-demo/audio/chime.mp3 — synthesized placeholder "
        "(see make_chime.py).",
    ]
    (pack_dir / "CREDITS.md").write_text("\n".join(credits), encoding="utf-8")

    n_mp3 = len(list(audio_dir.glob("*_l[123]_*.mp3")))
    print(f"done: {n_mp3} story MP3s + map.json + CREDITS.md", flush=True)


if __name__ == "__main__":
    main()
