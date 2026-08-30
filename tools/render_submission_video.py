#!/usr/bin/env python3
"""Render the deterministic five-minute ProofFix submission video and HTML player.

The renderer uses only Python's standard library plus ffmpeg/ffprobe. It reads the
frozen benchmark summary before generating any claims, creates six SVG scenes,
synthesizes local narration with ffmpeg's flite source, and produces an H.264/AAC
MP4 with burned-in captions. The companion HTML presentation has no network
dependencies and self-plays the same 300-second sequence.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


@dataclass(frozen=True)
class Scene:
    number: int
    title: str
    kicker: str
    duration: int
    narration: str


SCENES = [
    Scene(
        1,
        "The last-mile trap",
        "CASE-01 · Istio route mismatch",
        45,
        "It is three A M. Checkout traffic is failing with HTTP five oh threes. "
        "The Istio Virtual Service routes requests to subset V two, but the ready pods and "
        "Destination Rule expose only V one. A general AI assistant can produce a convincing "
        "diagnosis in seconds. That is not enough for an on-call engineer. Production recovery "
        "requires a bounded action, an executable rollback, live service-level verification, "
        "and evidence that supports every final claim. ProofFix turns incident response from a "
        "plausible chat answer into a verified state transition. It proves recovery before "
        "declaring victory.",
    ),
    Scene(
        2,
        "Recovery without proof",
        "Same fixture · Same model · Same evaluation",
        45,
        "On the left, the simple ReAct baseline inspects the route and patches V two to V one. "
        "Traffic returns. All three service-level windows pass. Yet the baseline exhausts its "
        "step budget without linking its critical conclusion to the exact observations and "
        "verification evidence in its ledger. Under strict Verified Recovery Success, that run "
        "fails evidence closure. On the right, ProofFix faces the identical frozen incident. "
        "The benchmark rewards safe and auditable recovery, not merely issuing a useful command. "
        "Across all three CASE zero one trials, ReAct scores zero of three while ProofFix scores "
        "three of three.",
    ),
    Scene(
        3,
        "The nine-stage evidence machine",
        "Purposeful orchestration, not an open-ended chat loop",
        75,
        "ProofFix operates through nine deterministic stages. Scope binds the namespace, budgets, "
        "and safety envelope. Observe collects structured Kubernetes resources, events, readiness, "
        "and live telemetry, while redacting Secrets before model context. Hypothesize creates "
        "competing causal explanations. Discriminate runs targeted tests instead of anchoring on "
        "the first plausible answer. Plan selects the smallest remediation and pairs it with an "
        "executable inverse. The Safety Gate rejects out-of-scope targets, forbidden operations, "
        "missing rollback, and data-loss risk. Execute applies only the approved change. Verify "
        "requires semantic fixture checks and three consecutive service-level windows. Close "
        "compiles the Incident Recovery Packet only when every critical claim points to exact "
        "evidence. Every observation, decision, and action is stored in an append-only S H A two "
        "fifty-six hash chain.",
    ),
    Scene(
        4,
        "Live CASE-01 recovery",
        "Minimal patch · Mandatory rollback · Three SLO windows",
        75,
        "For CASE zero one, structured observation finds sixteen relevant resources. The evidence "
        "shows that checkout traffic targets V two while only V one has ready pods and endpoints. "
        "ProofFix proposes one narrow patch: change the Virtual Service destination from V two to "
        "V one. The plan includes the exact inverse patch, so rollback is executable before any "
        "mutation occurs. Policy approves the namespace, target, operation, and rollback. After "
        "execution, ProofFix does not stop at a successful command. It sends one thousand live "
        "requests in each of three consecutive windows. Trial one records zero errors with P ninety "
        "five latency of eleven point six, ten point one, and eleven point four milliseconds, all "
        "well below the two-hundred millisecond limit. Workload readiness and semantic verification "
        "also pass. The final Incident Recovery Packet closes every claim against the immutable "
        "ledger, producing a strict Verified Recovery Success.",
    ),
    Scene(
        5,
        "Measured on 90 valid runs",
        "15 cases · 3 trials · 2 systems · 45 paired comparisons",
        35,
        "The frozen benchmark covers routing, scheduling, resource, authentication, messaging, "
        "storage, and a healthy-system abstention control. ProofFix reaches thirty-seven point "
        "eight percent Verified Recovery Success, versus twenty-six point seven percent for ReAct: "
        "an eleven point one percentage-point lift. Both systems record zero forbidden-action runs "
        "and one hundred percent safe abstention. All ninety selected trajectories verify across "
        "two thousand six hundred ninety-seven hash-chained events. The confidence interval includes "
        "zero and P equals zero point one two five, so this is promising measured improvement, not a "
        "statistically conclusive win.",
    ),
    Scene(
        6,
        "Trust the proof of recovery",
        "A production incident ends with evidence, not eloquence",
        25,
        "Our core insight is simple. Root-cause accuracy is a vanity metric when the service still "
        "needs safe recovery. The meaningful unit of agent reliability is a verified state "
        "transition: evidence closed, action admissible, blast radius bounded, rollback ready, and "
        "recovery proven under load. ProofFix is fully reproducible, with code, benchmark records, "
        "and agent trajectories in the tagged repository. Do not trust the diagnosis. Trust the "
        "proof of recovery.",
    ),
]


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def capture(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def validate_inputs() -> dict:
    summary = json.loads((ROOT / "artifacts/benchmark/summary.json").read_text())
    expected = {
        "valid_runs": 90,
        "pairs": 45,
        "verified_trajectories": 90,
        "events": 2697,
    }
    actual = {
        "valid_runs": summary["matrix"]["valid_runs"],
        "pairs": summary["matrix"]["pairs"],
        "verified_trajectories": summary["integrity"]["verified_trajectories"],
        "events": summary["integrity"]["events"],
    }
    if actual != expected:
        raise RuntimeError(f"Frozen benchmark mismatch: expected {expected}, got {actual}")
    if round(summary["paired_vrs"]["baseline_rate"] * 100, 1) != 26.7:
        raise RuntimeError("Unexpected baseline VRS")
    if round(summary["paired_vrs"]["proofix_rate"] * 100, 1) != 37.8:
        raise RuntimeError("Unexpected ProofFix VRS")
    return summary


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def rect(x: int, y: int, w: int, h: int, fill: str, radius: int = 24,
         stroke: str = "none", stroke_width: int = 0, opacity: float = 1) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity}"/>'
    )


def text(x: int, y: int, value: str, size: int = 40, fill: str = "#F4F7FB",
         weight: str = "normal", anchor: str = "start", family: str = "sans",
         max_chars: int | None = None, line_height: int | None = None) -> str:
    font = FONT_MONO if family == "mono" else (FONT_BOLD if weight == "bold" else FONT)
    lines = [value]
    if max_chars:
        lines = textwrap.wrap(value, max_chars, break_long_words=False, break_on_hyphens=False)
    line_height = line_height or int(size * 1.32)
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{esc(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return (
        f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{spans}</text>'
    )


def pill(x: int, y: int, label: str, fill: str, width: int) -> str:
    return rect(x, y, width, 48, fill, 24) + text(x + width // 2, y + 33, label, 22, "#07111F", "bold", "middle")


def terminal(x: int, y: int, w: int, h: int, title: str, lines: list[tuple[str, str]], accent: str) -> str:
    out = [rect(x, y, w, h, "#0B1424", 18, "#26344A", 2)]
    out.append(rect(x, y, w, 58, "#121F33", 18))
    out.append(f'<circle cx="{x+28}" cy="{y+29}" r="7" fill="#FF5A67"/>')
    out.append(f'<circle cx="{x+52}" cy="{y+29}" r="7" fill="#F2C94C"/>')
    out.append(f'<circle cx="{x+76}" cy="{y+29}" r="7" fill="#33D17A"/>')
    out.append(text(x + 105, y + 38, title, 22, "#C5D4E8", "bold", family="mono"))
    cursor_y = y + 100
    for line, color in lines:
        out.append(text(x + 28, cursor_y, line, 22, color, family="mono", max_chars=max(32, int(w / 14))))
        cursor_y += 42
    out.append(rect(x + 28, y + h - 35, 14, 24, accent, 2))
    return "".join(out)


def header(scene: Scene) -> str:
    return "".join([
        text(80, 80, "PROOF", 30, "#F4F7FB", "bold"),
        text(198, 80, "FIX", 30, "#36D1DC", "bold"),
        pill(1550, 44, f"SCENE {scene.number} / 6", "#36D1DC", 250),
        text(80, 160, scene.title, 62, "#F4F7FB", "bold"),
        text(82, 210, scene.kicker, 28, "#8FA8C4"),
    ])


def scene_body(scene: Scene, summary: dict) -> str:
    if scene.number == 1:
        return "".join([
            rect(80, 270, 790, 610, "#101C2F", 28, "#FF5A67", 3),
            pill(120, 310, "CRITICAL ALERT", "#FF5A67", 230),
            text(120, 405, "checkout ingress", 46, "#F4F7FB", "bold"),
            text(120, 462, "HTTP 503 SPIKE", 66, "#FF5A67", "bold"),
            text(120, 545, "VirtualService → subset v2", 30, "#C5D4E8", family="mono"),
            text(120, 592, "Ready backends → subset v1", 30, "#33D17A", family="mono"),
            rect(120, 660, 700, 150, "#0B1424", 18),
            text(155, 715, "Correct diagnosis", 28, "#F4F7FB", "bold"),
            text(470, 715, "≠", 40, "#FF5A67", "bold", "middle"),
            text(785, 715, "safe recovery", 28, "#F4F7FB", "bold", "end"),
            text(155, 770, "The missing last mile: proof", 28, "#36D1DC", "bold"),
            rect(930, 270, 890, 610, "#0E2030", 28, "#36D1DC", 3),
            text(1000, 360, "A production-grade agent must:", 38, "#F4F7FB", "bold"),
            text(1030, 450, "01  Bound the blast radius", 32, "#C5D4E8"),
            text(1030, 525, "02  Carry executable rollback", 32, "#C5D4E8"),
            text(1030, 600, "03  Verify live SLOs", 32, "#C5D4E8"),
            text(1030, 675, "04  Close every evidence claim", 32, "#C5D4E8"),
            rect(1000, 755, 750, 74, "#36D1DC", 18),
            text(1375, 805, "PROVE RECOVERY BEFORE VICTORY", 28, "#07111F", "bold", "middle"),
        ])
    if scene.number == 2:
        left = terminal(80, 280, 840, 570, "react-baseline · CASE-01 · trial 1", [
            ("$ inspect virtualservice checkout", "#8FA8C4"),
            ("route subset: v2  [missing]", "#FF5A67"),
            ("$ patch destination subset=v1", "#F4F7FB"),
            ("service traffic: RECOVERED", "#33D17A"),
            ("SLO windows: PASS / PASS / PASS", "#33D17A"),
            ("evidence closure: FAIL", "#FF5A67"),
            ("VRS: FAIL  ·  CASE total 0/3", "#FF5A67"),
        ], "#FF5A67")
        right = terminal(1000, 280, 840, 570, "proofix · CASE-01 · trial 1", [
            ("scope → observe → challenge", "#8FA8C4"),
            ("plan: v2 → v1 + inverse", "#F4F7FB"),
            ("policy gate: ALLOWED", "#33D17A"),
            ("service traffic: RECOVERED", "#33D17A"),
            ("SLO windows: PASS / PASS / PASS", "#33D17A"),
            ("evidence closure: PASS", "#33D17A"),
            ("VRS: PASS  ·  CASE total 3/3", "#33D17A"),
        ], "#36D1DC")
        return left + right + text(960, 925, "Same recovery signal. Different standard of proof.", 34, "#F4F7FB", "bold", "middle")
    if scene.number == 3:
        stages = ["SCOPE", "OBSERVE", "HYPOTHESIZE", "DISCRIMINATE", "PLAN", "SAFETY GATE", "EXECUTE", "VERIFY", "CLOSE"]
        colors = ["#36D1DC", "#55B7FF", "#7A9CFF", "#9B7BFF", "#C56CFF", "#F2C94C", "#FF9F43", "#33D17A", "#36D1DC"]
        out = [rect(80, 280, 1760, 325, "#0B1424", 26, "#26344A", 2)]
        for i, (label, color) in enumerate(zip(stages, colors)):
            x = 108 + i * 192
            out.append(f'<circle cx="{x+70}" cy="390" r="64" fill="{color}" opacity="0.18" stroke="{color}" stroke-width="4"/>')
            out.append(text(x + 70, 400, str(i + 1), 38, color, "bold", "middle"))
            out.append(text(x + 70, 505, label, 20, "#F4F7FB", "bold", "middle"))
            if i < 8:
                out.append(f'<path d="M {x+140} 390 L {x+178} 390" stroke="#52657D" stroke-width="4" marker-end="url(#arrow)"/>')
        cards = [
            (80, "BOUNDED TOOLS", "Typed Kubernetes reads and reversible mutations", "#55B7FF"),
            (530, "STRUCTURED MEMORY", "Immutable observations, hypotheses, and action ledger", "#9B7BFF"),
            (980, "VERIFICATION LOOPS", "Challengers, semantic checks, and three SLO windows", "#33D17A"),
            (1430, "CRYPTOGRAPHIC TRACE", "SHA-256 chain for every decision and tool response", "#36D1DC"),
        ]
        for x, title_value, body, color in cards:
            out.extend([
                rect(x, 675, 410, 235, "#101C2F", 22, color, 2),
                text(x + 28, 730, title_value, 24, color, "bold"),
                text(x + 28, 790, body, 24, "#C5D4E8", max_chars=28, line_height=36),
            ])
        return "".join(out)
    if scene.number == 4:
        left = terminal(80, 280, 890, 590, "proofix live trajectory", [
            ("[observe] 16 resources captured", "#8FA8C4"),
            ("[evidence] VS targets v2", "#F2C94C"),
            ("[evidence] v1 endpoints READY", "#33D17A"),
            ("[plan] patch v2 → v1", "#F4F7FB"),
            ("[rollback] patch v1 → v2", "#F4F7FB"),
            ("[policy] ALLOWED · scoped", "#33D17A"),
            ("[execute] virtualservice patched", "#36D1DC"),
            ("[close] evidence packet SIGNED", "#33D17A"),
        ], "#36D1DC")
        out = [left, rect(1030, 280, 810, 590, "#101C2F", 26, "#33D17A", 3),
               text(1080, 345, "LIVE SLO VERIFICATION", 31, "#33D17A", "bold")]
        values = [("WINDOW 1", "0 errors", "p95 11.6 ms"), ("WINDOW 2", "0 errors", "p95 10.1 ms"), ("WINDOW 3", "0 errors", "p95 11.4 ms")]
        for i, (label, errors, latency) in enumerate(values):
            y = 405 + i * 135
            out.extend([
                rect(1080, y, 710, 105, "#0B1424", 18),
                text(1115, y + 42, label, 23, "#8FA8C4", "bold"),
                text(1115, y + 78, errors, 27, "#33D17A", "bold"),
                text(1750, y + 66, latency, 28, "#F4F7FB", "bold", "end"),
            ])
        out.extend([
            rect(1080, 820, 710, 1, "#52657D", 0),
            pill(1080, 780, "VRS PASS · EVIDENCE CLOSED", "#33D17A", 710),
            text(960, 945, "3,000 live requests · rollback ready before mutation", 32, "#C5D4E8", "bold", "middle"),
        ])
        return "".join(out)
    if scene.number == 5:
        proofix_rate = summary["paired_vrs"]["proofix_rate"] * 100
        baseline_rate = summary["paired_vrs"]["baseline_rate"] * 100
        out = [rect(80, 270, 1760, 620, "#0B1424", 26, "#26344A", 2)]
        rows = [
            ("Verified Recovery Success", f"{baseline_rate:.1f}%  (12/45)", f"{proofix_rate:.1f}%  (17/45)", "+11.1 pp"),
            ("Forbidden-action runs", "0", "0", "SAFE"),
            ("CASE-15 safe abstention", "100%", "100%", "SAFE"),
            ("Median elapsed time", "179.1 s", "173.4 s", "−5.8 s"),
            ("Selected trajectory integrity", "45 / 45", "45 / 45", "90 / 90"),
        ]
        headers = ["METRIC", "REACT", "PROOFIX", "DELTA"]
        xs = [130, 990, 1290, 1600]
        for x, label in zip(xs, headers):
            out.append(text(x, 340, label, 24, "#8FA8C4", "bold"))
        out.append(rect(120, 370, 1680, 2, "#52657D", 0))
        for i, row in enumerate(rows):
            y = 440 + i * 88
            if i % 2 == 0:
                out.append(rect(110, y - 49, 1700, 70, "#101C2F", 12))
            colors = ["#F4F7FB", "#C5D4E8", "#33D17A", "#36D1DC"]
            for x, value, color in zip(xs, row, colors):
                out.append(text(x, y, value, 25, color, "bold" if x >= 1290 else "normal"))
        out.extend([
            pill(120, 825, "15 CASES", "#55B7FF", 250),
            pill(390, 825, "90 VALID RUNS", "#36D1DC", 300),
            pill(710, 825, "2,697 EVENTS", "#9B7BFF", 300),
            text(1770, 855, "95% CI [0.0, 22.2] pp  ·  p = 0.125", 25, "#F2C94C", "bold", "end"),
            text(960, 950, "Promising measured improvement · not a statistically conclusive win", 30, "#F4F7FB", "bold", "middle"),
        ])
        return "".join(out)
    return "".join([
        rect(180, 305, 1560, 440, "#0E2030", 34, "#36D1DC", 3),
        text(960, 405, "ROOT-CAUSE ACCURACY", 45, "#8FA8C4", "bold", "middle"),
        text(960, 485, "IS NOT THE FINISH LINE.", 68, "#F4F7FB", "bold", "middle"),
        text(960, 590, "THE UNIT OF RELIABILITY IS A", 42, "#8FA8C4", "bold", "middle"),
        text(960, 675, "VERIFIED STATE TRANSITION.", 68, "#36D1DC", "bold", "middle"),
        text(960, 825, "DON'T TRUST THE DIAGNOSIS. TRUST THE PROOF OF RECOVERY.", 36, "#33D17A", "bold", "middle"),
        text(960, 900, "github.com/CEORocks/proofix  ·  v1.0.0-iteration1", 28, "#C5D4E8", anchor="middle", family="mono"),
    ])


def build_svg(scene: Scene, summary: dict) -> str:
    background = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#07111F"/><stop offset="1" stop-color="#101C31"/></linearGradient>
  <radialGradient id="glow"><stop offset="0" stop-color="#36D1DC" stop-opacity=".13"/><stop offset="1" stop-color="#36D1DC" stop-opacity="0"/></radialGradient>
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#52657D"/></marker>
</defs>
<rect width="1920" height="1080" fill="url(#bg)"/>
<circle cx="1650" cy="100" r="570" fill="url(#glow)"/>
<path d="M0 1010 C 420 950, 650 1080, 1040 1010 S 1640 940, 1920 1010" fill="none" stroke="#36D1DC" stroke-opacity=".12" stroke-width="2"/>
"""
    footer = text(80, 1035, "micro1 FRONTIER ENGINEERING CHALLENGE 2026", 20, "#52657D", "bold") + text(1840, 1035, "PROOFIX", 20, "#52657D", "bold", "end")
    return background + header(scene) + scene_body(scene, summary) + footer + "</svg>\n"


def split_sentences(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]


def srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_subtitles(path: Path) -> None:
    entries: list[str] = []
    index = 1
    offset = 0.0
    for scene in SCENES:
        sentences = split_sentences(scene.narration)
        weights = [max(1, len(sentence.split())) for sentence in sentences]
        usable = scene.duration - 2.0
        cursor = offset + 0.7
        for sentence, weight in zip(sentences, weights):
            duration = usable * weight / sum(weights)
            end = min(offset + scene.duration - 0.5, cursor + duration)
            wrapped = "\n".join(textwrap.wrap(sentence, 72, break_long_words=False))
            entries.append(f"{index}\n{srt_time(cursor)} --> {srt_time(end)}\n{wrapped}\n")
            index += 1
            cursor = end
        offset += scene.duration
    path.write_text("\n".join(entries))


def html_scene(scene: Scene, summary: dict) -> str:
    if scene.number == 1:
        body = """<div class="grid two"><div class="panel danger"><span class="chip red">CRITICAL ALERT</span><h2>checkout ingress</h2><div class="huge red-text">HTTP 503</div><code>VirtualService → v2 [missing]</code><code class="good">Ready backends → v1</code></div><div class="panel"><h2>Production recovery requires</h2><ul><li>Bounded blast radius</li><li>Executable rollback</li><li>Live SLO verification</li><li>Evidence closure</li></ul><div class="banner">PROVE RECOVERY BEFORE VICTORY</div></div></div>"""
    elif scene.number == 2:
        body = """<div class="grid two"><div class="terminal danger"><b>react-baseline · CASE-01</b><pre>$ inspect virtualservice checkout
route subset: v2 [missing]
$ patch destination subset=v1
service traffic: <i>RECOVERED</i>
SLO windows: <i>PASS / PASS / PASS</i>
evidence closure: <em>FAIL</em>
VRS: <em>FAIL · 0/3</em></pre></div><div class="terminal success"><b>proofix · CASE-01</b><pre>scope → observe → challenge
plan: v2 → v1 + inverse
policy gate: <i>ALLOWED</i>
service traffic: <i>RECOVERED</i>
SLO windows: <i>PASS / PASS / PASS</i>
evidence closure: <i>PASS</i>
VRS: <i>PASS · 3/3</i></pre></div></div>"""
    elif scene.number == 3:
        labels = ["Scope", "Observe", "Hypothesize", "Discriminate", "Plan", "Safety Gate", "Execute", "Verify", "Close"]
        body = '<div class="stages">' + "".join(f'<div><span>{i}</span><b>{label}</b></div>' for i, label in enumerate(labels, 1)) + '</div><div class="grid four"><div class="panel small"><h3>Bounded tools</h3><p>Typed reads and reversible mutations</p></div><div class="panel small"><h3>Structured memory</h3><p>Immutable observations and hypotheses</p></div><div class="panel small"><h3>Verification loops</h3><p>Challengers, semantics, SLO windows</p></div><div class="panel small"><h3>Hash-chain trace</h3><p>Every decision and tool response</p></div></div>'
    elif scene.number == 4:
        body = """<div class="grid two"><div class="terminal success"><b>proofix live trajectory</b><pre>[observe] 16 resources captured
[evidence] VS targets v2
[evidence] v1 endpoints READY
[plan] patch v2 → v1
[rollback] patch v1 → v2
[policy] ALLOWED · scoped
[execute] virtualservice patched
[close] evidence packet SIGNED</pre></div><div class="panel success"><h2>LIVE SLO VERIFICATION</h2><div class="windows"><div><b>WINDOW 1</b><i>0 errors · p95 11.6 ms</i></div><div><b>WINDOW 2</b><i>0 errors · p95 10.1 ms</i></div><div><b>WINDOW 3</b><i>0 errors · p95 11.4 ms</i></div></div><div class="banner green">VRS PASS · EVIDENCE CLOSED</div></div></div>"""
    elif scene.number == 5:
        body = """<div class="panel metrics"><table><thead><tr><th>Metric</th><th>ReAct</th><th>ProofFix</th><th>Delta</th></tr></thead><tbody><tr><td>Verified Recovery Success</td><td>26.7% (12/45)</td><td>37.8% (17/45)</td><td>+11.1 pp</td></tr><tr><td>Forbidden-action runs</td><td>0</td><td>0</td><td>SAFE</td></tr><tr><td>CASE-15 abstention</td><td>100%</td><td>100%</td><td>SAFE</td></tr><tr><td>Median elapsed</td><td>179.1 s</td><td>173.4 s</td><td>−5.8 s</td></tr><tr><td>Trajectory integrity</td><td>45/45</td><td>45/45</td><td>90/90</td></tr></tbody></table><p class="note">95% CI [0.0, 22.2] pp · McNemar p=0.125 · Promising, not conclusive</p></div>"""
    else:
        body = """<div class="closing"><span>ROOT-CAUSE ACCURACY IS NOT THE FINISH LINE.</span><strong>THE UNIT OF RELIABILITY IS A<br>VERIFIED STATE TRANSITION.</strong><h2>DON'T TRUST THE DIAGNOSIS.<br>TRUST THE PROOF OF RECOVERY.</h2><code>github.com/CEORocks/proofix · v1.0.0-iteration1</code></div>"""
    return f'<section class="scene" data-duration="{scene.duration}"><header><div class="logo">PROOF<span>FIX</span></div><div class="scene-no">SCENE {scene.number} / 6</div><h1>{esc(scene.title)}</h1><p>{esc(scene.kicker)}</p></header><main>{body}</main><div class="caption">{esc(scene.narration)}</div></section>'


def write_html(path: Path, summary: dict) -> None:
    scenes = "\n".join(html_scene(scene, summary) for scene in SCENES)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ProofFix · 5-Minute Submission</title><style>
:root{{--bg:#07111f;--panel:#101c2f;--line:#26344a;--text:#f4f7fb;--muted:#8fa8c4;--cyan:#36d1dc;--green:#33d17a;--red:#ff5a67;--yellow:#f2c94c}}*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:Arial,sans-serif}}body:before{{content:"";position:fixed;inset:0;background:radial-gradient(circle at 90% 0,#36d1dc22,transparent 42%),linear-gradient(145deg,#07111f,#101c31);z-index:-1}}.scene{{display:none;position:absolute;inset:0;padding:4vh 4vw 10vh;opacity:0;transform:scale(.985)}}.scene.active{{display:block;animation:enter .8s ease forwards}}@keyframes enter{{to{{opacity:1;transform:scale(1)}}}}header{{position:relative}}.logo{{font-weight:900;font-size:2.1vw;letter-spacing:.04em}}.logo span{{color:var(--cyan)}}.scene-no{{position:absolute;right:0;top:0;padding:.7em 1.3em;background:var(--cyan);color:#07111f;border-radius:999px;font-weight:900}}h1{{font-size:3.7vw;margin:3vh 0 .3vh}}header>p{{margin:0;color:var(--muted);font-size:1.65vw}}main{{margin-top:5vh}}.grid{{display:grid;gap:3vw}}.two{{grid-template-columns:1fr 1fr}}.four{{grid-template-columns:repeat(4,1fr);margin-top:4vh}}.panel,.terminal{{background:#101c2fee;border:2px solid var(--line);border-radius:1.5vw;padding:2.2vw;min-height:49vh;box-shadow:0 20px 70px #0005}}.panel.danger,.terminal.danger{{border-color:var(--red)}}.panel.success,.terminal.success{{border-color:var(--green)}}.chip{{display:inline-block;border-radius:999px;padding:.55em 1em;font-weight:900;color:#07111f}}.red{{background:var(--red)}}.red-text,em{{color:var(--red)}}.huge{{font-size:5vw;font-weight:900;margin:2vh 0}}code,pre{{display:block;font:1.35vw/1.75 'DejaVu Sans Mono',monospace;color:#c5d4e8}}code.good,pre i{{color:var(--green);font-style:normal}}pre em{{font-style:normal}}h2{{font-size:2.2vw}}ul{{font-size:1.7vw;line-height:2.2}}.banner{{margin-top:4vh;padding:1.1em;background:var(--cyan);color:#07111f;text-align:center;border-radius:1vw;font-size:1.5vw;font-weight:900}}.banner.green{{background:var(--green)}}.stages{{display:grid;grid-template-columns:repeat(9,1fr);gap:1vw;padding:4vh 2vw;background:#0b1424;border:2px solid var(--line);border-radius:1.5vw}}.stages div{{text-align:center}}.stages span{{display:grid;place-items:center;margin:auto;width:4.5vw;height:4.5vw;border:3px solid var(--cyan);border-radius:50%;font-size:2vw;color:var(--cyan);font-weight:900}}.stages b{{display:block;margin-top:2vh;font-size:1vw}}.panel.small{{min-height:20vh;padding:1.5vw}}.panel.small h3{{color:var(--cyan);font-size:1.3vw}}.panel.small p{{color:#c5d4e8;font-size:1.15vw;line-height:1.5}}.windows div{{display:flex;justify-content:space-between;padding:1.2em;margin:1.2vh 0;background:#0b1424;border-radius:.8vw;font-size:1.35vw}}.windows i{{color:var(--green);font-style:normal}}.metrics{{min-height:52vh;padding:1.2vw 2vw}}table{{width:100%;border-collapse:collapse;font-size:1.35vw}}th,td{{padding:1.15em;text-align:left;border-bottom:1px solid var(--line)}}th{{color:var(--muted);text-transform:uppercase}}td:nth-child(3),td:nth-child(4){{color:var(--green);font-weight:900}}.note{{text-align:center;color:var(--yellow);font-size:1.3vw}}.closing{{text-align:center;padding:7vh 5vw;border:3px solid var(--cyan);border-radius:2vw;background:#0e2030cc}}.closing span{{font-size:2vw;color:var(--muted);font-weight:900}}.closing strong{{display:block;font-size:4.2vw;line-height:1.25;margin:3vh;color:var(--cyan)}}.closing h2{{color:var(--green)}}.caption{{display:none}}#controls{{position:fixed;left:4vw;right:4vw;bottom:2.5vh;display:flex;align-items:center;gap:1vw;z-index:10}}button{{background:var(--cyan);border:0;border-radius:999px;padding:.8em 1.3em;font-weight:900;color:#07111f;cursor:pointer}}#track{{height:10px;background:#26344a;border-radius:9px;flex:1;overflow:hidden;cursor:pointer}}#fill{{height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--green))}}#clock{{font:1vw monospace;color:#c5d4e8;min-width:8em}}#hint{{font-size:.95vw;color:var(--muted)}}
</style></head><body>{scenes}<div id="controls"><button id="toggle">PAUSE</button><button id="restart">RESTART</button><button id="full">FULLSCREEN</button><div id="track"><div id="fill"></div></div><div id="clock">00:00 / 05:00</div><div id="hint">Space: play/pause</div></div><script>
const scenes=[...document.querySelectorAll('.scene')],durations=scenes.map(x=>+x.dataset.duration),total=durations.reduce((a,b)=>a+b,0);let started=performance.now(),pausedAt=0,paused=false,offset=0,last=-1;function fmt(s){{s=Math.max(0,Math.min(total,s));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.floor(s%60)).padStart(2,'0')}}function locate(t){{let sum=0;for(let i=0;i<durations.length;i++){{if(t<sum+durations[i])return i;sum+=durations[i]}}return durations.length-1}}function render(){{const now=paused?pausedAt:(performance.now()-started)/1000+offset;const t=Math.min(total,now),i=locate(t);if(i!==last){{scenes.forEach((s,j)=>s.classList.toggle('active',j===i));last=i}}document.querySelector('#fill').style.width=(t/total*100)+'%';document.querySelector('#clock').textContent=fmt(t)+' / 05:00';if(t>=total&&!paused){{paused=true;pausedAt=total;document.querySelector('#toggle').textContent='PLAY'}}requestAnimationFrame(render)}}function toggle(){{if(paused){{started=performance.now();offset=pausedAt;paused=false;document.querySelector('#toggle').textContent='PAUSE'}}else{{pausedAt=(performance.now()-started)/1000+offset;paused=true;document.querySelector('#toggle').textContent='PLAY'}}}}document.querySelector('#toggle').onclick=toggle;document.querySelector('#restart').onclick=()=>{{started=performance.now();offset=0;pausedAt=0;paused=false;last=-1;document.querySelector('#toggle').textContent='PAUSE'}};document.querySelector('#full').onclick=()=>document.documentElement.requestFullscreen?.();document.querySelector('#track').onclick=e=>{{const r=e.currentTarget.getBoundingClientRect();offset=(e.clientX-r.left)/r.width*total;started=performance.now();pausedAt=offset;last=-1}};addEventListener('keydown',e=>{{if(e.code==='Space'){{e.preventDefault();toggle()}}if(e.key==='f')document.documentElement.requestFullscreen?.()}});render();
</script></body></html>"""
    path.write_text(doc)


def render_audio(scene: Scene, work: Path) -> Path:
    text_path = work / f"scene-{scene.number:02}.txt"
    raw_path = work / f"scene-{scene.number:02}-raw.wav"
    audio_path = work / f"scene-{scene.number:02}.wav"
    text_path.write_text(scene.narration)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         f"flite=textfile={text_path}:voice=slt", "-ar", "48000", "-ac", "2", str(raw_path)])
    raw_duration = float(capture(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", str(raw_path)]))
    target_voice = scene.duration - 1.4
    rate = max(0.65, raw_duration / target_voice)
    if rate > 2.0:
        raise RuntimeError(f"Narration for scene {scene.number} requires unsupported speed {rate:.2f}")
    filters = f"atempo={rate:.6f},apad,atrim=0:{scene.duration},afade=t=out:st={scene.duration-0.8}:d=0.8"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_path),
         "-af", filters, "-ar", "48000", "-ac", "2", str(audio_path)])
    return audio_path


def render_video(output: Path, build: Path, summary: dict) -> None:
    segment_paths: list[Path] = []
    for scene in SCENES:
        svg_path = build / f"scene-{scene.number:02}.svg"
        svg_path.write_text(build_svg(scene, summary))
        png_path = build / f"scene-{scene.number:02}.png"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(svg_path),
             "-vf", f"scale={W}:{H}", "-frames:v", "1", str(png_path)])
        audio_path = render_audio(scene, build)
        segment = build / f"scene-{scene.number:02}.mp4"
        fade_out = scene.duration - 0.7
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            "fade=t=in:st=0:d=0.55,"
            f"fade=t=out:st={fade_out}:d=0.7,"
            f"drawbox=x=0:y={H-10}:w='{W}*t/{scene.duration}':h=10:color=0x36D1DC@0.95:t=fill"
        )
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "30",
             "-i", str(png_path), "-i", str(audio_path), "-t", str(scene.duration), "-vf", vf,
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-tune", "stillimage", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(segment)])
        segment_paths.append(segment)
    concat = build / "concat.txt"
    concat.write_text("".join(f"file '{path}'\n" for path in segment_paths))
    raw_video = build / "submission-video-raw.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat), "-c", "copy", str(raw_video)])
    subtitle_path = build / "submission-video.srt"
    write_subtitles(subtitle_path)
    subtitle_filter = (
        f"subtitles={subtitle_path}:force_style='FontName=DejaVu Sans,FontSize=10,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H99000000,BorderStyle=3,Outline=1,"
        "Shadow=0,MarginV=18,Alignment=2'"
    )
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw_video),
         "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(output)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "submission_video.mp4")
    parser.add_argument("--html", type=Path, default=ROOT / "submission_video.html")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "artifacts/video-build")
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"Required executable not found: {tool}")
    summary = validate_inputs()
    args.build_dir.mkdir(parents=True, exist_ok=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    write_html(args.html, summary)
    if not args.html_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        render_video(args.output, args.build_dir, summary)
        duration = float(capture(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", str(args.output)]))
        if abs(duration - 300.0) > 0.1:
            raise RuntimeError(f"Expected 300-second output, got {duration:.3f}")
        print(f"Rendered {args.output} ({duration:.3f}s)")
    print(f"Rendered {args.html}")


if __name__ == "__main__":
    main()
