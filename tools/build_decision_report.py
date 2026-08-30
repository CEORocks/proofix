from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "proofix-winning-problem-and-execution-plan.pdf"


NAVY = colors.HexColor("#17233D")
INK = colors.HexColor("#263247")
MUTED = colors.HexColor("#65728A")
CORAL = colors.HexColor("#F26B5E")
TEAL = colors.HexColor("#18A999")
PALE = colors.HexColor("#F2F5F9")
PALE_CORAL = colors.HexColor("#FFF1EE")
WHITE = colors.white
LINE = colors.HexColor("#D9E0E8")


def register_fonts() -> tuple[str, str, str]:
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf"),
    ]
    for regular, bold, italic in candidates:
        if all(Path(p).exists() for p in (regular, bold, italic)):
            pdfmetrics.registerFont(TTFont("ReportRegular", regular))
            pdfmetrics.registerFont(TTFont("ReportBold", bold))
            pdfmetrics.registerFont(TTFont("ReportItalic", italic))
            return "ReportRegular", "ReportBold", "ReportItalic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


REG, BOLD, ITALIC = register_fonts()


class ReportDoc(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=letter,
            leftMargin=0.66 * inch,
            rightMargin=0.66 * inch,
            topMargin=0.62 * inch,
            bottomMargin=0.58 * inch,
            title="ProofFix: Winning Problem Definition and Execution Plan",
            author="micro1 Frontier Engineering Challenge 2026",
            subject="Evidence-closed Kubernetes incident recovery agent decision brief",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        self.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=self._page)])

    def _page(self, canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(self.leftMargin, letter[1] - 0.40 * inch, letter[0] - self.rightMargin, letter[1] - 0.40 * inch)
        canvas.setFont(REG, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(self.leftMargin, 0.31 * inch, "ProofFix - micro1 Frontier Engineering Challenge 2026")
        canvas.drawRightString(letter[0] - self.rightMargin, 0.31 * inch, f"{doc.page}")
        canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverKicker", fontName=BOLD, fontSize=10, leading=12, textColor=CORAL, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverTitle", fontName=BOLD, fontSize=30, leading=34, textColor=WHITE, spaceAfter=12))
styles.add(ParagraphStyle(name="CoverSub", fontName=REG, fontSize=14, leading=20, textColor=colors.HexColor("#DCE5F3"), spaceAfter=18))
styles.add(ParagraphStyle(name="CoverMeta", fontName=REG, fontSize=9.5, leading=14, textColor=colors.HexColor("#B8C6DA")))
styles.add(ParagraphStyle(name="H1x", fontName=BOLD, fontSize=18, leading=22, textColor=NAVY, spaceBefore=2, spaceAfter=10))
styles.add(ParagraphStyle(name="H2x", fontName=BOLD, fontSize=12.5, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=6))
styles.add(ParagraphStyle(name="Bodyx", fontName=REG, fontSize=8.6, leading=12.1, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name="Smallx", fontName=REG, fontSize=7.2, leading=9.6, textColor=INK))
styles.add(ParagraphStyle(name="SmallMut", fontName=REG, fontSize=7, leading=9.2, textColor=MUTED))
styles.add(ParagraphStyle(name="Bulletx", fontName=REG, fontSize=8.3, leading=11.6, textColor=INK, leftIndent=12, firstLineIndent=-7, bulletIndent=0, spaceAfter=3))
styles.add(ParagraphStyle(name="Callout", fontName=BOLD, fontSize=13, leading=18, textColor=NAVY, borderColor=CORAL, borderWidth=1.2, borderPadding=10, backColor=PALE_CORAL, spaceBefore=6, spaceAfter=10))
styles.add(ParagraphStyle(name="Metric", fontName=BOLD, fontSize=22, leading=24, textColor=TEAL, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="MetricLabel", fontName=REG, fontSize=7.2, leading=9, textColor=MUTED, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="Foot", fontName=REG, fontSize=6.6, leading=8.7, textColor=MUTED))


def P(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", styles["Bulletx"])


def table(data, widths, header=True, font_size=7.2, row_bgs=None):
    cooked = []
    for r, row in enumerate(data):
        cooked.append([P(str(c), "Smallx" if r or not header else "Smallx") for c in row])
    t = Table(cooked, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("FONTNAME", (0, 0), (-1, -1), REG),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), BOLD),
        ]
        for i in range(1, len(data)):
            commands.append(("BACKGROUND", (0, i), (-1, i), WHITE if i % 2 else PALE))
    if row_bgs:
        for row_idx, color in row_bgs.items():
            commands.append(("BACKGROUND", (0, row_idx), (-1, row_idx), color))
    t.setStyle(TableStyle(commands))
    return t


def link(label: str, url: str) -> str:
    return f'<link href="{url}" color="#167D8D"><u>{label}</u></link>'


story = []

# Cover
cover = Table(
    [[
        P("DECISION BRIEF / 28 AUGUST 2026", "CoverKicker"),
    ], [
        P("ProofFix", "CoverTitle"),
    ], [
        P("Evidence-closed Kubernetes incident recovery", "CoverSub"),
    ], [
        P("The winning problem definition, architecture, benchmark, infrastructure plan, and 72-hour execution roadmap for the micro1 Frontier Engineering Challenge 2026.", "CoverMeta"),
    ]],
    colWidths=[7.16 * inch],
    rowHeights=[0.45 * inch, 0.72 * inch, 0.58 * inch, 1.25 * inch],
)
cover.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
    ("LEFTPADDING", (0, 0), (-1, -1), 28),
    ("RIGHTPADDING", (0, 0), (-1, -1), 28),
    ("TOPPADDING", (0, 0), (-1, -1), 10),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
story += [Spacer(1, 0.55 * inch), cover, Spacer(1, 0.35 * inch)]
story.append(P("DON'T TRUST THE DIAGNOSIS. TRUST THE PROOF OF RECOVERY.", "Callout"))
metric_table = Table([
    [P("15", "Metric"), P("90", "Metric"), P("1", "Metric")],
    [P("paired benchmark cases", "MetricLabel"), P("total benchmark runs", "MetricLabel"), P("verified state-transition metric", "MetricLabel")],
], colWidths=[2.38 * inch] * 3)
metric_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), PALE),
    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
]))
story += [metric_table, Spacer(1, 0.28 * inch), P("Prepared for a team-size-one online challenge. Detailed rules were taken from the supplied 10-page micro1 rulebook; live event metadata was checked on HackerEarth.", "SmallMut"), PageBreak()]

story += [P("Executive decision", "H1x")]
story.append(P("Build <b>ProofFix</b>: an operational agent that turns a Kubernetes alert into a human-approvable Incident Recovery Packet, applies the smallest admissible recovery inside a disposable cluster, and proves that the whole service recovered."))
story.append(P("The exact user bottleneck is not merely finding a plausible root cause. It is establishing the causal evidence chain, choosing the correct operation and target, bounding blast radius, preserving rollback, and verifying the post-change state under incident pressure."))
story.append(P("<b>Central product promise:</b> “Give me the smallest safe recovery I can approve now, show the evidence that justifies it, and prove the service is healthy afterward.”", "Callout"))

story += [P("Why this is the strongest rubric play", "H2x")]
matrix = [
    ["Candidate", "User", "Agent", "E2E", "Eval", "Repro", "Insight", "Total"],
    ["ProofFix: verified Kubernetes recovery", "15", "28", "19", "15", "14", "5", "96"],
    ["CI/test-failure repair", "13", "23", "18", "15", "15", "3", "87"],
    ["Kubernetes compliance evidence", "14", "25", "17", "13", "12", "4", "85"],
    ["FinOps anomaly remediation", "14", "24", "16", "12", "11", "4", "81"],
]
story.append(table(matrix, [2.38*inch, .48*inch, .52*inch, .48*inch, .48*inch, .52*inch, .52*inch, .52*inch], row_bgs={1: colors.HexColor("#E9F8F5")}))
story.append(P("Rubric-ceiling estimates, not project results. ProofFix leads on differentiation, live end-to-end verification, safety narrative, public scenarios, and a failure-derived hot take. CI repair is easier but crowded; compliance and FinOps have weaker live recovery oracles for this 72-hour window.", "SmallMut"))

story += [P("The research signal", "H2x")]
evidence = [
    ["Evidence", "Consequence for the build"],
    [f'{link("ITBench", "https://arxiv.org/abs/2502.05352")} reports 13.8% SRE resolution.', "There is substantial measurable headroom on realistic IT tasks."],
    [f'{link("Cloud-OpsBench", "https://arxiv.org/abs/2603.00468")} reaches 0.76/0.68 joint RCA but only 0.38/0.15 evidence closure.', "Correct final answers can still be untrustworthy operationally."],
    [f'{link("1,675-run RCA failure study", "https://arxiv.org/abs/2602.09937")} finds incomplete exploration and hallucinated telemetry across models.', "A stronger prompt is not the solution; workflow controls are."],
    [f'{link("R2Act", "https://arxiv.org/abs/2607.04623")} finds 91.4%-99.7% root-service accuracy but 36.8%-60.3% valid recovery actions.', "Diagnosis and valid action selection are different tasks."],
    [f'{link("21 Aug trajectory study", "https://arxiv.org/abs/2608.21310")} shows success depends on evidence-grounded paths.', "Trajectories and evidence gates belong in the primary design."],
]
story.append(table(evidence, [3.55*inch, 3.40*inch]))
story += [PageBreak()]

story += [P("Target user, trigger, and output", "H1x")]
story.append(P("<b>User.</b> The on-call SRE or platform engineer at a small or mid-sized organization operating Kubernetes microservices, often responding to a service they did not author."))
story.append(P("<b>Trigger.</b> An availability or latency alert with distributed evidence across Kubernetes state, logs, metrics, traces, deployment configuration, and service dependencies."))
story.append(P("<b>Bottleneck.</b> Under time pressure, the responder must judge whether the diagnosis is supported, whether the proposed action is admissible, what else could be harmed, how to roll back, and whether recovery truly occurred."))

packet = [
    ["Incident Recovery Packet", "What the responder receives"],
    ["Situation", "Impact, affected SLO, scope, current health, severity"],
    ["Proof", "Timestamped evidence, dependency/fault path, source pointers"],
    ["Reasoning", "Ranked hypotheses, discriminating tests, counterevidence"],
    ["Recovery", "Smallest action, exact target, expected postcondition"],
    ["Safety", "Blast radius, forbidden actions checked, rollback, approval gate"],
    ["Verification", "Before/after probes, whole-system health, residual uncertainty"],
]
story.append(table(packet, [2.05*inch, 4.90*inch]))

story += [P("Baseline fairness contract", "H2x")]
for item in [
    "One general-purpose ReAct agent with the official mitigation task and basic instructions.",
    "Same fixed model, typed AIOpsLab tools, 20 environment actions, total token ceiling, timeout, fresh cluster, and no evaluation-time internet as ProofFix.",
    "No explicit evidence ledger, hypothesis board, challenger, safety policy, runbook memory, or post-action verification state machine.",
    "Every run is reported; no best-of-N selection. Resource differences and internal model-call counts are disclosed.",
]:
    story.append(bullet(item))

story += [P("ProofFix architecture", "H2x")]
arch = [
    ["Stage", "Responsibility", "Gate / failure behavior"],
    ["1. Controller", "Freeze manifest; enforce budget; trace state", "Deterministic state machine"],
    ["2. Observer", "Topology, symptoms, changes, telemetry", "Read-only, source every observation"],
    ["3. Hypothesis manager", "Rank causes and next discriminating test", "Support + counterevidence required"],
    ["4. Challenger", "Try to falsify leading diagnosis", "Return to observation if evidence gaps remain"],
    ["5. Recovery planner", "Smallest reversible action and rollback", "Exact operation, target, expected postcondition"],
    ["6. Safety gate", "Allowlist, scope, data-loss and rollback policy", "Human approval in production; sandbox in benchmark"],
    ["7. Executor", "Apply approved plan and record diff", "One bounded re-plan; no silent retries"],
    ["8. Health verifier", "Whole-system probes and persistence checks", "Rollback on regression or partial recovery"],
    ["9. Report compiler", "Build packet from trace only", "Unsupported critical claim fails the case"],
]
story.append(table(arch, [1.28*inch, 3.18*inch, 2.49*inch]))
story += [PageBreak()]

story += [P("Fifteen-case benchmark", "H1x")]
story.append(P(f"Use all 14 current mitigation tasks in the MIT-licensed {link('AIOpsLab', 'https://github.com/microsoft/AIOpsLab')} registry plus one pre-registered healthy/noisy abstention control. AIOpsLab evaluates the general state of the entire system after mitigation, not only the injected resource."))
cases = [
    ["#", "Case", "Family", "Critical capability"],
    ["1", "Target-port: user service", "Routing", "YAML + exact target"],
    ["2", "Target-port: text service", "Routing", "Topology transfer"],
    ["3", "Target-port: post-storage", "Routing", "Persistence dependency"],
    ["4", "Missing MongoDB auth", "Auth/config", "No secret leakage"],
    ["5", "Revoked auth: geo", "Authorization", "Backend propagation"],
    ["6", "Revoked auth: rate", "Authorization", "Target transfer"],
    ["7", "Unregistered user: geo", "Identity", "Absent vs revoked"],
    ["8", "Unregistered user: rate", "Identity", "Exact target"],
    ["9", "Hotel app misconfiguration", "App config", "Cross-layer fix"],
    ["10", "Deployment scaled to zero", "Capacity", "Minimal restoration"],
    ["11", "Nonexistent node assignment", "Scheduling", "Counterfactual evidence"],
    ["12", "Kafka queue failure", "Messaging", "Multi-service path"],
    ["13", "Redeploy without PV", "Data safety", "Challenge: prevent data-loss masking"],
    ["14", "Wrong binary usage", "Runtime", "Process/image evidence"],
    ["15", "Healthy + noisy distractors", "Abstention", "Control: do nothing safely"],
]
story.append(table(cases, [.33*inch, 2.70*inch, 1.28*inch, 2.64*inch], font_size=6.8, row_bgs={13: PALE_CORAL, 15: colors.HexColor("#E9F8F5")}))

story += [P("Primary metric: Verified Recovery Success", "H2x")]
story.append(P("A case scores 1 only when the agent submits within budget, the whole-environment evaluator confirms recovery (or unchanged health for case 15), no forbidden action occurred, post-recovery probes pass for the fixed window, and the packet contains no unsupported critical claim. <b>VRS is the mean across all case-trial pairs.</b>"))
metric_cards = Table([
    [P("15 x 3 x 2", "Metric"), P("20", "Metric"), P("0", "Metric")],
    [P("cases x trials x systems = 90 runs", "MetricLabel"), P("environment actions per run", "MetricLabel"), P("allowed cherry-picked runs", "MetricLabel")],
], colWidths=[2.31*inch]*3)
metric_cards.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .5, LINE),
    ("INNERGRID", (0, 0), (-1, -1), .5, LINE), ("TOPPADDING", (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
]))
story += [metric_cards, Spacer(1, 7)]
for item in [
    "Paired clean environments from one pinned image; alternate baseline/full order by case and trial.",
    "Fixed model version and temperature 0 where supported; equal total token ceiling and no internet.",
    "Pre-register cases, acceptable/forbidden actions, metric code, seeds, timeouts, and exclusions.",
    "Report percentage-point change, paired bootstrap 95% CI, and exact McNemar test.",
    "Ship fast deterministic replay fixtures plus a full live mode; judges can replay three representative live incidents.",
]:
    story.append(bullet(item))
story += [PageBreak()]

story += [P("Infrastructure and reproducibility", "H1x")]
infra = [
    ["Resource", "Owned role", "Fairness / safety constraint"],
    ["VM2 control plane", "Repo, orchestration, trace ingest, dashboard, aggregation", "No scenario workload competes with control services"],
    ["Runner VM A", "Baseline shards", "Same immutable image as full system"],
    ["Runner VM B", "ProofFix shards", "Pair and alternate with A"],
    ["Runner VM C", "Extra trials and live demo cluster", "Disposable namespaces/clusters only"],
    ["Clean-room VM", "Zero-cache setup, reproduction, video", "No dev credentials or warmed state"],
    ["Gemini Deep Research", "Failure taxonomy, runbook sources, disconfirmation", "Freeze before eval; no gold-label access"],
    ["Antigravity pipelines", "Deploy, inject, schedule, trace, infra-retry", "Never retry a valid agent failure"],
    ["Frontier orchestration", "Development ablations", "Same final model/token ceiling for comparison"],
]
story.append(table(infra, [1.42*inch, 3.05*inch, 2.48*inch]))
story += [P("Trajectory contract", "H2x")]
story.append(P("Every run emits JSONL and a human-readable view containing: instructions; observations; tool calls and responses; hypothesis updates; verifier feedback; policy decision; approval checkpoint; action diff; health checks; retries; final packet; model/tool versions; timestamps; token/cost data; and content hashes. Secrets are redacted at the tool boundary."))

story += [P("Target gates (goals, not current results)", "H2x")]
targets = [
    [">=80%", "+30 pp", "0", ">=85%", "<10 min"],
    ["VRS", "vs baseline", "forbidden actions", "evidence gates", "median TTM"],
]
t = Table([[P(x, "Metric") for x in targets[0]], [P(x, "MetricLabel") for x in targets[1]]], colWidths=[1.39*inch]*5)
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), PALE), ("BOX", (0,0), (-1,-1), .5, LINE),
    ("INNERGRID", (0,0), (-1,-1), .5, LINE), ("TOPPADDING", (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
]))
story.append(t)

story += [P("Clean-environment contract", "H2x")]
for item in [
    "Pinned OS/container digests, model identifier, dependency lock, scenario commit, and deterministic policy manifest.",
    "One command for setup, baseline, ProofFix, evaluation, and report generation; expected output and runtime documented.",
    "Quick replay target under 15 minutes; full 90-run benchmark target under two hours on four runners.",
    "No credentials in submission; environment variables documented; all public/synthetic data and licenses enumerated.",
]:
    story.append(bullet(item))
story += [PageBreak()]

story += [P("72-hour execution roadmap", "H1x")]
timeline = [
    ["Window", "Outcome", "Non-negotiable exit gate"],
    ["Aug 28 - foundation", "Freeze problem, cases, metric, fairness, licenses. Scaffold trace schema, baseline, one smoke case.", "Baseline completes one live mitigation and records a replayable trace."],
    ["Aug 29 - full path", "Observer, hypothesis ledger, challenger, policy, executor, verifier, packet. Five dev cases.", "One incident runs alert-to-verified-packet without manual repair."],
    ["Aug 30 - evidence", "Ablations; remove weak components; freeze code; run 90 paired evaluations; aggregate stats.", "All runs accounted for; metric report and changelog generated."],
    ["Aug 31 - delivery", "Clean-room run, README, video, trajectory viewer, licenses, final package.", "Freeze 15:00 UTC; verify authenticated countdown before upload."],
]
story.append(table(timeline, [1.15*inch, 3.62*inch, 2.18*inch]))

story += [P("Improvement changelog plan", "H2x")]
change = [
    ["Stage", "Hypothesis", "Keep only if"],
    ["Baseline", "Generic ReAct handles simple incidents", "Fair starting point is reproducible"],
    ["+ Evidence ledger", "Prevents premature diagnosis", "VRS/grounding rise without excessive latency"],
    ["+ Challenger", "Catches plausible wrong causes", "Unsupported claims and invalid actions fall"],
    ["+ Safety policy", "Prevents target/operation mistakes", "Forbidden-action rate reaches zero"],
    ["+ Health verifier", "Converts fixes into proved recovery", "VRS rises; partial fixes are caught"],
    ["+ Failure memory", "Improves transfer to unseen targets", "Held-out VRS rises without leakage/cost blowout"],
]
story.append(table(change, [1.32*inch, 3.05*inch, 2.58*inch]))
story.append(P("Preserve at least one removed experiment. Prime candidates are unconstrained multi-agent debate (latency/cost) and unfiltered trajectory memory (anchoring/leakage).", "SmallMut"))

story += [P("Hot take", "H2x")]
story.append(P("Root-cause accuracy is a vanity metric when the user needs a safe recovery. The meaningful unit of agent reliability is a <b>verified state transition</b>: evidence closed, action admissible, blast radius bounded, recovery observed, and rollback available. Better prompts may improve prose; they do not supply the missing control system.", "Callout"))
story += [PageBreak()]

story += [P("Risks, limits, and decision guardrails", "H1x")]
risks = [
    ["Risk", "Mitigation"],
    ["“Another SRE agent”", "Lead with evidence closure, policy-gated recovery, and verified state transition—not chat-based RCA."],
    ["Live benchmark noise", "Pinned images, paired order, three trials, infra-failure classification, deterministic replay fixtures."],
    ["Benchmark leakage", "Development/evaluation split, no internet, freeze manifests, exclude gold labels and eval traces from memory."],
    ["Consequential actions", "Disposable clusters, typed allowlist, namespace scope, data-loss policy, rollback, production human approval."],
    ["License ambiguity", "Redistribute only verified compatible assets. AIOpsLab is MIT; Cloud-OpsBench is research evidence unless its repo license is confirmed."],
    ["Time pressure", "Baseline and one complete live path first; UI polish only after evaluator and trace are stable."],
]
story.append(table(risks, [1.70*inch, 5.25*inch]))

story += [P("Material limitations", "H2x")]
for item in [
    "AIOpsLab is a benchmark; its faults and service topologies do not represent every production incident.",
    "Fifteen cases support a strong hackathon comparison, not a universal reliability claim.",
    "Recognizable scenario patterns may still encourage overfitting; target variants and gold-label isolation reduce but do not eliminate it.",
    "Human review time is reported only if a qualified reviewer can score blinded packets consistently.",
    "HackerEarth's deeper dynamic tabs were blocked from this VM by its anonymous/VPN IP gate; the supplied 10-page rulebook controls detailed requirements.",
]:
    story.append(bullet(item))

story += [P("Sources and provenance", "H2x")]
sources = [
    ["Source", "Publisher / date", "Supports"],
    ["Agentic Workflows Hackathon (supplied 10-page PDF)", "micro1 / 27 Aug 2026", "Rubric, rules, deliverables, 10+ cases, video, trajectories"],
    [link("HackerEarth challenge page", "https://www.hackerearth.com/community/challenges/hackathon/micro1-frontier-engineering-challenge-2026/"), "HackerEarth / accessed 28 Aug", "Dates, online, team size 1, registrations"],
    [link("Effective Troubleshooting", "https://sre.google/sre-book/effective-troubleshooting/"), "Google SRE", "Evidence, hypothesis testing, controlled changes"],
    [link("AIOpsLab paper", "https://arxiv.org/abs/2501.06706"), "Chen et al. / 12 Jan 2025", "Live fault injection, whole-system evaluation"],
    [link("AIOpsLab repository", "https://github.com/microsoft/AIOpsLab"), "Microsoft / accessed 28 Aug", "MIT license and current mitigation registry"],
    [link("ITBench", "https://arxiv.org/abs/2502.05352"), "Jha et al. / 7 Feb 2025", "IT automation benchmark and low SRE resolution"],
    [link("Cloud-OpsBench v2", "https://arxiv.org/abs/2603.00468"), "Wang et al. / 22 Aug 2026", "Outcome-versus-evidence gap"],
    [link("Systematic RCA failures", "https://arxiv.org/abs/2602.09937"), "Kim et al. / 10 Feb 2026", "1,675 runs; prompt-only limits"],
    [link("R2Act", "https://arxiv.org/abs/2607.04623"), "Qi et al. / 6 Jul 2026", "Diagnosis-versus-action validity gap"],
    [link("Beyond Fault Localization", "https://arxiv.org/abs/2608.21310"), "Lu et al. / 21 Aug 2026", "3,500 trajectory study"],
]
story.append(table(sources, [2.75*inch, 1.68*inch, 2.52*inch], font_size=6.6))
story += [Spacer(1, 9), P("Research stop condition", "H2x"), P("The decision survived a second-wave challenge on novelty, licensing, benchmark availability, reproducibility, action safety, and 72-hour buildability. Additional searches were returning weaker variants and were unlikely to change the selection before implementation needed to begin.", "Foot")]


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ReportDoc(str(OUT))
    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    build()
