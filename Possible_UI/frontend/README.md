# Q&A Evaluation Studio — Frontend

A multi-page enterprise UI for an internal AI-evaluation workspace. Users upload
documents / research links, pick a primary Bedrock evaluation model and a secondary
provider to test (RavenPack, Nexa, …), generate questions (Manual / Assisted /
Fully-Automatic), run them, and review groundedness, hallucination risk, shortfalls,
evidence, and final summaries — with auditable export.

> Internal evaluation & research support only. All generated outputs require human review.

## Stack

- **Vite + React 18** SPA
- **TailwindCSS** design system (navy chrome, soft-blue accents, success/warning/error tones)
- **React Router** for the 12 pages
- **lucide-react** icons, **recharts** for the results charts

## Run it

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # production build into dist/
```

(Node was installed via `winget install OpenJS.NodeJS.LTS`. If `node` isn't on your
PATH in a new shell, open a fresh terminal so the updated PATH is picked up.)

## Pages (left-to-right evaluation journey)

| # | Route | Page |
|---|-------|------|
| 01 | `/` | Welcome / Terms & Conditions (gate) |
| 02 | `/dashboard` | Story Mode Dashboard (stepper + run summary) |
| 03 | `/sources` | Source Setup (upload docs / add links, source quality) |
| 04 | `/models` | Model & Provider Selection |
| 05 | `/qa-mode` | Q&A Generation Mode (Manual / Assisted / Automatic) |
| 06 | `/workspace` | Evaluation Workspace (chat + config + evidence inspector) |
| 07 | `/assisted` | Assisted Q&A Review (approve / edit / reject) |
| 08 | `/monitor` | Fully Automatic Run Monitor (live pipeline) |
| 09 | `/results` | Results Dashboard (metrics + charts + table) |
| 10 | `/evidence/:id` | Evidence Detail View |
| 11 | `/history` | Run History / Audit Trail |
| 12 | `/settings` | Settings |

## Project structure

```
src/
  api/            # ← backend seam (see below)
    client.js     #   API_BASE, USE_MOCK flag, fetch wrapper
    index.js      #   api.getModels(), api.runEvaluation(), … (mock today)
  components/      # reusable: Sidebar, Stepper, StatusChip, Card, Button,
                   # ChatBubble, EvaluationCard, EvidenceCard, ResultsTable,
                   # JsonViewer, ModelCard, ProviderCard, ModeCard, MetricCard,
                   # ExportButton, ProgressTimeline, SourceUploadCard, ui.jsx
    layout/        # AppLayout, Sidebar, TopStatusBar
  context/         # RunContext — shared evaluation-run state across the wizard
  data/            # placeholders.js — realistic banking/research sample data
  lib/             # tone.js — verdict/groundedness/support → chip tone mapping
  pages/           # 01_… 12_… the twelve screens
```

## Wiring to the Python backend

Everything goes through **one seam** so no UI code changes when you go live:

1. Open `src/api/client.js` and set `USE_MOCK = false`.
2. Set the API base via `VITE_API_BASE` (defaults to `/api`). During `npm run dev`,
   `vite.config.js` proxies `/api` → `http://localhost:8000` — point that at your
   FastAPI/Flask app.
3. In `src/api/index.js`, each method already has the real `request('/path', …)` call
   next to its mock body; the mock branch simply returns sample data today. Implement
   the endpoints to match (`/models`, `/providers`, `/sources`, `/questions/generate`,
   `/evaluations/run`, `/runs`, …) and the whole app switches over.

The expected response shapes are exactly the objects in `src/data/placeholders.js`.

## Notes

- All sample content is illustrative — **no real customer data**.
- Empty / loading / success / warning / error states are present throughout.
- Desktop-first, tablet-friendly responsive layouts.
