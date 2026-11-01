"""Regenerates architecture.png/svg and dataflow.png/svg.

Run:  python3 make_diagrams.py
Needs: matplotlib. Edit the coordinates below to change the layout.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

FONT = "Inter" if any("Inter" in f.name for f in fm.fontManager.ttflist) else "DejaVu Sans"
plt.rcParams["font.family"] = FONT

INK = "#1F2933"
MUTED = "#52606D"
LINE = "#5B6770"

C = {
    "staff": ("#F1F3F5", "#B8C0C7"),
    "fe": ("#E7F1FB", "#8DB8E0"),
    "api": ("#DCEBFA", "#6FA3D6"),
    "agent": ("#EEE8FA", "#9B87D1"),
    "guard": ("#F7F3FD", "#9B87D1"),
    "svc": ("#E4F4E8", "#7DBE8E"),
    "llm": ("#FDEFD9", "#E0A458"),
    "data": ("#FFF6CC", "#D9BF4A"),
    "obs": ("#F1F3F5", "#B8C0C7"),
    "gate": ("#FFF1D6", "#E0A458"),
    "stop": ("#FDE3E1", "#D9534F"),
    "human": ("#E4F4E8", "#7DBE8E"),
    "learn": ("#DDF3F0", "#5BB5A8"),
    "white": ("#FFFFFF", LINE),
}


def rect(ax, x, y, w, h, kind, rounding=0.18, lw=1.2, dashed=False, z=1):
    fc, ec = C[kind]
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={rounding}",
            fc=fc, ec=ec, lw=lw, ls="--" if dashed else "-", zorder=z,
        )
    )


def box(ax, x, y, w, h, title, body="", kind="white", fs=10.5, dashed=False, tfs=None, z=2):
    rect(ax, x, y, w, h, kind, rounding=0.12, dashed=dashed, z=z)
    tfs = tfs or fs
    if body:
        ax.text(x + w / 2, y + h - 0.2, title, ha="center", va="center", fontsize=tfs,
                fontweight="bold", color=INK, zorder=z + 1)
        ax.text(x + w / 2, y + (h - 0.36) / 2, body, ha="center", va="center", fontsize=fs - 0.8,
                color=INK, linespacing=1.25, zorder=z + 1)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=fs,
                fontweight="bold", color=INK, linespacing=1.25, zorder=z + 1)


def tag(ax, x, y, text, fs=11.5, color=INK, ha="left", weight="bold"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fs, fontweight=weight, color=color, zorder=5)


def lab(ax, x, y, text, fs=9.3, color=MUTED, ha="center"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fs, color=color, zorder=6,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.95))


def arrow(ax, pts, color=LINE, lw=1.5, dashed=False, z=4):
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, ls="--" if dashed else "-",
                solid_capstyle="round", zorder=z)
    ax.annotate(
        "", xy=pts[-1], xytext=pts[-2],
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls="--" if dashed else "-",
                        shrinkA=0, shrinkB=0, mutation_scale=13),
        zorder=z,
    )


def store(ax, x, y, w, text, h=0.5):
    box(ax, x, y, w, h, text, kind="data", fs=9.3)


def link(ax, x, y1, y2):
    ax.plot([x, x], [y1, y2], color="#B59A1F", lw=1.2, ls=(0, (2, 2)), zorder=3)


# ======================================================================
# 1. ARCHITECTURE
# ======================================================================
def architecture():
    fig, ax = plt.subplots(figsize=(22, 14.2), dpi=110)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 14.2)
    ax.axis("off")
    ax.text(11, 13.75, "Loan Pre-Underwriting Copilot: High-Level Architecture (v1)", ha="center",
            fontsize=22, fontweight="bold", color=INK)

    # staff
    rect(ax, 5.4, 11.65, 11.4, 1.35, "staff")
    tag(ax, 5.6, 12.75, "Bank staff (browser)", fs=11)
    for x, t in [(6.8, "Loan officers (many)"), (11.6, "Admin")]:
        box(ax, x, 11.8, 2.8, 0.7, t, kind="white", fs=11)

    # frontend
    rect(ax, 0.6, 10.0, 16.4, 1.0, "fe")
    ax.text(8.8, 10.7, "Frontend: React + JavaScript + CSS", ha="center", va="center",
            fontsize=11.5, fontweight="bold", color=INK, zorder=3)
    ax.text(8.8, 10.3, "Case queue  ·  New case  ·  Upload  ·  Report  ·  Confirm / Override  ·  Admin precedent queue",
            ha="center", va="center", fontsize=10.5, color=INK, zorder=3)
    for x in (7.4, 11.2, 15.0):
        arrow(ax, [(x, 11.8), (x, 11.0)])

    # application enclosure
    rect(ax, 0.3, 2.3, 17.0, 7.3, "obs", rounding=0.25, dashed=True, lw=1.4, z=0)
    tag(ax, 0.55, 9.38, "Application  (runs locally first; Docker Compose at the final stage)", fs=11, color=MUTED)

    # API band
    rect(ax, 0.6, 7.45, 16.4, 1.65, "api")
    tag(ax, 0.8, 8.9, "Backend: FastAPI", fs=11)
    box(ax, 0.9, 7.6, 3.2, 0.95, "Background graph runner", "starts and resumes the run", "white")
    box(ax, 4.6, 7.6, 6.0, 0.95, "Case · Upload · Report · Confirm APIs",
        "upload checks: type · password · blur", "white")
    box(ax, 11.1, 7.6, 2.6, 0.95, "Audit writer", "every action logged", "white")
    box(ax, 14.2, 7.6, 2.6, 0.95, "Auth + roles", "officer · admin", "white")
    arrow(ax, [(8.8, 10.0), (8.8, 8.55)])
    lab(ax, 9.9, 9.55, "HTTPS / JSON")
    arrow(ax, [(4.6, 8.07), (4.1, 8.07)])
    arrow(ax, [(10.6, 8.07), (11.1, 8.07)])

    # agent band
    rect(ax, 0.6, 4.95, 16.4, 2.3, "agent")
    tag(ax, 16.8, 7.05, "Agent runtime: LangGraph  (fixed order · gate after every stage · pause / resume for human review)", fs=11, ha="right")
    box(ax, 0.9, 5.1, 2.2, 1.0, "1  Supervisor", "plans, assigns,\nassembles", "white", fs=10.5)
    box(ax, 3.6, 5.1, 2.2, 1.0, "2  Extraction", "classify, mask,\nextract fields", "white", fs=10.5)
    box(ax, 6.3, 5.1, 2.2, 1.0, "3  KYC &\nCompliance", "", "white", fs=10.5)
    rect(ax, 9.0, 5.1, 4.4, 1.0, "white")
    ax.text(11.2, 5.92, "4  run in parallel", ha="center", fontsize=9.5, color=MUTED, zorder=4)
    box(ax, 9.15, 5.18, 2.0, 0.55, "Risk", kind="guard", fs=10.5)
    box(ax, 11.25, 5.18, 2.0, 0.55, "Policy", kind="guard", fs=10.5)
    box(ax, 13.9, 5.1, 2.6, 1.0, "5  Decision", "score in code,\nLLM writes report", "white", fs=10.5)
    for a, b in [(3.1, 3.6), (5.8, 6.3), (8.5, 9.0), (13.4, 13.9)]:
        arrow(ax, [(a, 5.6), (b, 5.6)])
    rect(ax, 3.6, 6.4, 12.9, 0.45, "guard", rounding=0.1, dashed=True)
    ax.text(10.05, 6.62, "Guardrails + online evaluation after every stage:  schema  ·  citations  ·  wording  ·  injection scan",
            ha="center", va="center", fontsize=10, color=INK, zorder=4)
    arrow(ax, [(2.0, 7.6), (2.0, 6.1)])
    lab(ax, 2.0, 6.95, "start /\nresume", fs=8.8)

    # services band
    rect(ax, 0.6, 2.5, 16.4, 2.25, "svc")
    # intake
    rect(ax, 2.7, 2.6, 4.0, 2.05, "white")
    tag(ax, 2.85, 4.45, "Intake & parsers (local)", fs=10.5)
    box(ax, 2.9, 3.4, 3.6, 0.7, "PyMuPDF · pdfplumber", "OpenCV · PaddleOCR", "svc", fs=10)
    box(ax, 2.9, 2.7, 3.6, 0.55, "PII masker + ID validators", kind="svc", fs=10)
    # core
    rect(ax, 7.0, 2.6, 4.9, 2.05, "white")
    tag(ax, 7.15, 4.45, "Deterministic core (code, no LLM maths)", fs=10.5)
    box(ax, 7.2, 3.45, 2.25, 0.7, "Rules engine", "+ scoring", "svc", fs=10)
    box(ax, 9.6, 3.45, 2.1, 0.7, "Rules file", "+ policy docs", "svc", fs=10)
    box(ax, 7.2, 2.7, 4.5, 0.55, "Mock services: identity · bureau · GST · Udyam", kind="svc", fs=10)
    # rag
    rect(ax, 12.2, 2.6, 4.6, 2.05, "white")
    tag(ax, 12.35, 4.45, "RAG (local models)", fs=10.5)
    box(ax, 12.4, 3.45, 4.2, 0.7, "BGE-small embeddings (384-d)", "pgvector search", "svc", fs=10)
    box(ax, 12.4, 2.7, 4.2, 0.55, "Cross-encoder reranker", kind="svc", fs=10)
    # vertical arrows agents -> services
    arrow(ax, [(4.7, 5.1), (4.7, 4.65)]); lab(ax, 5.55, 4.88, "parse · mask", fs=9)
    arrow(ax, [(7.4, 5.1), (7.4, 4.65)]); lab(ax, 7.95, 4.88, "lookups", fs=9)
    arrow(ax, [(10.1, 5.18), (10.1, 4.65)]); lab(ax, 10.7, 4.88, "score", fs=9)
    arrow(ax, [(12.8, 5.18), (12.8, 4.65)]); lab(ax, 13.8, 4.88, "retrieve · rerank", fs=9)

    # gateway column
    rect(ax, 17.9, 2.3, 3.7, 7.3, "llm", rounding=0.25)
    tag(ax, 19.75, 9.25, "LLM gateway: LiteLLM", fs=11, ha="center")
    ax.text(19.75, 8.82, "routing · fallback ·\ntoken + cost log", ha="center", va="center", fontsize=9.5, color=INK)
    box(ax, 18.1, 7.45, 3.3, 0.95, "Gemini Flash", "Supervisor · Extraction\nDecision", "white", fs=10)
    box(ax, 18.1, 6.2, 3.3, 0.95, "Groq gpt-oss-20b", "KYC · Risk", "white", fs=10)
    box(ax, 18.1, 4.95, 3.3, 0.95, "NVIDIA Nemotron", "Policy", "white", fs=10)
    box(ax, 18.1, 3.3, 3.3, 1.2, "Fallback model", "used on 429 / errors\n(free NVIDIA or similar)", "white", fs=10, dashed=True)
    arrow(ax, [(17.0, 5.6), (17.9, 5.6)], dashed=True)
    lab(ax, 17.45, 5.95, "all model\ncalls", fs=8.8)

    # bottom row
    box(ax, 0.5, 0.45, 5.8, 1.15, "Neon Postgres + pgvector",
        "cases · documents · fields · stage results · reports\nprecedents · policy vectors · rules · audit · checkpoints", "data", fs=10)
    box(ax, 6.8, 0.45, 2.7, 1.15, "Local file store", "uploaded documents", "data", fs=10)
    box(ax, 10.0, 0.45, 3.4, 1.15, "Prometheus · Loki · Tempo", "Grafana dashboards", "obs", fs=10)
    box(ax, 13.9, 0.45, 3.4, 1.15, "GitHub Actions CI", "tests + RAGAS + DeepEval gate", "obs", fs=10)
    box(ax, 17.9, 0.45, 3.7, 1.15, "Langfuse", "tokens · cost · latency per agent", "obs", fs=10)
    arrow(ax, [(3.4, 2.3), (3.4, 1.6)], lw=1.6); arrow(ax, [(3.4, 1.6), (3.4, 2.3)], lw=1.6)
    lab(ax, 4.4, 1.95, "reads / writes", fs=9)
    arrow(ax, [(8.1, 2.3), (8.1, 1.6)]); lab(ax, 8.85, 1.95, "uploads", fs=9)
    arrow(ax, [(11.7, 2.3), (11.7, 1.6)], dashed=True); lab(ax, 12.75, 1.95, "metrics · logs · traces", fs=9)
    arrow(ax, [(15.6, 1.6), (15.6, 2.3)], dashed=True); lab(ax, 16.25, 1.95, "eval gate on PR", fs=9)
    arrow(ax, [(19.75, 2.3), (19.75, 1.6)]); lab(ax, 20.4, 1.95, "traces", fs=9)

    fig.savefig("architecture.png", dpi=130, bbox_inches="tight", facecolor="white")
    fig.savefig("architecture.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ======================================================================
# 2. DATA FLOW
# ======================================================================
def dataflow():
    fig, ax = plt.subplots(figsize=(22, 16.6), dpi=110)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 16.6)
    ax.axis("off")
    ax.text(11, 16.1, "Data Flow: one loan case from upload to learning", ha="center",
            fontsize=22, fontweight="bold", color=INK)

    def lane(y0, y1, name, kind):
        fc, ec = C[kind]
        ax.add_patch(Rectangle((0.25, y0), 21.05, y1 - y0, fc="white", ec=ec, lw=1.2, zorder=0))
        ax.add_patch(Rectangle((0.25, y0), 0.6, y1 - y0, fc=ec, ec=ec, zorder=1))
        ax.text(0.55, (y0 + y1) / 2, name, rotation=90, ha="center", va="center",
                fontsize=12, fontweight="bold", color="white", zorder=2)

    # ---- lanes
    lane(12.55, 15.6, "1 · CASE INTAKE", "api")
    lane(6.05, 12.25, "2 · ASSESSMENT PIPELINE", "agent")
    ax.text(20.9, 12.02, "fixed order  ·  gate after each stage", ha="right", va="center",
            fontsize=9.8, color=MUTED, zorder=5)
    lane(3.25, 5.75, "3 · HUMAN REVIEW", "human")
    lane(0.35, 2.95, "4 · LEARNING LOOP", "learn")

    # ---- lane 1: intake (nodes y 13.55-14.65)
    y = 13.65
    box(ax, 1.3, y, 3.7, 1.1, "1  Officer creates case", "loan type + application form", "fe")
    box(ax, 5.7, y, 3.5, 1.1, "2  Upload files", "one by one or together", "fe")
    box(ax, 9.9, y, 3.7, 1.1, "3  Upload checks", "password? blur? file type?", "gate")
    box(ax, 14.3, y, 3.5, 1.1, "4  Store file", "+ document record", "fe")
    box(ax, 18.5, y, 2.4, 1.1, "5  Submit", "for assessment", "fe")
    for a, b in [(5.0, 5.7), (9.2, 9.9), (13.6, 14.3), (17.8, 18.5)]:
        arrow(ax, [(a, y + 0.55), (b, y + 0.55)])
    # reject loop
    arrow(ax, [(11.75, y + 1.1), (11.75, 15.2), (7.45, 15.2), (7.45, y + 1.1)], color="#D9534F")
    lab(ax, 9.6, 15.2, "rejected (password / blur): officer re-uploads", fs=9.3, color="#B03A36")
    lab(ax, 11.75, 13.4, "accepted (warning if borderline)", fs=9, color=MUTED)
    store(ax, 1.3, 12.8, 2.9, "cases · applicants")
    link(ax, 2.75, 13.65, 13.3)
    store(ax, 14.3, 12.8, 3.5, "files + documents")
    link(ax, 16.05, 13.65, 13.3)

    # ---- lane 2 row 1 (nodes y 10.15-11.35)
    y1 = 10.15
    h1 = 1.2
    box(ax, 1.3, y1, 3.3, h1, "6  Supervisor", "builds document checklist\nfrom the rules file", "agent")
    ax.text(13.0, 11.72, "7  EXTRACTION AGENT", ha="center", fontsize=10.5, fontweight="bold", color="#6B55B5", zorder=5)
    ax.plot([5.2, 20.9], [11.55, 11.55], color="#9B87D1", lw=1.2, zorder=3)
    box(ax, 5.2, y1, 3.5, h1, "7a  Parse", "PyMuPDF / pdfplumber, or\nOpenCV + local OCR;\nclassify document", "agent", fs=10.3)
    box(ax, 9.4, y1, 3.3, h1, "7b  Mask PII", "local masker; reversible\nmap stays on the machine", "agent", fs=10.3)
    box(ax, 13.4, y1, 3.4, h1, "7c  LLM extracts", "fields from MASKED text,\nper-field confidence", "agent", fs=10.3)
    box(ax, 17.5, y1, 3.4, h1, "7d  Code validators", "formats · checksums\ntotals · dates · tamper hints", "agent", fs=10.3)
    for a, b in [(4.6, 5.2), (8.7, 9.4), (12.7, 13.4), (16.8, 17.5)]:
        arrow(ax, [(a, y1 + 0.6), (b, y1 + 0.6)])
    arrow(ax, [(19.7, 13.65), (19.7, 12.4), (2.95, 12.4), (2.95, y1 + h1)])
    store(ax, 17.5, 9.4, 2.3, "extracted fields")
    link(ax, 18.65, y1, 9.9)

    # ---- lane 2 row 2 (snake right to left; nodes y 7.3-8.6)
    y2 = 7.3
    h2 = 1.3
    box(ax, 17.9, y2, 3.0, h2, "8  KYC & Compliance", "ID formats, checksums,\nname / PAN / DOB / address\nmatch, mock identity", "agent", fs=10.3)
    box(ax, 14.35, y2, 3.0, h2, "9  Gate", "hard fail?\nfix-type or eligibility-type", "gate", fs=10.3)
    rect(ax, 8.8, y2, 5.0, h2, "white")
    ax.text(11.3, y2 + 1.08, "10  PARALLEL", ha="center", fontsize=10, fontweight="bold", color="#6B55B5", zorder=4)
    box(ax, 8.95, y2 + 0.1, 2.35, 0.85, "Policy", "clauses + precedents\nrerank, grounding", "guard", fs=9.6, tfs=10.3)
    box(ax, 11.4, y2 + 0.1, 2.3, 0.85, "Risk", "FOIR, cheque returns,\nsalary, tamper", "guard", fs=9.6, tfs=10.3)
    box(ax, 5.25, y2, 3.0, h2, "11  Gate", "checks pass?\nretry once, else UNVERIFIED", "gate", fs=10.3)
    box(ax, 1.3, y2, 3.4, h2, "12  Decision", "stage scores to total in CODE\nLLM writes report + reason\nguardrails on output", "agent", fs=10.3)
    arrow(ax, [(20.2, y1), (20.2, y2 + h2)])
    for a, b in [(17.9, 17.35), (14.35, 13.8), (8.8, 8.25), (5.25, 4.7)]:
        arrow(ax, [(a, y2 + 0.65), (b, y2 + 0.65)])
    lab(ax, 14.07, y2 + 0.95, "no", fs=9)
    # hard fail path
    arrow(ax, [(15.85, y2), (15.85, 7.0), (4.0, 7.0), (4.0, y2)], color="#D9534F", dashed=True)
    lab(ax, 10.0, 7.0, "hard fail: stop here, short report with the stage scores so far", fs=9.3, color="#B03A36")
    store(ax, 5.25, 6.25, 6.4, "stage runs · rule results · reports  (written after every stage)")
    link(ax, 8.4, 6.75, 7.3 - 0.0)
    # precedent feed line into Policy
    arrow(ax, [(21.55, 9.15), (10.1, 9.15), (10.1, y2 + h2)], color="#2E8F82", dashed=True)
    lab(ax, 16.0, 9.15, "approved precedents (borderline cases only, never over hard rules)", fs=9.3, color="#1F6F65")

    # ---- lane 3: human review (nodes y 4.2-5.2)
    y3 = 4.15
    box(ax, 1.3, y3, 5.2, 1.1, "13  Report shown to officer", "stage scores · findings · citations\n\"recommended, awaiting your confirmation\"", "human")
    box(ax, 7.2, y3, 6.2, 1.1, "14  Officer confirms or overrides", "second click required · override needs a written reason", "human")
    box(ax, 14.1, y3, 5.2, 1.1, "15  Decision recorded", "audit log · report PDF export", "human")
    arrow(ax, [(1.9, y2), (1.9, y3 + 1.1)])
    arrow(ax, [(6.5, y3 + 0.55), (7.2, y3 + 0.55)])
    arrow(ax, [(13.4, y3 + 0.55), (14.1, y3 + 0.55)])
    store(ax, 14.1, 3.4, 5.2, "officer actions · audit log")
    link(ax, 16.7, y3, 3.9)

    # ---- lane 4: learning (nodes y 1.3-2.4)
    y4 = 1.3
    arrow(ax, [(8.6, y3), (8.6, y4 + 1.1)], color="#2E8F82")
    lab(ax, 9.5, 3.55, "override + reason", fs=9.3, color="#1F6F65")
    box(ax, 7.2, y4, 5.0, 1.1, "16  Proposed precedent", "officer reason + LLM report summary\n+ embedding", "learn")
    box(ax, 12.9, y4, 3.7, 1.1, "17  Admin decides", "hard-rule check, then\napprove or reject", "learn")
    box(ax, 17.3, y4, 3.6, 1.1, "18  Precedent stored", "expiry date set", "learn")
    arrow(ax, [(12.2, y4 + 0.55), (12.9, y4 + 0.55)])
    arrow(ax, [(16.6, y4 + 0.55), (17.3, y4 + 0.55)])
    lab(ax, 16.95, y4 + 0.8, "yes", fs=9)
    box(ax, 12.9, 0.5, 3.7, 0.5, "no: discarded (audited)", kind="white", fs=9.3)
    arrow(ax, [(14.75, y4), (14.75, 1.0)])
    store(ax, 17.3, 0.5, 3.6, "precedents (pgvector)")
    link(ax, 19.1, y4, 1.0)
    ax.plot([20.9, 21.55, 21.55], [y4 + 0.55, y4 + 0.55, 9.15], color="#2E8F82", lw=1.5, ls="--", zorder=4)

    # observability note
    box(ax, 1.3, 1.1, 5.2, 1.4, "Every step is observed",
        "masked traces + tokens + cost + latency\nto Langfuse; metrics and logs to Grafana", "obs", fs=10.3)

    fig.savefig("dataflow.png", dpi=130, bbox_inches="tight", facecolor="white")
    fig.savefig("dataflow.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    dataflow()
    print("done, font:", FONT)
