#!/usr/bin/env python3
"""Sthala demo video v6: v5 with the walk section tightened 16s -> 13.5s
(boss: the 15-20s voiceless stretch dragged). Nothing else changed.

Changes from v4:
1. Hindi fragment REMOVED from the scale section (no more surprise Hindi).
2. Full story voiceover retained (story_cut.mp3, 24.85s).
3. Story captions: 5 small complete captions synced to the full VO
   (transcript: story_cut_transcript.txt), font 30, lower third, fade in/out.
4. Chime softer (0.11) and sparser (walk: 4, linger: 1, scale: 1, away: 2,
   open: 1, end: 1 = 10 total vs v4's ~20).
5. Scale text card dropped entirely per boss (no replacement wording);
   clean visual beat with no text. Narrator n5 unchanged from v4.
No em dashes anywhere on screen (verified by grep).
76.5s, 24fps, 1280x720."""
import math, os, struct, subprocess, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
PACK = HERE / "packs" / "mumbai-demo"
AUD = PACK / "audio"
REF = HERE / "ref_frames"
FR = HERE / "hidden_demo_frames_v6"
TMP = Path("/tmp/sthala_demo_v6")
NV = HERE / "audio_src"  # narrator clips n1..n7 (+ n5_v5)
W, H, FPS = 1280, 720, 24
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FRG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
NAVY, TEAL, WHITE, DIM, AMBER = (11, 16, 32), (45, 212, 191), (240, 240, 240), (140, 150, 170), (232, 176, 80)
CARD = (20, 28, 48)
FR.mkdir(exist_ok=True); TMP.mkdir(exist_ok=True)

def F(p, s): return ImageFont.truetype(p, s)
def ctr(d, y, txt, font, fill):
    bb = d.textbbox((0, 0), txt, font=font)
    d.text(((W - (bb[2] - bb[0])) / 2, y), txt, font=font, fill=fill)
def ease_out(t): return 1 - (1 - t) ** 3
def run(cmd): subprocess.run(cmd, check=True)

CHIME = AUD / "chime.mp3"
ASRC = HERE / "audio_src"
STORY = ASRC / "story_cut.mp3"

def mix_section(clips, total, out):
    args = ["ffmpeg", "-y", "-v", "error"]
    for path, _, _ in clips: args += ["-i", str(path)]
    fc = ""
    for k, (_, delay, filt) in enumerate(clips):
        fc += f"[{k}:a]"
        if filt: fc += filt + ","
        fc += f"adelay={int(delay * 1000)}|{int(delay * 1000)}[c{k}];"
    fc += "".join(f"[c{k}]" for k in range(len(clips)))
    fc += f"amix=inputs={len(clips)}:normalize=0,apad=whole_dur={total}[m]"
    run(args + ["-filter_complex", fc, "-map", "[m]", "-ar", "22050", "-ac", "1",
                "-c:a", "aac", "-t", str(total), out])

def chime_clips(tick_list, vol=0.11):
    return [(CHIME, t, f"volume={vol},lowpass=f=2800") for t in tick_list]

def ticks(dur, start=2.0, factor=0.93, mind=0.5, t0=0.5):
    ts, t, iv = [], t0, start
    while t < dur - 0.3:
        ts.append(round(t, 2)); t += iv; iv = max(mind, iv * factor)
    return ts

# reference art
ART_NAV = Image.open(REF / "art_nav_clean.png").convert("RGB")
ART_KIN = Image.open(REF / "art_kinetic_clean.png").convert("RGB")
ART_CST = Image.open(REF / "art_coastline_clean.png").convert("RGB")
# story bg: darkened kinetic art
KIN_DARK = ART_KIN.filter(ImageFilter.GaussianBlur(5))
KIN_DARK = Image.blend(Image.new("RGB", (W, H), (4, 6, 12)), KIN_DARK, 0.28)

# envelope of story cut
run(["ffmpeg", "-y", "-v", "error", "-i", str(STORY), "-ar", "16000", "-ac", "1", str(TMP / "story.wav")])
w = wave.open(str(TMP / "story.wav")); n = w.getnframes()
s = struct.unpack("<%dh" % n, w.readframes(n)); w.close()
W2 = 1600
env = [math.sqrt(sum(x * x for x in s[i:i + W2]) / W2) for i in range(0, n - W2, W2)]
mx = max(env) or 1; env = [e / mx for e in env]
def env_at(t): return env[min(int(t * 10), len(env) - 1)] if t >= 0 else 0

# nav-art geometry (measured): fort + baked 35m ring
FORT = (845, 300); RING_R = 155
P0 = (250, 640); PC = (480, 600); P1 = (735, 410)  # bezier to ring edge
def bez(p):
    x = (1-p)**2*P0[0] + 2*(1-p)*p*PC[0] + p**2*P1[0]
    y = (1-p)**2*P0[1] + 2*(1-p)*p*PC[1] + p**2*P1[1]
    return x, y

# ================================================================ 0-6 OPEN: PIL title card
def title_card(sub1, sub2):
    im = Image.new("RGB", (W, H), (5, 8, 16)); d = ImageDraw.Draw(im, "RGBA")
    for k in range(16):  # faint topo contours
        r = 120 + k * 46
        d.ellipse([W/2 - r*1.7, H/2 - r*0.75, W/2 + r*1.7, H/2 + r*0.75],
                  outline=(22, 34, 58, 200), width=1)
    for r in (46, 30, 16):  # amber dot glow
        d.ellipse([W/2-r, 560-r, W/2+r, 560+r], fill=AMBER + (int(90*(1-r/50)),))
    d.ellipse([W/2-7, 553, W/2+7, 567], fill=AMBER)
    ctr(d, 250, "Sthala", F(SERIF, 120), WHITE)
    ctr(d, 400, sub1, F(FB, 40), TEAL)
    ctr(d, 470, sub2, F(FRG, 28), DIM)
    return im
for i in range(144):
    t = i / FPS
    im = title_card("stories that only play where they happened", "")
    fp = FR / f"o_{i:04d}.png"
    if fp.exists():
        continue
    if t < 0.8:  # fade from black
        im = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), im, t / 0.8)
    im.save(fp)
mix_section([(NV / "n1.mp3", 0.8, None)] + chime_clips([0.4]), 6, TMP / "open.aac")

# ================================================================ 6-22 WALK (16s)
walk_dur = 13.5  # v6: tightened from 16.0 (boss: 15-20s dragged)
def walk_d(t): return 35 + 115 * (1 - t / walk_dur) ** 1.6
wticks = ticks(walk_dur)
wchimes = wticks[:4]  # v5: sparse, was ~10
for i in range(int(walk_dur * FPS)):
    t = i / FPS
    fp = FR / f"w_{i:04d}.png"
    if fp.exists():
        continue
    im = ART_NAV.copy(); d = ImageDraw.Draw(im, "RGBA")
    p = 1 - (walk_d(t) - 35) / 115
    px, py = bez(max(0, min(1, p)))
    # trail behind
    for j in range(0, int(t * FPS), 6):
        pj = 1 - (walk_d(j / FPS) - 35) / 115
        qx, qy = bez(max(0, min(1, pj)))
        d.ellipse([qx-4, qy-4, qx+4, qy+4], fill=AMBER + (150,))
    # walker dot with halo
    d.ellipse([px-16, py-16, px+16, py+16], outline=AMBER + (120,), width=2)
    d.ellipse([px-9, py-9, px+9, py+9], fill=AMBER)
    # chime ripples at fort, synced to the (sparse) chimes
    for tk in wchimes:
        age = t - tk
        if 0 <= age < 1.2:
            rr = 30 + age * 120
            d.ellipse([FORT[0]-rr, FORT[1]-rr, FORT[0]+rr, FORT[1]+rr],
                      outline=AMBER + (int(190 * (1 - age / 1.2)),), width=2)
    # live counter card (covers baked "71 m")
    d.rounded_rectangle([36, 28, 250, 88], radius=14, fill=CARD)
    d.text((60, 42), f"{walk_d(t):.0f} m", font=F(FB, 34), fill=WHITE)
    # zone touch: flash + card, dot halts at ring edge
    if walk_d(t) <= 36:
        d.ellipse([FORT[0]-RING_R-6, FORT[1]-RING_R-6, FORT[0]+RING_R+6, FORT[1]+RING_R+6],
                  outline=(255, 255, 255, 220), width=3)
        d.rounded_rectangle([W/2-260, 96, W/2+260, 168], radius=14, fill=CARD)
        ctr(d, 110, "35 metres. It starts.", F(FB, 30), TEAL)
    # phone card beat
    if 0.5 <= t < 4.2:
        slide = 0 if t < 3.2 else ease_out(min(1, (t - 3.2)))
        by0 = 600 + slide * 260
        d.rounded_rectangle([W/2-270, by0-420, W/2+270, by0-304], radius=18,
                            fill=CARD, outline=TEAL + (200,), width=2)
        ctr(d, by0 - 404, "Sewri Fort . 31 m", F(FB, 30), WHITE)
        ctr(d, by0 - 360, "STORY AVAILABLE", F(FB, 24), TEAL)
    if 4.2 <= t < 7.2:
        d.rounded_rectangle([40, H-96, 560, H-36], radius=14, fill=CARD)
        d.text((64, H-82), "Phone stays in the pocket.", font=F(FB, 26), fill=WHITE)
    im.save(fp)
mix_section([(NV / "n2.mp3", 0.8, None)] + chime_clips(wchimes), walk_dur, TMP / "walk.aac")

# ================================================================ 22-26 LINGER (4s)
for i in range(96):
    t = i / FPS
    fp = FR / f"l_{i:04d}.png"
    if fp.exists():
        continue
    im = ART_NAV.copy(); d = ImageDraw.Draw(im, "RGBA")
    px, py = P1  # halted at ring edge
    d.ellipse([px-16, py-16, px+16, py+16], outline=AMBER + (120,), width=2)
    d.ellipse([px-9, py-9, px+9, py+9], fill=AMBER)
    frac = min(1, t / 3.4)
    d.arc([px-48, py-48, px+48, py+48], start=-90, end=-90 + 360 * frac, fill=AMBER, width=6)
    d.rounded_rectangle([36, 28, 250, 88], radius=14, fill=CARD)
    d.text((60, 42), "35 m", font=F(FB, 34), fill=WHITE)
    d.rounded_rectangle([36, 104, 330, 164], radius=14, fill=CARD)
    d.text((60, 118), "stay.", font=F(FB, 28), fill=DIM)
    if frac >= 1:
        d.rounded_rectangle([36, 176, 420, 236], radius=14, fill=CARD)
        d.text((60, 190), "layer 2... layer 3.", font=F(FB, 28), fill=TEAL)
    im.save(fp)
mix_section([(NV / "n3.mp3", 0.3, None)] + chime_clips([1.4]), 4, TMP / "linger.aac")

# ================================================================ 26-56 STORY (30s)
VO_OFF = 5.0
# Full-VO captions, synced to story_cut.mp3 segment timings (see story_cut_transcript.txt)
CAPTIONS = [
    (VO_OFF + 0.00, VO_OFF + 3.32,
     "Sewri Fort represents more than just a military structure."),
    (VO_OFF + 3.72, VO_OFF + 7.92,
     "It's a window into the complex political landscape of 17th century India."),
    (VO_OFF + 8.58, VO_OFF + 12.94,
     "The fort's evolution, from a watchtower to a prison to a storage facility,"),
    (VO_OFF + 13.42, VO_OFF + 17.08,
     "reflects the changing fortunes of Mumbai and its strategic importance."),
    (VO_OFF + 17.54, VO_OFF + 24.36,
     "As you stand here, consider the countless lives impacted by the events that unfolded within these walls."),
]
CF = F(FRG, 30)
def wrap_txt(txt, font, maxw):
    lines, cur = [], ""
    for wd in txt.split():
        trial = (cur + " " + wd).strip()
        if font.getbbox(trial)[2] <= maxw:
            cur = trial
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines
CAPW = [(s, e, wrap_txt(t, CF, 1060)) for s, e, t in CAPTIONS]
nS = 30 * FPS
for i in range(nS):
    t = i / FPS
    fp = FR / f"s_{i:04d}.png"
    if fp.exists():
        continue
    im = KIN_DARK.copy(); d = ImageDraw.Draw(im, "RGBA")
    if t < VO_OFF:
        ctr(d, H/2 - 100, "Sewri Fort", F(SERIF, 72), WHITE)
        ctr(d, H/2 + 0, "a Sthala story", F(FRG, 32), TEAL)
    else:
        vt = t - VO_OFF
        for s, e, lines in CAPW:
            if s <= t < e + 0.3:
                a = max(0.0, min(1.0, (t - s) / 0.25, (e + 0.3 - t) / 0.25))
                lh = 42
                bw = max(CF.getbbox(l)[2] for l in lines) + 56
                bh = lh * len(lines) + 36
                bx0, by0 = (W - bw) / 2, H - 190 - bh
                d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=14,
                                    fill=(10, 14, 26, int(205 * a)))
                for k, l in enumerate(lines):
                    bb = CF.getbbox(l)
                    tx = (W - (bb[2] - bb[0])) / 2
                    d.text((tx, by0 + 18 + k * lh), l,
                           font=CF, fill=WHITE + (int(255 * a),))
        # voice topography shimmer at bottom
        for gx in range(0, W, 10):
            v = env_at(vt)
            h = v * 26
            d.line([(gx, H - 10 - h), (gx, H - 10)], fill=TEAL + (110,), width=3)
    d.rectangle([0, H - 5, W * (i / nS), H], fill=AMBER + (200,))
    im.save(fp)
print("story frames done")
mix_section([(NV / "n4.mp3", 0.5, None), (STORY, VO_OFF, None)], 30, TMP / "story.aac")

# ================================================================ 56-68 SCALE (12s)
# v5: Hindi fragment removed; text card dropped entirely (clean visual beat).
DOTS = [(783, 124, "Sewri Fort", (808, 100)),
        (636, 322, "Banganga Tank", (661, 298)),
        (398, 594, "Walkeshwar Temple", (180, 500))]
for i in range(288):
    t = i / FPS
    fp = FR / f"c_{i:04d}.png"
    if fp.exists():
        continue
    im = ART_CST.copy(); d = ImageDraw.Draw(im, "RGBA")
    lit = 1 + int(t / 3.6)
    for j, (x, y, nm, (lx, ly)) in enumerate(DOTS):
        on = j < lit
        if on:
            pulse = 1 + 0.14 * math.sin(t * 6)
            for rr in (30, 21, 13):
                d.ellipse([x-rr*pulse, y-rr*pulse, x+rr*pulse, y+rr*pulse],
                          outline=AMBER + (int(200 - rr * 5),), width=2)
        d.text((lx+2, ly+2), nm, font=F(FB, 28), fill=(0, 0, 0, 170))
        d.text((lx, ly), nm, font=F(FB, 28), fill=WHITE if on else DIM)
        if j == 1 and on:
            d.text((661, 340), "layer 2", font=F(FRG, 22), fill=TEAL)
            d.rounded_rectangle([40, H-132, 1030, H-84], radius=12, fill=CARD)
            d.text((64, H-118), "Tied to the Ramayana, where Ram and Lakshman prayed for water.",
                   font=F(FRG, 24), fill=WHITE)
    # v5: text card dropped entirely per boss. Clean visual beat, no text.
    im.save(fp)
mix_section([(NV / "n5.mp3", 0.5, None)] + chime_clips([0.4]), 12, TMP / "scale.aac")

# ================================================================ 68-74 WALK AWAY (6s)
for i in range(144):
    t = i / FPS
    im = ART_NAV.copy(); d = ImageDraw.Draw(im, "RGBA")
    # ring goes dim
    fp = FR / f"a_{i:04d}.png"
    if fp.exists():
        continue
    d.ellipse([FORT[0]-RING_R, FORT[1]-RING_R, FORT[0]+RING_R, FORT[1]+RING_R],
              outline=(90, 100, 120, 200), width=4)
    p = min(1, t / 5.2)
    px, py = bez(1 - p * 0.85)
    d.ellipse([px-16, py-16, px+16, py+16], outline=AMBER + (120,), width=2)
    d.ellipse([px-9, py-9, px+9, py+9], fill=AMBER)
    d.rounded_rectangle([36, 28, 480, 96], radius=14, fill=CARD)
    d.text((60, 44), "Walk away. It stops.", font=F(FB, 30), fill=WHITE)
    im.save(fp)
mix_section([(NV / "n6.mp3", 0.3, None)] + chime_clips([0.6, 3.8]), 6, TMP / "away.aac")

# ================================================================ 74-79 END (5s)
for i in range(120):
    t = i / FPS
    im = title_card("Walk the city. Hear its stories.", "")
    fp = FR / f"e_{i:04d}.png"
    if fp.exists():
        continue
    if t > 4.2:  # gentle fade to black at the very end
        im = Image.blend(im, Image.new("RGB", (W, H), (0, 0, 0)), min(1, (t - 4.2) / 0.8))
    im.save(fp)
mix_section([(NV / "n7.mp3", 0.8, None)] + chime_clips([0.3]), 5, TMP / "end.aac")

# ---------------------------------------------------------------- assemble
def seg(pat, n, aac, out):
    run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", pat,
         "-i", aac, "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-ar", "22050", "-ac", "1", "-c:a", "aac", "-t", str(n / FPS), out])
seg(str(FR / "o_%04d.png"), 144, TMP / "open.aac", TMP / "v_o.mp4")
seg(str(FR / "w_%04d.png"), 324, TMP / "walk.aac", TMP / "v_w.mp4")
seg(str(FR / "l_%04d.png"), 96, TMP / "linger.aac", TMP / "v_l.mp4")
seg(str(FR / "s_%04d.png"), 720, TMP / "story.aac", TMP / "v_s.mp4")
seg(str(FR / "c_%04d.png"), 288, TMP / "scale.aac", TMP / "v_c.mp4")
seg(str(FR / "a_%04d.png"), 144, TMP / "away.aac", TMP / "v_a.mp4")
seg(str(FR / "e_%04d.png"), 120, TMP / "end.aac", TMP / "v_e.mp4")
with open(TMP / "list.txt", "w") as fh:
    for s in ["v_o", "v_w", "v_l", "v_s", "v_c", "v_a", "v_e"]:
        fh.write(f"file '{TMP/s}.mp4'\n")
run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
     "-i", str(TMP / "list.txt"), "-c", "copy", str(HERE / "sthala-demo-v6.mp4")])
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "csv=p=0", str(HERE / "sthala-demo-v6.mp4")], capture_output=True, text=True).stdout.strip())
print(f"DONE: sthala-demo-v6.mp4 {dur:.0f}s, {os.path.getsize(HERE/'sthala-demo-v6.mp4')/1e6:.1f} MB")
