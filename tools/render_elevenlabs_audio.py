#!/usr/bin/env python3
"""Replace the submission video's narration with scene-aligned ElevenLabs TTS.

The API key is accepted only through ELEVENLABS_API_KEY. It is never written to
disk or included in generated metadata. Scene text is extracted directly from
the six Voiceover Narration blocks in docs/VIDEO_SCRIPT.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCENE_DURATIONS = (45.0, 45.0, 75.0, 75.0, 35.0, 25.0)


@dataclass(frozen=True)
class SceneAudio:
    number: int
    duration: float
    text: str


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def capture(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def media_duration(path: Path) -> float:
    return float(
        capture(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ]
        )
    )


def extract_scene_text(script_path: Path) -> list[SceneAudio]:
    markdown = script_path.read_text()
    sections = re.findall(
        r"(?ms)^### Scene (\d+):(.*?)(?=^### Scene \d+:|\Z)", markdown
    )
    if len(sections) != 6:
        raise RuntimeError(f"Expected six scene headings, found {len(sections)}")

    scenes: list[SceneAudio] = []
    for number, duration in enumerate(SCENE_DURATIONS, 1):
        section_number, section = sections[number - 1]
        if int(section_number) != number:
            raise RuntimeError(f"Expected Scene {number}, found Scene {section_number}")
        match = re.search(
            r"(?ms)^- \*\*Voiceover Narration[^\n]*\*\*\s*$\n"
            r"(.*?)^- \*\*On-Screen Callouts:\*\*",
            section,
        )
        if not match:
            raise RuntimeError(f"Unable to extract Scene {number} narration")
        quoted_lines: list[str] = []
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if not stripped.startswith(">"):
                continue
            value = stripped[1:].strip()
            if value:
                quoted_lines.append(value)
        narration = " ".join(quoted_lines)
        narration = re.sub(r"[*`]", "", narration)
        narration = re.sub(r"\s+", " ", narration).strip()
        if narration.startswith('"') and narration.endswith('"'):
            narration = narration[1:-1]
        scenes.append(SceneAudio(number=number, duration=duration, text=narration))
    return scenes


def load_narration_json(path: Path) -> list[SceneAudio]:
    data = json.loads(path.read_text())
    scenes = [
        SceneAudio(
            number=int(item["scene"]),
            duration=float(item["duration"]),
            text=str(item["text"]),
        )
        for item in data
    ]
    expected = list(range(1, 7))
    if [scene.number for scene in scenes] != expected:
        raise RuntimeError("Narration JSON must contain Scenes 1 through 6 in order")
    if tuple(scene.duration for scene in scenes) != SCENE_DURATIONS:
        raise RuntimeError("Narration JSON scene durations do not match the frozen timeline")
    return scenes


def synthesize(
    scene: SceneAudio,
    output: Path,
    *,
    api_key: str,
    voice_id: str,
    model_id: str,
    stability: float,
    similarity_boost: float,
    style: float,
    speed: float,
    previous_text: str | None,
    next_text: str | None,
) -> None:
    payload: dict[str, object] = {
        "text": scene.text,
        "model_id": model_id,
        "seed": 2026 + scene.number,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": True,
            "speed": speed,
        },
    }
    if previous_text:
        payload["previous_text"] = previous_text[-1000:]
    if next_text:
        payload["next_text"] = next_text[:1000]
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        "?output_format=mp3_44100_128",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "xi-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            audio = response.read()
    except urllib.error.HTTPError as error:
        message = error.read().decode(errors="replace")
        raise RuntimeError(
            f"ElevenLabs Scene {scene.number} request failed with HTTP "
            f"{error.code}: {message[:500]}"
        ) from error
    if len(audio) < 1000:
        raise RuntimeError(f"Scene {scene.number} returned an unexpectedly small response")
    output.write_bytes(audio)


def atempo_chain(rate: float) -> str:
    factors: list[float] = []
    remaining = rate
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.8f}" for factor in factors)


def fit_scene(
    source: Path, output: Path, duration: float, max_tempo_rate: float
) -> dict[str, float]:
    source_duration = media_duration(source)
    lead_in = 0.22
    tail = 0.38
    speech_target = duration - lead_in - tail
    tempo_rate = max(1.0, source_duration / speech_target)
    if tempo_rate > max_tempo_rate:
        raise RuntimeError(
            f"Narration needs {tempo_rate:.3f}x tempo to fit {duration:.0f}s; "
            f"shorten the script or raise --max-tempo-rate"
        )
    speech_seconds = source_duration / tempo_rate
    filters = (
        f"{atempo_chain(tempo_rate)},"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"adelay={round(lead_in * 1000)}|{round(lead_in * 1000)},"
        f"apad,atrim=0:{duration},"
        "afade=t=in:st=0:d=0.12,"
        f"afade=t=out:st={duration-tail}:d={tail}"
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            filters,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    fitted_duration = media_duration(output)
    return {
        "source_seconds": round(source_duration, 3),
        "target_seconds": duration,
        "tempo_rate": round(tempo_rate, 4),
        "speech_seconds": round(speech_seconds, 3),
        "tail_silence_seconds": round(duration - lead_in - speech_seconds, 3),
        "fitted_seconds": round(fitted_duration, 3),
    }


def mux_video(video: Path, narration: Path, output: Path, voice_name: str) -> float:
    video_duration = media_duration(video)
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-i",
            str(narration),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-af",
            f"apad,atrim=0:{video_duration}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-metadata:s:a:0",
            f"title=ElevenLabs {voice_name} narration",
            "-metadata:s:a:0",
            "language=eng",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return media_duration(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--script", type=Path, default=ROOT / "docs/VIDEO_SCRIPT.md"
    )
    parser.add_argument("--narration-json", type=Path)
    parser.add_argument(
        "--video", type=Path, default=ROOT / "submission_video.mp4"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/video-build/final_submission_video.mp4",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=ROOT / "artifacts/video-build/elevenlabs",
    )
    parser.add_argument("--voice-id", default="pNInz6obpgDQGcFmaJgB")
    parser.add_argument("--voice-name", default="Adam")
    parser.add_argument("--model-id", default="eleven_multilingual_v2")
    parser.add_argument("--stability", type=float, default=0.68)
    parser.add_argument("--similarity-boost", type=float, default=0.86)
    parser.add_argument("--style", type=float, default=0.0)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-tempo-rate", type=float, default=1.12)
    parser.add_argument("--reuse-sources", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key and not args.reuse_sources:
        raise SystemExit("ELEVENLABS_API_KEY is required")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scenes = (
        load_narration_json(args.narration_json)
        if args.narration_json
        else extract_scene_text(args.script)
    )
    report: dict[str, object] = {
        "voice_id": args.voice_id,
        "voice_name": args.voice_name,
        "model_id": args.model_id,
        "voice_settings": {
            "stability": args.stability,
            "similarity_boost": args.similarity_boost,
            "style": args.style,
            "speed": args.speed,
        },
        "scene_durations": list(SCENE_DURATIONS),
        "scenes": [],
    }
    fitted_paths: list[Path] = []
    for index, scene in enumerate(scenes):
        source = args.work_dir / f"scene-{scene.number:02}-source.mp3"
        fitted = args.work_dir / f"scene-{scene.number:02}-fitted.wav"
        if not args.reuse_sources or not source.exists():
            synthesize(
                scene,
                source,
                api_key=api_key or "",
                voice_id=args.voice_id,
                model_id=args.model_id,
                stability=args.stability,
                similarity_boost=args.similarity_boost,
                style=args.style,
                speed=args.speed,
                previous_text=scenes[index - 1].text if index else None,
                next_text=scenes[index + 1].text if index + 1 < len(scenes) else None,
            )
        timing = fit_scene(source, fitted, scene.duration, args.max_tempo_rate)
        timing.update(
            {
                "scene": scene.number,
                "words": len(scene.text.split()),
                "source_file": source.name,
                "fitted_file": fitted.name,
            }
        )
        report["scenes"].append(timing)
        fitted_paths.append(fitted)
        print(
            f"Scene {scene.number}: {timing['source_seconds']}s -> "
            f"{scene.duration:.0f}s (tempo {timing['tempo_rate']}x)"
        )

    concat_file = args.work_dir / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{path.resolve()}'\n" for path in fitted_paths)
    )
    narration = args.work_dir / "elevenlabs-narration.wav"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(narration),
        ]
    )
    report["narration_seconds"] = round(media_duration(narration), 3)
    output_duration = mux_video(args.video, narration, args.output, args.voice_name)
    report["output_seconds"] = round(output_duration, 3)
    report["output_file"] = str(args.output)
    report_path = args.work_dir / "render-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    if abs(output_duration - media_duration(args.video)) > 0.05:
        raise RuntimeError("Output duration drifted from the source video")
    print(f"Rendered {args.output} ({output_duration:.3f}s)")
    print(f"Timing report: {report_path}")


if __name__ == "__main__":
    main()
