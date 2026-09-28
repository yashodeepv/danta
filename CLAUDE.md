# Danta — CLAUDE.md

Danta is a **deterministic spec-to-code compiler**. A plain-text Markdown spec
compiles to Python (FastAPI), JavaScript (Express), and Java (Spring Boot) —
with test suites and CI configs included. No ML model in the compiler; same
spec always produces the same code.

## Quick orientation

```
danta/                  Python package (the compiler)
  spec/                 Markdown parser → IR (constants, entities, flows, screens)
  ir2/                  Second IR: typed flow graph, expression checker, sexpr emitter
  sim/                  Simulator: synthesizes test scenarios, runs every path
  check/                Semantic validation rules
  codegen/              Code generators (Python, JavaScript, Java) + formatter
  gen/                  AI-assisted generation helpers
  app/
    pipeline.py         Main build() function: parse → IR → sim → codegen
    server.py           Local dev server (serves the Studio at localhost:8765)
    prompt.py           Builds the LLM system prompt
    static/
      index.html        Landing page (marketing — no Studio)
      studio.html       Spec Studio + Docs (full app; Pyodide-injected for Pages)
  tests/                112 tests (unittest); run with:
                          python3.11 -m unittest discover danta/tests -q
tools/
  build_site.py         Builds site/ for GitHub Pages:
                          index.html  → site/index.html  (landing, copied as-is)
                          studio.html → site/studio.html (Pyodide loader injected)
                          danta.zip   → site/danta.zip   (bundled Python sources)
                          danta-skill.md → site/danta-skill.md
  danta-skill.md        LLM system prompt covering the full Danta grammar
site/                   Build output — gitignored
```

## How to run

```bash
# Install (once)
pip install -e .

# Local Studio (real Python backend, no Pyodide)
danta studio                        # opens http://localhost:8765
danta studio --port 8800 --no-browser

# Build the GitHub Pages site
python3.11 tools/build_site.py      # writes to site/
cd site && python3.11 -m http.server 8800   # preview locally

# CLI
danta check  myspec.md              # validate; exit 1 on errors
danta show   myspec.md              # print compiled flows as outlines
danta simulate myspec.md            # run all test paths
danta build  myspec.md --verify     # generate + run each project's own tests
danta prompt                        # print the LLM system prompt

# Tests
python3.11 -m unittest discover danta/tests -q    # 112 tests, 2 skipped
```

## Key architecture facts

**Pipeline** (`danta/app/pipeline.py → build(text)`):
1. Strip LLM fences → parse spec → semantic errors
2. Synthesize test scenarios (`danta/sim/`)
3. Run simulator on every scenario; `SimError` (missing mock) is caught per-run
   and recorded as `skipped` — it never crashes the whole build
4. Codegen (`danta/codegen/`) → format → store in `_remember()` cache
5. Return a dict with `errors`, `flows` (with `runs`, `coverage`), `screens`, `project`

**Simulator** (`danta/sim/runner.py`):
- `run(flow, input, mocks)` — executes every step; Call steps need mocks
- `SimError` is raised when a mock is missing; pipeline catches it gracefully
- `synthesize(rng, flow, hints)` — auto-generates scenarios + mocks

**Pyodide build** (`tools/build_site.py`):
- Injects a `<script>…</script>` loader before `<script>\n(function () {` in `studio.html`
- The loader overrides `window.fetch` to intercept `/api/` requests and route them to
  `danta/web.py` running in Pyodide (WASM)
- Fetch shim must handle URL objects: `typeof url === 'string' ? url : (url.url || url.href || String(url))`

**Two-page site structure** (as of commit `d1d224b`):
- `index.html` — pure landing page (hero, features, how-it-works, footer). No Studio, no docs. "Open Studio →" links to `studio.html`.
- `studio.html` — full Studio + Docs. Has a "← Home" back-link. Pyodide loader injected here by `build_site.py`.

## CSS / design tokens

All colours are CSS custom properties on `:root` (light) / `[data-theme="dark"]` + `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` (dark). Key tokens:

```
--accent: #c2410c  (light) / #f59e0b (dark) — amber/orange brand colour
--paper, --surface, --sunk, --raised — background hierarchy
--ink, --muted, --faint — text hierarchy
--line, --line-strong — borders
--sans: "DM Sans", ...
--display: "Bricolage Grotesque", ...
--mono: "JetBrains Mono", ...
```

Step-type colours: `--trigger` (blue), `--call` (sky), `--compute` (purple), `--validate` (orange), `--branch` (pink), `--persist` (green), `--notify` (teal).

Dark-mode toggle: `data-theme-set` attribute on buttons; saved to `localStorage('danta-theme')`.

## Docs toggle (studio.html)

The Docs view (`#docs-view`) is toggled by hiding `<main>` and showing the docs div:

```javascript
studioMain.style.display = docsShown ? 'none' : 'grid';
docsView.style.display   = docsShown ? 'block' : 'none';
```

**Do not** use the `hidden` attribute on `<main>` — `main { display: grid }` in author CSS overrides UA `[hidden]`.

## What NOT to do

- Do not add CCN (ComputeCell Networks) framing or neuron-level work here — that lives in a separate repo.
- Do not commit `site/` — it's gitignored.
- Do not break the `<script>\n(function () {` pattern in `studio.html` — the build injection depends on it.
- Do not add ML models to the compiler; Danta is deterministic by design.

## Current state (as of 2026-09-28)

- All 112 tests pass.
- Landing page + Studio are split into two pages; GitHub Pages build produces both.
- `SimError` from the simulator is caught per test-run (no more crashes on complex specs with unmocked Call steps).
- Local server: `python3.11 -m http.server 8800` in `site/` (PID may vary; start fresh if needed).
- No GitHub remote yet — repo is local only on `main` branch.
