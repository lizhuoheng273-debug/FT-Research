<p align="center"><a href="README.md"><b>简体中文</b></a> | English</p>

<h1 align="center">FT-Research · Personal AI Finance Research Workbench</h1>

<p align="center">
  <a href="https://research.vincentli-website.com">🌐 Live Demo</a> ·
  <a href="#screenshots">Screenshots</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#deployment">Deployment</a> ·
  <a href="#owner--guest-system">Owner / Guest</a>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

> **Turn scattered research signals into verifiable leads.**
>
> FT-Research unifies AI hot topics, evidence-first financial news, daily market review, stock research, and AI conversations into one deployable personal research platform, powered by a **server-hosted GLM model** with owner/guest isolation and cloud deployment. A public demo is live; clone it to self-host.

## Live Demo

**<https://research.vincentli-website.com>** — open the landing page and click "Continue as guest" (guest model calls are rate-limited, and guest data is isolated from the owner).

## Screenshots

**Landing page** — public entry with one-click guest access

![FT-Research landing page](docs/screenshots/ft-landing.png)

<table>
<tr>
<td width="50%">

**Daily market review** — indices, market structure, and an AI closing summary with transparent data freshness

![Daily market review](docs/screenshots/ft-review.png)

</td>
<td width="50%">

**Financial news** — global hot-topic ranking with traceable, source-linked key points

![Financial news](docs/screenshots/ft-finance-news.png)

</td>
</tr>
<tr>
<td width="50%">

**AI hot topics** — Top-5 ranking plus sortable / pinnable / hideable RSS subscription streams

![AI hot topics](docs/screenshots/ft-ai-news.png)

</td>
<td width="50%">

**Stock research** — quotes + financials + a "let AI read this stock" context entry

![Stock research](docs/screenshots/ft-stock.png)

</td>
</tr>
</table>

---

## Features

Navigation is two-level: the **AI section** (news and reports) and the **Finance section** (quotes and review).

### AI section

| Page | Capabilities |
|---|---|
| 🤖&nbsp;**AI hot topics** (`/ai/news`) | Top-5 hot-topic ranking · sortable / pinnable / hideable RSS streams sorted by publish time · per-source refresh status (success / failure / cache fallback) |
| 📰&nbsp;**Report center** (`/ai/daily`) | AI daily / weekly / monthly reports **solidified daily at 08:00** by a scheduled job, parsed from the web and archived for later reading |
| 💬&nbsp;**AI conversation workspace** (`/ai/conversations`) | Server-hosted GLM (**the key never leaves the backend**) · NDJSON streaming with **interrupt-and-resume** · session history persisted in SQLite and revisitable · enter **with context from any page** |

### Finance section

| Page | Capabilities |
|---|---|
| 📊&nbsp;**Daily market review** (`/finance/review`) | Indices · market structure · an **AI closing brief generated automatically after market close** (scheduled, idempotent, context-only, never advisory) · full history |
| 📡&nbsp;**Financial news** (`/finance/news`) | **Evidence-first** aggregation: key points link back to sources · global headlines · a Following stream · refresh per source with transparent status |
| 🔍&nbsp;**Stock research** (`/finance/stocks/:code`) | Normalized debounced search · A-share / US / HK quotes and key financials · one site-wide entry · **bulk watchlist import** · "let AI read this stock" carries context into the conversation |
| ⚔️&nbsp;**Bull–bear debate** (`/finance/debate`) | Multi-agent: an objective fact brief → bull and bear researchers argue → a neutral moderator summarizes consensus and disagreement, **deliberately producing no trade calls** |
| ⭐&nbsp;**Watchlist** (`/finance/watchlist`) | Paste a batch of codes to add · single-table overview · hand it all to AI |

> **Boundaries**: objective data curation and public information aggregation only — **no stock picks, no forecasts, no trade timing**. The AI explains and organizes context; judgment stays with the user.

## Architecture

```
FT-Research/
├── backend/                FastAPI :8900
│   ├── app.py                application entry
│   ├── financial_news.py     evidence-first financial news pipeline
│   ├── financial_hotlist.py  global financial hot-topic ranking
│   ├── financial_editorial.py key-point editing with source attribution
│   ├── news_sources.json     RSS source config (refresh per source)
│   ├── aihot_api.py          AI HOT read-only proxy (ETag cache + failure fallback)
│   ├── aihot_reports.py      daily / weekly / monthly report center (08:00 daily job)
│   ├── market_review.py      daily review data
│   ├── market_review_brief.py post-close AI brief (idempotent, context-only)
│   ├── chat.py               AI conversations (server-hosted GLM, NDJSON streaming)
│   ├── conversation_routes.py session persistence and recovery
│   ├── auth.py / auth_routes.py  owner / guest auth (hashed passwords, guest tokens)
│   ├── ai_limits.py          model-call rate limits (identity / IP / input length)
│   ├── astock.py / gstock.py A-share / US / HK market data
│   ├── market.py             indices and market sentiment
│   └── debate.py             bull–bear debate orchestration
├── frontend/               Vite + React 19 + TypeScript :5899
├── deploy/tencent-lighthouse/  production deployment (compose / Caddy / preflight / backup)
└── docs/                   deployment and design docs
```

**Three automated pipelines**:

```
News      RSS / AI HOT → parse & dedupe → evidence tagging (traceable points) → hot list / streams / headlines
Reports   daily 08:00 job solidifies daily/weekly/monthly reports · post-close review brief (idempotent, no rerun after downtime)
Sessions  any page carries context → server-hosted GLM → NDJSON streaming (resumable) → SQLite history
```

## Quick Start

```bash
# Backend (:8900)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900

# Frontend (:5899)
cd frontend && npm install && npm run dev
# Open http://localhost:5899
```

AI conversations need a GLM API key configured as a server-side environment variable (never shipped to the frontend). News, review, and market data work out of the box.

## Deployment

A complete production setup for Tencent Cloud Lighthouse: Docker / compose orchestration, Caddy reverse proxy with automatic HTTPS, production preflight checks, and backup scripts.

- Full walkthrough: [`deploy/tencent-lighthouse/README.md`](deploy/tencent-lighthouse/README.md)
- Owner / guest production config: [`docs/OWNER_GUEST_DEPLOYMENT.md`](docs/OWNER_GUEST_DEPLOYMENT.md)

## Owner / Guest System

- **Owner**: generate a password hash with `python scripts/owner_password.py` and set `FT_OWNER_PASSWORD_HASH`; session history is stored server-side in SQLite.
- **Guest**: tokens live only in the current page's memory and expire on refresh or exit; the server rate-limits model calls by identity, IP, and input length; data is isolated from the owner.
- Set `FT_AUTH_SECURE_COOKIE=true` under HTTPS; keys and passwords never enter the repository.

## Tests

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -m "not live"   # offline unit tests + API validation
cd frontend && npm test          # frontend tests
```

About 90 tests across the frontend and backend.

## License

MIT

## Acknowledgments

Built as a second-generation fork of [Vibe-Research](https://github.com/simonlin1212/Vibe-Research) by Simon Lin (MIT): the quotes and debate dashboards build on upstream capability, while the AI news pipeline, report center, daily review briefs, AI conversation workspace, permission system, and cloud deployment are independent extensions.

## Disclaimer

For learning and research only; not investment advice. Markets carry risk — make independent decisions and verify everything yourself.
