<p align="center"><b>English</b> · <a href="README.uk.md">Українська</a></p>

<p align="center">
  <h1 align="center">📝 Multi-Agent Long-Form Document Generator</h1>
  <p align="center">
    <strong>An async LLM pipeline that plans, researches, writes and reviews structured documents with real citations, then renders them to DOCX with deterministic code</strong>
  </p>
  <p align="center">
    <a href="#features">Features</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#design-decisions">Design decisions</a> •
    <a href="#tech-stack">Tech stack</a> •
    <a href="#getting-started">Getting started</a> •
    <a href="#usage">Usage</a>
  </p>
</p>

---

## Overview

A Python application that turns a table of contents and a topic into a long, structured document (academic-style reports, coursework, theses). Several LLM roles work in an async pipeline: a planner designs the structure, a research stage pulls sources from scientific databases (OpenAlex) and the web (Tavily), a writer produces each section from those sources, and a reviewer scores the result and points to the sections worth regenerating.

The model writes text, but everything that has to be exact is done in code: citation numbering, the bibliography and document formatting according to the Ukrainian standard **DSTU 8302:2015**. Runs from a web UI or the CLI and supports **OpenAI and Gemini**, with presets to balance cost and quality.

## Features

- **🤖 Multi-agent pipeline** – async orchestration of separate roles:
  - **Planner / Blueprint** – analyses the topic and the table of contents, classifies sections (theory / practice / introduction / conclusions) and builds a content blueprint for each one: main thesis, subtopics, terms to define
  - **Research** – collects sources in parallel from **OpenAlex** (scientific papers) and **Tavily** (web search), then aggregates and de-duplicates them. Ukrainian queries are batch-translated to English first, so the search hits international databases
  - **Writer** – generates each section from its own pool of sources and the context of neighbouring sections; introduction and conclusions are written in a separate pass
  - **Reviewer** – a final pass that returns a structured JSON review: score 1–10, strengths, issues per section with severity, and a list of sections recommended for regeneration

- **🔁 Targeted regeneration** – any single section can be regenerated without rerunning the whole document

- **⚡ Concurrency** – research and section generation run concurrently with `asyncio`, which matters on documents with dozens of sections

- **🔌 Pluggable providers** – an abstract async interface (`BaseAIProvider`) with **OpenAI** and **Gemini** implementations and a mock provider for offline runs. Retries with exponential backoff (`tenacity`)

- **🎚️ Quality presets** – `economy` / `standard` / `quality`: a main model for body sections and a cheaper helper model for service steps (planning, blueprints, query translation, introduction and conclusions, review)

- **📚 Deterministic formatting** – bibliography per **DSTU 8302:2015** (Cyrillic and Latin sources, sorting, renumbering) and a DOCX layout built with python-docx: A4, fixed margins, Times New Roman 14 pt, 1.5 spacing, each chapter on a new page

- **🌐 Web UI** – Flask dashboard with an interactive table-of-contents editor, live generation logs over **Server-Sent Events (SSE)**, model / preset / topic controls and per-section regeneration

- **💻 CLI mode** – full run from the command line for automation

- **🧩 Typed domain** – Pydantic models for sources, sections, plans and reviews; all prompts are **Jinja** templates in one place (`core/prompts.py`)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Web UI / CLI                        │
│                (Flask + SSE  /  argparse)               │
└──────────────────────┬──────────────────────────────────┘
                       │
              ┌────────▼─────────┐
              │   Orchestrator   │
              │     (async)      │
              └────────┬─────────┘
   plan → blueprints → research → body sections → intro / conclusions → review
          │              │              │
          ▼              ▼              ▼
   ┌────────────┐  ┌──────────────┐  ┌────────────────┐
   │ LLM        │  │ Research     │  │ DOCX + DSTU    │
   │ providers  │  │ OpenAlex +   │  │ docx_writer    │
   │ OpenAI /   │  │ Tavily       │  │ dstu_formatter │
   │ Gemini     │  │ (aggregated) │  │                │
   └────────────┘  └──────────────┘  └────────────────┘
```

## Design decisions

- **The model never owns the citations.** The writer only puts local markers like `[3]` into the text. Code maps them to source IDs, ignores numbers that don't exist, renumbers them across the whole document and builds the bibliography only from sources that are actually cited.
- **Formatting is code, not a prompt.** Layout and the bibliography standard are applied by python-docx and a dedicated formatter, so the output is the same on every run regardless of the model.
- **Structured outputs everywhere they are parsed.** Plans, blueprints, query translations and reviews are requested as JSON and parsed into Pydantic models. Optional steps such as query translation and the review fail softly: a malformed response skips that step instead of breaking the run.
- **Cost control by role.** Expensive models are used only where quality is visible (body sections); everything else goes to a cheap helper model.

## Tech stack

| Layer | Technology |
|-------|-----------|
| AI / LLM | OpenAI (gpt-4o / gpt-4o-mini), Google Gemini (2.5-flash) |
| Orchestration | `asyncio`, concurrent research and generation |
| Source research | OpenAlex API (scientific papers), Tavily API (web) |
| Reliability | `tenacity` (retries with backoff), `httpx` (async HTTP) |
| Domain models | Pydantic v2 |
| Prompts | Jinja2 templates |
| Output | python-docx, DSTU 8302:2015 |
| Web | Flask + Flask-CORS, Server-Sent Events (SSE) |
| Configuration | YAML + python-dotenv |

## Project structure

```
kursova_generator/
├── main.py                  # CLI entry point, provider wiring, pipeline run
├── config.yaml              # Providers, presets, research and project settings
├── requirements.txt
│
├── core/                    # Core
│   ├── orchestrator.py      # Async pipeline (plan → research → generation → review)
│   ├── models.py            # Pydantic models (Source, Section, Plan, WorkReview, ...)
│   ├── prompts.py           # Jinja templates for every prompt
│   ├── toc_parser.py        # Table-of-contents parser (hierarchy, numbering)
│   ├── docx_writer.py       # DOCX layout
│   ├── dstu_formatter.py    # Bibliography per DSTU 8302:2015
│   └── research/            # Source research
│       ├── aggregator.py    # Aggregation + de-duplication
│       ├── openalex.py      # OpenAlex client
│       └── tavily.py        # Tavily client
│
├── ai_providers/            # Pluggable LLM providers
│   ├── base_provider.py     # Abstract async interface (ABC)
│   ├── openai_provider.py   # OpenAI
│   ├── gemini_provider.py   # Google Gemini
│   └── mock_provider.py     # Mock for offline runs
│
├── web/                     # Web UI
│   ├── app.py               # Flask server with SSE streaming
│   ├── templates/
│   └── static/
│
├── input/                   # Sample tables of contents (toc.txt)
└── output/                  # Generated documents (git-ignored)
```

## Getting started

### Prerequisites
- Python 3.10+
- An OpenAI and/or Gemini API key
- (Optional) a Tavily API key for web research

### Installation

```bash
git clone https://github.com/solabuch/kursova_generator.git
cd kursova_generator

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
TAVILY_API_KEY=...        # optional, for web research
```

Adjust `config.yaml` – pick a preset and project settings:

```yaml
default_preset: standard   # economy | standard | quality

presets:
  standard:
    main:   {provider: gemini, model: gemini-2.5-flash}
    helper: {provider: openai, model: gpt-4o-mini}

project_settings:
  work_type: coursework    # coursework | report | essay | diploma
  input_toc_file: "input/toc.txt"
  output_dir: "output/"
```

## Usage

### 🌐 Web UI (recommended)

```bash
python web/app.py
```

Open `http://127.0.0.1:5000`. The dashboard lets you edit the table of contents, choose the model and preset, follow generation logs live and regenerate individual sections.

### 💻 CLI

```bash
python main.py --topic "Your topic" --toc input/toc.txt --output output/work.docx
# optionally pass formatting guidelines:
python main.py --topic "..." --methodology guidelines.md
```

### Output

A ready `.docx` in `output/`: a structured document with sections, in-text citations and a bibliography formatted per DSTU 8302:2015.

## How it works

1. **Table-of-contents parsing** – builds a hierarchical structure with section numbering
2. **Planning and blueprints** – the planner classifies sections and builds a content blueprint for each one
3. **Research (concurrent)** – sources are collected for every section from OpenAlex and Tavily, then aggregated and de-duplicated
4. **Generation (concurrent)** – the writer produces each section from its sources and context; introduction and conclusions are written in a separate pass
5. **Assembly** – sections are merged, citations renumbered, the bibliography formatted per DSTU 8302:2015 and the result exported to DOCX
6. **Review** – a final LLM pass scores the document and lists sections worth regenerating

## License

Built for learning and portfolio purposes.
