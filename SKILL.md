---
name: "china-political-interpretation"
description: "LLM-powered comprehensive evidence-led interpretation for China politics materials. Uses Gemini AI for deep analysis of policy documents, speeches, communiques, and regulatory texts. Features intelligent material understanding, smart search strategy generation, semantic diff analysis, risk scenario modeling, and automated HTML/PDF briefing package generation."
---

# China Political Interpretation Skill (LLM-Powered)

## Overview

This skill provides **AI-powered** political analysis using **Gemini LLM** at every step:

- 🤖 **LLM Material Understanding**: Automatically identifies document type, issuing body, key actors, policy signals
- 🤖 **LLM Search Strategy**: Generates intelligent horizontal/vertical search queries
- 🤖 **LLM Deep Analysis**: Policy intent, semantic diff, power signals, risk scenarios
- 🤖 **LLM Report Generation**: Modern interactive HTML + structured PDF reports
- 🔍 **Smart Content Extraction**: URL/PDF/Image with anti-crawling bypass
- 📊 **Real-time Progress**: SSE-based progress tracking in Web UI

## 🚀 Quick Start

### 1. Configure LLM API

```bash
# Copy and edit the environment config
cp .env.example .env

# Edit .env and add your Gemini API key
# GEMINI_API_KEY=your_api_key_here
# GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta  (or your proxy)
# GEMINI_MODEL=gemini-2.0-flash
```

### 2. Install Dependencies

```bash
# Create virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright for anti-crawling
python -m playwright install chromium

# Install frontend dependencies
cd ../frontend
npm install
```

### 3. Start Services

```bash
# Terminal 1: Start backend API server
cd backend
source venv/bin/activate
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000

# Terminal 2: Start frontend dev server
cd frontend
npm run dev
```

### 4. Open Web Interface

Visit `http://localhost:5173` in your browser.

### 5. Usage

1. **Add materials** - Drag-drop files (PDF/Image) or paste URLs
2. **Start analysis** - Click "Start Analysis" button
3. **Watch progress** - See LLM working through 8 stages:
   - 识别文本
   - 🤖 LLM理解材料
   - 🤖 LLM生成检索策略
   - 搜索横向材料
   - 搜索纵向材料
   - 🤖 LLM深度分析
   - 🤖 LLM生成HTML报告
   - 🤖 LLM生成PDF报告
4. **Access reports** - Download HTML/PDF briefing packages

## CLI Mode (LLM-Powered)

All CLI commands now support LLM-powered analysis when `GEMINI_API_KEY` is configured.

### Complete LLM-Powered Analysis Pipeline:
```bash
# Step 1: Build query matrix (LLM understands material + generates search strategy)
python3 scripts/build_research_queries.py \
  --file /path/to/material.txt \
  --output /tmp/query_matrix.json

# Step 2: Fetch related context
python3 scripts/fetch_context_results.py \
  --queries-json /tmp/query_matrix.json \
  --output /tmp/context_results.json

# Step 3: Generate LLM analysis (deep policy analysis)
python3 scripts/generate_analysis_outline.py \
  --material-file /path/to/material.txt \
  --query-matrix /tmp/query_matrix.json \
  --context-results /tmp/context_results.json \
  --output /tmp/analysis.json \
  --output-format json

# Step 4: Generate LLM reports (HTML + PDF)
python3 scripts/render_llm_reports.py \
  --analysis-json /tmp/analysis.json \
  --output-dir /tmp/policy_brief \
  --base-name policy-brief
```

## Quick Commands (CLI)

### Extract content from URL (with anti-crawling):
```bash
python3 scripts/content_extractor.py \
  --url https://example.com/news \
  --output /tmp/extracted.txt \
  --force-browser  # Use if standard fetch fails
```

### Extract content from image (OCR):
```bash
python3 scripts/content_extractor.py \
  --image /path/to/screenshot.png \
  --output /tmp/extracted.txt
```
Build query matrix (now supports URL, image, PDF):
```bash
python3 scripts/build_research_queries.py \
  --file /path/to/material.txt \
  --output /tmp/query_matrix.json

# Or directly from URL:
python3 scripts/build_research_queries.py \
  --url https://example.com/news \
  --output /tmp/query_matrix.json \
  --force-browser
```

Fetch related context from the query matrix:
```bash
python3 scripts/fetch_context_results.py \
  --queries-json /tmp/query_matrix.json \
  --output /tmp/context_results.json \
  --markdown /tmp/context_results.md
```

Generate analysis outline:
```bash
python3 scripts/generate_analysis_outline.py \
  --material-file /path/to/material.txt \
  --query-matrix /tmp/query_matrix.json \
  --context-results /tmp/context_results.json \
  --output /tmp/analysis_outline.md
```

Render deliverable package (HTML + PDF) - New Modern Output:
```bash
python3 scripts/render_analysis_web_pdf.py \
  --analysis-md /tmp/analysis_outline.md \
  --output-dir /tmp/policy_brief \
  --base-name policy-brief

# Use legacy rendering if needed:
python3 scripts/render_analysis_web_pdf.py \
  --analysis-md /tmp/analysis_outline.md \
  --output-dir /tmp/policy_brief \
  --base-name policy-brief \
  --use-legacy
```

Render HTML only (modern interactive):
```bash
python3 scripts/render_html_report.py \
  --analysis-md /tmp/analysis_outline.md \
  --output /tmp/policy_brief/report.html \
  --theme auto  # light, dark, or auto
```

Render PDF only (structured, print-friendly):
```bash
python3 scripts/render_pdf_report.py \
  --analysis-md /tmp/analysis_outline.md \
  --output /tmp/policy_brief/report.pdf
```

Or produce outline and package in one command:
```bash
python3 scripts/generate_analysis_outline.py \
  --material-file /path/to/material.txt \
  --query-matrix /tmp/query_matrix.json \
  --context-results /tmp/context_results.json \
  --output /tmp/analysis_outline.md \
  --package-dir /tmp/policy_brief \
  --package-base-name policy-brief
```

## Evidence Standard
- Use `F` for directly sourced facts (quoted, timestamped, attributable).
- Use `I` for inference built from multiple facts.
- Use `S` for scenario judgments about future outcomes.
- Assign confidence levels (`high`, `medium`, `low`) to every `I` and `S` statement.
- Include absolute dates (for example `2025-07-15`) instead of ambiguous terms like "recently".
- Assign source authority tier for each core claim:
  - `T0`: core communiques and top-leadership authoritative speeches.
  - `T1`: central normative documents and Xinhua authorized releases.
  - `T2`: ministry regulations/circulars and central media commentary.
  - `T3`: local implementation files and peripheral official interpretation.
- Do not let lower-tier documents negate higher-tier political signal without explicit contradiction analysis.

## Required Analysis Lenses
- Policy intent: state explicit goals and likely implicit political goals.
- Institutional map: identify lead agencies, coordination bodies, and likely veto points.
- Cadre and power signals: flag personnel, campaign language, and center-local command clues.
- Textual & semantic shifts: compare same-type historical texts and extract added terms, dropped terms, and intensity changes in modifiers.
- Implementation path: describe who executes, what resources are required, and what can fail.
- Distributional impact: map winners, losers, and affected regions/sectors/groups.
- External signaling: assess foreign policy, market, or geopolitical signaling if relevant.
- Business and compliance impact: translate policy logic into operational implications for firms and sectors.

## Horizontal and Vertical Expansion
- Run horizontal expansion by collecting same-event coverage from official documents, party-state media, market media, and external outlets.
- Run vertical expansion by collecting predecessor policies, implementation notices, and retrospective evaluations across at least 3 time points.
- Prioritize primary sources over commentary.
- Mark contradictions explicitly and explain why they may exist.
- Force one discourse diff pass: compare at least one historical peer document and output:
  - newly introduced wording,
  - disappeared wording,
  - softened/hardened modifiers (for example from restriction language to development language),
  - inferred political intent behind wording shifts.

## Output Format
Use this section order in final analysis:
1. Core Judgment (3-5 bullets)
2. What Happened (Fact Layer)
3. Why It Happened (Political Logic)
4. Who Gains Power / Who Bears Cost
5. Textual & Semantic Diff (added/dropped/shifted wording)
6. Vertical Lineage (past to present)
7. Horizontal Comparison (source and narrative divergence + tier conflict)
8. Risk and Scenario Tree (next 3-12 months, include extreme tail risk <10%)
9. What to Watch (indicators and trigger events)
10. Business/Compliance Impact & Actionable Strategy
11. Evidence Table (claim, source, date, tag, confidence, tier)
12. Deliverables (file paths for `.html` and `.pdf`)

## Deliverable Requirements

### HTML Report (Modern Interactive)
- Responsive layout for all devices
- Dark/Light theme toggle
- Collapsible sections with smooth transitions
- Floating navigation with scroll highlighting
- Interactive evidence tags (F/I/S) with tooltips
- Sortable tables
- Smooth animations

### PDF Report (Structured Print-Friendly)
- Clear text hierarchy with numbered sections
- Clean table layout with proper borders
- No decorative elements (gradients, animations)
- A4 format, print-friendly
- Emphasis on readability and information structure

- Always generate both outputs after each completed interpretation:
  - one readable and polished HTML report (modern, interactive);
  - one accurately typeset PDF report (structured, print-friendly).
- HTML must include semantic structure (`header`, `main`, `section`, tables, heading hierarchy).
- Keep interpretation panels fully expanded by default (no hidden tab-only reading path that can cause missed content).
- Make `F`/`I`/`S` evidence tags visually prominent and immediately scannable.
- PDF must preserve hierarchy, spacing, and table legibility.
- If PDF engine dependencies are missing, install or report exactly what is missing and stop before claiming completion.

## Project Structure

```
china-political-interpretation/
├── SKILL.md                    # This file
├── start.sh                    # One-click startup script
├── config/
│   ├── .env                    # Runtime configuration (API keys)
│   ├── .env.example            # Configuration template
│   └── trusted_sources.json    # Trusted source definitions
├── frontend/                   # React + Vite + TypeScript + Tailwind
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx             # Main application
│   │   └── components/         # UI components
│   └── dist/                   # Build output
├── backend/
│   ├── api/
│   │   ├── app.py              # FastAPI main server
│   │   └── services/
│   │       └── task_runner.py  # LLM-powered analysis pipeline
│   ├── core/                   # Core analysis scripts
│   │   ├── llm_client.py       # 🤖 LLM client (OpenAI-compatible)
│   │   ├── content_extractor.py # URL/Image/PDF extraction
│   │   ├── build_research_queries.py # 🤖 LLM material understanding
│   │   ├── fetch_context_results.py
│   │   ├── generate_analysis_outline.py # 🤖 LLM deep analysis
│   │   └── search_engine.py    # Multi-provider search
│   ├── reports/                # Report renderers
│   │   ├── render_llm_reports.py   # 🤖 LLM HTML/PDF generation
│   │   ├── render_html_report.py   # HTML output
│   │   ├── render_pdf_report.py    # PDF output
│   │   └── render_analysis_web_pdf.py  # Legacy combined renderer
│   └── requirements.txt
├── desktop/                    # Electron desktop app
│   └── electron/
├── tests/                      # Test suite
├── docs/                       # Architecture documentation
├── scripts/                    # Quality gate scripts
├── agents/
└── references/
```

## References
- Read `references/analysis-framework.md` for lens-by-lens interpretation prompts.
- Read `references/source-playbook.md` for source tiers and query strategy.

## Boundaries
- Avoid unsupported certainty when evidence is thin.
- Distinguish party position, state position, local implementation, and media framing.
- State data gaps and propose verification steps instead of guessing.
