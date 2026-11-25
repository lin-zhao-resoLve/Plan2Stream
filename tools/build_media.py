#!/usr/bin/env python3
"""Encode the Plan2Stream project-page media and write docs/media.json.

Reads tools/sources.json (the explicit, reproducible pick list), encodes every
asset into a *flat* media/ directory (GitHub Release assets have a flat
namespace) and writes docs/media.json describing it.  Outputs that already
exist with a nonzero size are skipped unless --force is given.

Requires only the ffmpeg / ffprobe CLIs and the Python standard library.

Usage: python3 tools/build_media.py [--force] [--workers 16]
"""
from __future__ import annotations

import argparse
import array
import datetime as dt
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
TASK_ORDER = ["T2V", "IT2V", "TA2V", "ITA2V", "T2AV", "IT2AV", "TA2AV", "ITA2AV"]
RELEASE = {"owner": "lin-zhao-resoLve", "repo": "Plan2Stream", "tag": "assets-v1"}
FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
WAVE_POINTS = 160
WALL_START_S = 2.0
WALL_LEN_S = 6.0


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def ffprobe(path: Path) -> dict[str, Any]:
    """Return ffprobe stream/format info for a media file."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)  # type: ignore[no-any-return]


def has_stream(info: dict[str, Any], kind: str) -> bool:
    """True if the probed file has at least one stream of the given codec_type."""
    return any(s.get("codec_type") == kind for s in info.get("streams", []))


def duration_of(info: dict[str, Any]) -> float:
    """Container duration in seconds."""
    return float(info["format"]["duration"])


def done(path: Path) -> bool:
    """True if path exists with nonzero size."""
    return path.exists() and path.stat().st_size > 0


def run_ffmpeg(args: list[str], out: Path) -> None:
    """Run ffmpeg writing to a temp sibling of `out`, then atomically rename."""
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    try:
        subprocess.run(FF + args + [str(tmp)], capture_output=True, text=True, check=True)
        tmp.replace(out)
    except subprocess.CalledProcessError as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed for {out.name}: {exc.stderr.strip()[-400:]}") from exc


# --------------------------------------------------------------------------- #
# Encoders
# --------------------------------------------------------------------------- #
def enc_item_video(src: Path, out: Path, with_audio: bool) -> None:
    """Item video: the original bitstream (no re-encode), first video + audio stream, moov atom up front.

    Sources are H.264 yuv420p (+ AAC), which browsers play as-is.
    """
    args = ["-i", str(src), "-map", "0:v:0"]
    if with_audio:
        args += ["-map", "0:a:0"]
    args += ["-c", "copy", "-movflags", "+faststart"]
    args += [] if with_audio else ["-an"]
    run_ffmpeg(args, out)


def enc_still(src: Path, out: Path, width: int, seek: float) -> None:
    """Single JPEG frame at `seek` seconds (0 for images), width capped at `width`."""
    run_ffmpeg(
        (["-ss", f"{seek}"] if seek > 0 else []) + ["-i", str(src), "-frames:v", "1",
         "-vf", f"scale='min({width},iw)':-2", "-q:v", "4"],
        out,
    )


def enc_audio(src: Path, out: Path) -> None:
    """Input audio -> AAC 96k m4a."""
    run_ffmpeg(["-i", str(src), "-vn", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"], out)


NATIVE = "trunc(iw/2)*2:trunc(ih/2)*2"   # keep the source resolution (even dims)
HALF = "trunc(iw/4)*2:trunc(ih/4)*2"     # half width/height = planner resolution


def enc_wall(src: Path, out: Path, start: float, scale: str, fps: int, with_audio: bool = False,
             length: float = WALL_LEN_S, crf: int = 22) -> None:
    """Wall tile segment of `length` s at `fps`, scaled by the ffmpeg `scale` expression.

    The streamed tile is the native-resolution output and keeps the source audio (AAC 96k)
    so the page can play it on hover; the planner tile is always silent.
    """
    audio = ["-map", "0:a:0", "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2"] if with_audio else ["-an"]
    run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", str(src), "-map", "0:v:0",
         "-vf", f"scale={scale},fps={fps},format=yuv420p",
         "-c:v", "libx264", "-profile:v", "high", "-crf", f"{crf}", "-preset", "slow",
         "-maxrate", "5M", "-bufsize", "10M"]  # cap high-motion tiles; resolution unchanged
        + audio + ["-movflags", "+faststart"],
        out,
    )


SPRITE = {"step": 60, "cols": 10, "w": 192, "h": 108}  # hour-scale scrub previews: one frame per minute
SPRITE_MIN = {"step": 10, "cols": 10, "w": 192, "h": 108}  # minute-scale scrub previews: one frame per 10 s


def sprite_count(duration: float, sprite: dict[str, int] = SPRITE) -> int:
    """Frames at 0, step, 2*step, ... strictly before the end (a frame at t == duration does not exist)."""
    return max(1, -(-int(round(duration * 1000)) // (sprite["step"] * 1000)))


def remux(src: Path, out: Path, end: float | None = None) -> None:
    """Lossless copy (no re-encode) with the moov atom up front for fast start and seeking.

    `end` keeps only the first `end` seconds (stream copy; the cut starts on the first keyframe).
    """
    run_ffmpeg(["-i", str(src)] + (["-t", f"{end}"] if end else []) + ["-map", "0", "-c", "copy", "-movflags", "+faststart"],
               out)


def enc_sprite(src: Path, out: Path, duration: float, sprite: dict[str, int] = SPRITE) -> None:
    """Grid of one thumbnail every sprite['step'] s (keyframes only, so an hour decodes quickly)."""
    count = sprite_count(duration, sprite)
    rows = -(-count // sprite["cols"])
    run_ffmpeg(["-skip_frame", "nokey", "-t", f"{duration}", "-i", str(src), "-an",
                "-vf", f"fps=1/{sprite['step']},scale={sprite['w']}:{sprite['h']},setsar=1,"
                       f"tile={sprite['cols']}x{rows}",
                "-frames:v", "1", "-q:v", "4"], out)


def waveform(path: Path, points: int = WAVE_POINTS) -> list[float]:
    """Normalized (0..1) peak envelope of the audio track, `points` values."""
    raw = subprocess.run(
        FF[:-1] + ["-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    n = len(samples)
    if n == 0:
        return [0.0] * points
    peaks: list[float] = []
    for i in range(points):
        chunk = samples[i * n // points: max((i + 1) * n // points, i * n // points + 1)]
        peaks.append(float(max(abs(v) for v in chunk)) if chunk else 0.0)
    top = max(peaks) or 1.0
    return [round(p / top, 3) for p in peaks]


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #
def clip(text: str, limit: int) -> str:
    """Trim text to `limit` chars at a word boundary, adding an ellipsis."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


def first_sentence(text: str) -> str:
    """First sentence of a plain text block."""
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


def sentence(text: str) -> str:
    """Ensure text ends with terminal punctuation."""
    text = text.strip()
    return text if not text or text[-1] in ".!?" else text + "."


def parse_prompt(raw: Optional[str]) -> dict[str, Any]:
    """Return {'scene','prompt','speech'} from a JSON-string or plain-text prompt."""
    if not raw:
        return {"scene": "", "prompt": "", "speech": None}
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        obj = None
    if not isinstance(obj, dict):
        text = re.sub(r"\s+", " ", raw).strip()
        return {"scene": first_sentence(text), "prompt": text, "speech": None}
    scene = str(obj.get("scene") or "").strip()
    parts = [sentence(scene)]
    if obj.get("actions"):
        parts.append(sentence(str(obj["actions"])))
    cam = ", ".join(str(obj[k]).replace("_", " ") for k in ("camera", "camera_motion") if obj.get(k))
    if cam:
        parts.append(f"Camera: {cam}.")
    speech: Optional[str] = None
    audio = obj.get("audio")
    if isinstance(audio, dict):
        tr = str(audio.get("transcript") or "").strip()
        if tr:
            speech = tr
        else:
            quotes = re.findall(r"[\"“]([^\"”]{3,})[\"”]", str(audio.get("description") or ""))
            if quotes:
                speech = " ".join(quotes)
    elif isinstance(audio, str):
        quotes = re.findall(r"[\"“]([^\"”]{3,})[\"”]", audio)
        if quotes:
            speech = " ".join(quotes)
    if speech:
        speech = "“" + clip(speech.strip("\"“” "), 300) + "”"
    return {"scene": scene, "prompt": " ".join(p for p in parts if p), "speech": speech}


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
Job = tuple[str, Callable[[], None]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", type=Path, default=ROOT / "tools" / "sources.json")
    ap.add_argument("--media-dir", type=Path, default=ROOT / "media")
    ap.add_argument("--manifest", type=Path, default=ROOT / "docs" / "media.json")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--force", action="store_true", help="re-encode outputs that already exist")
    args = ap.parse_args()

    media: Path = args.media_dir
    media.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, Any]] = json.loads(args.sources.read_text())
    # Wall slots follow the order in sources.json (grid position), not the task grouping below.
    # A source may pin its tile with "wall_slot": N; the others fill the remaining slots in list order.
    wall_srcs = [x for x in sources if x["role"] in ("wall", "both")]
    fixed = {x["id"]: int(x["wall_slot"]) for x in wall_srcs if "wall_slot" in x}
    if len(set(fixed.values())) != len(fixed) or not all(1 <= n <= len(wall_srcs) for n in fixed.values()):
        raise SystemExit(f"invalid wall_slot values: {fixed}")
    free = iter(n for n in range(1, len(wall_srcs) + 1) if n not in fixed.values())
    wall_slot = {x["id"]: f"wall-{fixed.get(x['id']) or next(free):02d}" for x in wall_srcs}
    # Demo order: by task, then optional "demo_rank" (defaults to the position in sources.json).
    pos = {id(src_): n for n, src_ in enumerate(sources)}
    sources.sort(key=lambda s: (TASK_ORDER.index(s["task"]), s.get("demo_rank", pos[id(s)])))

    # A source whose generation dir was archived off this machine falls back to the page's own copy:
    # item/hour/minute media are lossless stream copies of the source, and a wall-only tile can only be
    # kept as already built. "off" sources without a source are skipped (they produce nothing).
    srcs: dict[str, Path] = {}
    probes: dict[str, dict[str, Any]] = {}
    for s in sources:
        sid = s["id"]
        src = Path(s["source_video"])
        if not src.exists():
            copy = media / (f"{wall_slot[sid]}.mp4" if s["role"] == "wall" else f"{sid}.mp4")
            if not done(copy):
                if s["role"] == "off":
                    continue
                raise SystemExit(f"{sid}: source {src} is missing and has no built page copy; restore it from S3")
            src = copy
        srcs[sid] = src
        probes[sid] = ffprobe(src)

    jobs: list[Job] = []

    def want(name: str) -> bool:
        return args.force or not done(media / name)

    def add(name: str, fn: Callable[[], None]) -> None:
        if want(name):
            jobs.append((name, fn))

    wall_entries: list[dict[str, object]] = []
    for s in sources:
        sid, task = s["id"], s["task"]
        if sid not in probes:  # "off" source that is no longer available
            continue
        src = srcs[sid]
        info = probes[sid]
        audio = has_stream(info, "audio")
        if s["role"] in ("item", "both"):  # role "wall": hero-wall tile only, not a demo item
            add(f"{sid}.mp4", lambda src=src, sid=sid, audio=audio: enc_item_video(src, media / f"{sid}.mp4", audio))
            add(f"{sid}.jpg", lambda src=src, sid=sid: enc_still(src, media / f"{sid}.jpg", 960, 1.0))
            if "I" in task.split("2")[0]:
                if s.get("input_image"):
                    add(f"{sid}-input.jpg",
                        lambda p=Path(s["input_image"]), sid=sid: enc_still(p, media / f"{sid}-input.jpg", 640, 0.0))
                else:
                    add(f"{sid}-input.jpg",
                        lambda src=src, sid=sid: enc_still(src, media / f"{sid}-input.jpg", 640, 0.0))
            if task in ("TA2AV", "ITA2AV") and s.get("input_audio"):
                add(f"{sid}-input.m4a",
                    lambda p=Path(s["input_audio"]), sid=sid: enc_audio(p, media / f"{sid}-input.m4a"))
        if s["role"] in ("wall", "both"):
            wid = wall_slot[sid]
            if src == media / f"{wid}.mp4" and any(want(f) for f in (f"{wid}.mp4", f"{wid}-plan.mp4", f"{wid}.jpg")):
                raise SystemExit(f"{sid}: wall tile {wid} needs its source {s['source_video']}; restore it from S3")
            if "wall_start" in s:  # explicit segment start (seconds) for this tile
                start = float(s["wall_start"])
            else:
                start = WALL_START_S if duration_of(info) >= WALL_START_S + WALL_LEN_S else 0.0
            length = float(s.get("wall_len", WALL_LEN_S))
            # Real planner output ("future conditioning") when available; otherwise the
            # plan tile is simulated by downsampling the final video.
            plan_src = Path(s["wall_plan_video"]) if s.get("wall_plan_video") else src
            # Streamed tile: native output resolution, 24 fps. Planner tile: the real planner output at
            # its native resolution when given, else the output downsampled to planner resolution.
            plan_scale = NATIVE if s.get("wall_plan_video") else HALF
            add(f"{wid}.mp4", lambda src=src, wid=wid, start=start, audio=audio, length=length:
                enc_wall(src, media / f"{wid}.mp4", start, NATIVE, 24, audio, length, 22))
            add(f"{wid}-plan.mp4", lambda plan_src=plan_src, wid=wid, start=start, length=length, ps=plan_scale:
                enc_wall(plan_src, media / f"{wid}-plan.mp4", start, ps, 12, False, length, 24))
            add(f"{wid}.jpg", lambda src=src, wid=wid, start=start: enc_still(src, media / f"{wid}.jpg", 960, start))
            wall_entries.append({"id": wid, "src": f"{wid}.mp4", "plan": f"{wid}-plan.mp4",
                                 "poster": f"{wid}.jpg", "task": task, "has_audio": audio,
                                 "real_plan": bool(s.get("wall_plan_video"))})
        if s["role"] == "hour":  # hour-scale demo: lossless remux + poster + per-minute sprite
            dur = duration_of(info)
            add(f"{sid}.mp4", lambda src=src, sid=sid: remux(src, media / f"{sid}.mp4"))
            add(f"{sid}.jpg", lambda src=src, sid=sid: enc_still(src, media / f"{sid}.jpg", 960, 60.0))
            add(f"{sid}-sprite.jpg", lambda src=src, sid=sid, dur=dur: enc_sprite(src, media / f"{sid}-sprite.jpg", dur))
        if s["role"] == "minute":  # minute-scale demo: lossless copy (optionally only the first trim_end s) + sprite
            end = float(s["trim_end"]) if s.get("trim_end") else None
            dur = min(duration_of(info), end or float("inf"))
            add(f"{sid}.mp4", lambda src=src, sid=sid, end=end: remux(src, media / f"{sid}.mp4", end))
            add(f"{sid}.jpg", lambda src=src, sid=sid: enc_still(src, media / f"{sid}.jpg", 960, 0.0))  # = first frame
            add(f"{sid}-sprite.jpg", lambda src=src, sid=sid, dur=dur:
                enc_sprite(src, media / f"{sid}-sprite.jpg", dur, SPRITE_MIN))

    failures: list[str] = []

    def run(job: Job) -> None:
        name, fn = job
        try:
            fn()
            print(f"ok    {name}", flush=True)
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append(f"{name}: {exc}")
            print(f"FAIL  {name}: {exc}", file=sys.stderr, flush=True)

    print(f"{len(jobs)} outputs to encode ({args.workers} workers)")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, jobs))

    # Manifest ---------------------------------------------------------------
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for s in sources:
        sid, task = s["id"], s["task"]
        if s["role"] not in ("item", "both"):  # wall-only, hour-scale and "off" sources are not demos
            continue
        out = media / f"{sid}.mp4"
        if not done(out):
            continue
        info = ffprobe(out)
        vstream = next(x for x in info["streams"] if x["codec_type"] == "video")
        audio = has_stream(info, "audio")
        pp = parse_prompt(s.get("prompt"))
        has_img = "I" in task.split("2")[0]
        first_frame = has_img and not s.get("input_image")
        in_audio = f"{sid}-input.m4a" if task in ("TA2AV", "ITA2AV") and done(media / f"{sid}-input.m4a") else None
        items.append({
            "id": sid,
            "task": task,
            "seconds": round(duration_of(info), 2),
            "width": int(vstream["width"]),
            "height": int(vstream["height"]),
            "src": f"{sid}.mp4",
            "poster": f"{sid}.jpg",
            "has_audio": audio,
            "title": s.get("title") or sid,
            "caption": s.get("caption") or clip(pp["scene"] or pp["prompt"], 160),  # sources.json may override
            "input_image": f"{sid}-input.jpg" if has_img and done(media / f"{sid}-input.jpg") else None,
            "input_image_is_first_frame": first_frame,
            "input_audio": in_audio,
            "input_audio_is_output_audio": task in ("TA2V", "ITA2V"),
            "waveform": waveform(out) if audio else None,
        })
        counts[task] = counts.get(task, 0) + 1

    wall_entries.sort(key=lambda w: str(w["id"]))
    wall = [w for w in wall_entries if all(done(media / str(w[k])) for k in ("src", "plan", "poster"))]
    hour: list[dict[str, Any]] = []
    for s in sources:
        sid = s["id"]
        if s["role"] != "hour" or not all(done(media / f) for f in (f"{sid}.mp4", f"{sid}.jpg", f"{sid}-sprite.jpg")):
            continue
        info = ffprobe(media / f"{sid}.mp4")
        dur = duration_of(info)
        hour.append({
            "id": sid, "task": s["task"], "seconds": round(dur, 2),
            "src": f"{sid}.mp4", "poster": f"{sid}.jpg", "has_audio": has_stream(info, "audio"),
            "title": s.get("title") or sid, "caption": s.get("caption") or "",
            "sprite": dict(SPRITE, src=f"{sid}-sprite.jpg", count=sprite_count(dur)),
        })
    hour.sort(key=lambda h: str(h["id"]))
    minute: list[dict[str, Any]] = []
    for s in sources:
        sid = s["id"]
        if s["role"] != "minute" or not all(done(media / f) for f in (f"{sid}.mp4", f"{sid}.jpg", f"{sid}-sprite.jpg")):
            continue
        info = ffprobe(media / f"{sid}.mp4")
        dur = duration_of(info)
        minute.append({
            "id": sid, "task": s["task"], "seconds": round(dur, 2),
            "src": f"{sid}.mp4", "poster": f"{sid}.jpg", "has_audio": has_stream(info, "audio"),
            "title": s.get("title") or sid, "caption": s.get("caption") or "",
            "sprite": dict(SPRITE_MIN, src=f"{sid}-sprite.jpg", count=sprite_count(dur, SPRITE_MIN)),
        })
    mrank = {s["id"]: s.get("minute_rank", 99) for s in sources if s["role"] == "minute"}  # tab order (sources.json)
    minute.sort(key=lambda h: (mrank.get(h["id"], 99), str(h["id"])))
    # Project film (rendered separately in plan2stream-film; copied in as media/plan2stream-film.mp4 + .jpg poster).
    film = None
    film_path = media / "plan2stream-film.mp4"
    if film_path.exists():
        secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(film_path)], capture_output=True, text=True, check=True).stdout.strip())
        film = {"src": film_path.name, "poster": "plan2stream-film.jpg", "seconds": round(secs, 2), "title": "Plan2Stream"}
    manifest = {
        "release": RELEASE,
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wall": wall,
        "items": items,
        "minute": minute,
        "hour": hour,
    }
    if film:
        manifest["film"] = film
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {args.manifest}: {len(items)} items, {len(wall)} wall tiles; per task {counts}")
    if failures:
        print(f"{len(failures)} failures", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
