# LLM Options for CPG Analytics Insights

---

## Can Ollama Run in Docker So Anyone Can Install It?

**Yes — and it is the recommended way to ship it to others.**

Ollama has an official Docker image (`ollama/ollama`).
You add it to `docker-compose.yml` alongside postgres, api, and ui.
Anyone who runs `docker compose up` gets a fully working local LLM — no manual install, no API key, no internet dependency after the first pull.

### What "docker compose up" looks like for a new installer

```
Step 1 — docker pulls the ollama/ollama image (~1 GB)       ← happens once
Step 2 — ollama container starts                            ← ~5 seconds
Step 3 — an init step pulls the model (e.g. llama3.1:8b)  ← ~4.7 GB download, once
Step 4 — model is saved to a named Docker volume           ← persists across restarts
Step 5 — api and ui containers start, point to ollama      ← normal startup
```

On every subsequent `docker compose up` (same machine):
- Steps 1, 3 are skipped — image and model are already cached
- Total startup time: ~10 seconds

### docker-compose addition (what it looks like)

```yaml
services:
  ollama:
    image: ollama/ollama          # official image, ~1 GB
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama  # model weights stored here (4–5 GB)
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s           # give it time to start

  ollama-init:                    # runs once, pulls the model, then exits
    image: ollama/ollama
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["ollama", "pull", "llama3.1"]
    environment:
      OLLAMA_HOST: http://ollama:11434
    restart: "no"                 # exit after pull completes

  api:
    ...
    depends_on:
      ollama:
        condition: service_healthy
    environment:
      LLM_BASE_URL: http://ollama:11434/v1
      LLM_MODEL: llama3.1

volumes:
  pg_data:
  ollama_data:                    # model weights survive container restarts
```

### How the api service talks to Ollama

Inside Docker Compose, services talk to each other by service name.
The api container reaches Ollama at `http://ollama:11434/v1`.
That URL is passed as an env var — no hardcoding.

```
[api container]  →  POST http://ollama:11434/v1/chat/completions
                          ↓
                    [ollama container]
                    runs llama3.1:8b locally
                          ↓
                    returns JSON response
```

### Minimum machine requirements

| Model | Disk (for volume) | RAM needed | CPU inference speed |
|---|---|---|---|
| `llama3.1:8b` | 4.7 GB | 8 GB free | ~5–15 s per response |
| `mistral:7b` | 4.1 GB | 8 GB free | ~5–12 s per response |
| `phi3:mini` | 2.2 GB | 4 GB free | ~2–5 s per response |

Most developer laptops (16 GB RAM) handle `llama3.1:8b` comfortably.
The machine does not need a GPU — CPU works, just slower.

### What if the team's machines are too small?

Option A — use `phi3:mini` instead (2.2 GB, works on 8 GB RAM, noticeably less capable)

Option B — run Ollama on one shared machine (a desktop, a workstation, a cloud VM) and
point everyone's `LLM_BASE_URL` to that machine's IP. The rest of the stack
(postgres, api, ui) runs locally per person; only the LLM is shared.

Option C — switch to Groq (free cloud API, no machine requirements, see below).
The only change is the env var value. The code is identical.

### What a first-time installer does

```bash
git clone <repo>
cd cpg-analytics
cp .env.example .env        # no keys needed
docker compose up --build   # that's it
```

They wait ~10 minutes on first run (model download).
After that, `docker compose up` starts in ~10 seconds every time.

---


## What You're Trying to Do

Your platform already does the hard part:
- Aggregates revenue by category, region, and month
- Builds a compact "bounded context" (< 1,000 tokens) from the data
- Has `/insights` and `/ask` endpoints ready to receive an LLM response

The only missing piece is wiring an LLM to those endpoints.
Because you send **aggregates only** (not raw rows), even a small local model handles it well.

---

## The Three Options

### 1. Ollama — Local, Free, Private (Recommended to Start)

Ollama runs open-source LLMs directly on your laptop or server.
No API key. No internet. No cost. Data never leaves your machine.

**How it works:**

```
Your API server
      │
      │  POST /v1/chat/completions
      ▼
Ollama (localhost:11434)
      │
      │  runs model inference on CPU/GPU
      ▼
  Response text
      │
      ▼
Your /insights or /ask endpoint
```

Ollama exposes an **OpenAI-compatible REST API**, so the code change is minimal:
- `base_url` → `http://localhost:11434/v1`
- `api-key` → `"ollama"` (any string; ignored)
- `model` → name of the model you pulled (e.g. `llama3.1`)

**Models to use for this use case:**

| Model | Size | RAM needed | Good for |
|---|---|---|---|
| `llama3.1:8b` | 4.7 GB | 8 GB | Best balance — smart, fast |
| `mistral:7b` | 4.1 GB | 8 GB | Slightly faster, very capable |
| `gemma2:9b` | 5.4 GB | 10 GB | Strong reasoning |
| `phi3:mini` | 2.2 GB | 4 GB | Very fast; weaker on long context |
| `llama3.1:70b` | 40 GB | 64 GB | Near-GPT-4 quality; needs big machine |

**For your laptop:** Start with `llama3.1:8b` or `mistral:7b`.
They handle revenue summaries and Q&A well within your bounded context size.

**Setup (5 minutes):**

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download from https://ollama.com

# 2. Pull a model
ollama pull llama3.1        # 4.7 GB download

# 3. Start the Ollama server (auto-starts on Mac after install)
ollama serve

# 4. Test it works
curl http://localhost:11434/v1/models
```

**What to change in the codebase:**

Only two things in `src/api/llm.py`:
- Base URL: `http://localhost:11434/v1`
- Auth header: `Authorization: Bearer ollama` (any string works)

The prompt structure, fallback logic, and endpoints stay exactly the same.
Ollama speaks the OpenAI chat completions format natively.

**Limitations:**
- Inference is slower than cloud APIs (3–10 seconds per response on CPU)
- Quality is slightly below GPT-4 for complex analysis
- Cannot run in Docker compose on most laptops (needs GPU pass-through or a dedicated machine)

---

### 2. Groq — Free Cloud API, Extremely Fast

Groq runs open-source models (Llama, Mistral, Gemma) on custom silicon.
It is the fastest inference available anywhere — responses in under 1 second.

**Free tier:** 6,000 requests/day on Llama 3.1 70B. More than enough for analytics Q&A.

**Models available free:**
- `llama-3.1-70b-versatile` — near-GPT-4 quality, very fast
- `llama-3.1-8b-instant` — fastest option
- `mixtral-8x7b-32768` — good for long contexts

**API format:** OpenAI-compatible.
- `base_url` → `https://api.groq.com/openai/v1`
- `api_key` → from [console.groq.com](https://console.groq.com) (free sign-up)

**Why this is better than Azure/DeepSeek for your use case:**
- Free tier is generous
- Much faster than DeepSeek
- Llama 70B is genuinely good at business data summaries
- OpenAI-compatible → same minimal code change as Ollama

**Setup:**
```bash
# 1. Sign up at https://console.groq.com (free, no credit card)
# 2. Create an API key
# 3. Set in .env:  GROQ_API_KEY=gsk_xxxx
```

---

### 3. Google Gemini — Free Tier, Multimodal

Google's Gemini Flash has a generous free tier and can handle text + images.

**Free tier:** 15 requests/minute, 1 million tokens/day on Gemini 1.5 Flash.
That is effectively unlimited for analytics Q&A.

**API format:** OpenAI-compatible via `https://generativelanguage.googleapis.com/v1beta/openai/`

**Setup:**
```bash
# 1. Go to https://aistudio.google.com — sign in with Google account
# 2. Create an API key (free, no billing required)
# 3. Set in .env:  GOOGLE_API_KEY=AIza_xxxx
```

---

## Comparison

| Option | Cost | Speed | Quality | Privacy | Complexity |
|---|---|---|---|---|---|
| **Ollama (local)** | Free forever | Slow on CPU, fast on GPU | Good (8B) / Great (70B) | Perfect — no data leaves | Low |
| **Groq** | Free tier (6k/day) | Extremely fast (< 1s) | Great (Llama 70B) | Data sent to Groq | Low |
| **Gemini Flash** | Free tier (1M tokens/day) | Fast (1–2s) | Great | Data sent to Google | Low |
| **OpenAI GPT-4o** | ~$2.50/1M tokens | Fast | Best | Data sent to OpenAI | Low |
| **Azure OpenAI** | Pay-per-use | Fast | Best | Can be private | Medium |

---

## Recommended Path

**Phase 1 — Today (development and demos):**
Use **Ollama in Docker** with `llama3.1:8b`.
- Add the `ollama` and `ollama-init` services to `docker-compose.yml`
- Anyone on the team runs `docker compose up` — no setup beyond Docker itself
- Zero cost, works offline, data stays on the machine
- One-time ~4.7 GB model download; cached in a Docker volume after that

**Phase 2 — Team is on low-spec machines or wants faster responses:**
Switch to **Groq** (free cloud API).
- Free account at console.groq.com — no credit card needed
- Llama 3.1 70B — much smarter than the local 8B model, responds in < 1 second
- Change is one env var (`LLM_BASE_URL`) and one API key in `.env`
- The rest of the stack (Docker compose, endpoints, prompts) is untouched

**Phase 3 — Production / sensitive data:**
- Data is internal/sensitive → run Ollama on a **dedicated server or VM** (8–16 GB RAM)
  and point all instances at it via `LLM_BASE_URL=http://<server-ip>:11434/v1`
- Data can leave the org → Groq or Gemini Flash stay free at typical analytics volumes

---

## What Your Bounded Context Already Does Right

The `/ask` endpoint builds a context like this before calling the LLM:

```
=== CPG Analytics — Data Summary Context ===
Date range : 2022-07-01 to 2024-07-21
Total revenue : $751,785.88

Revenue by Category:
  Beverages: $273,408.23 (36.4%)
  Snacks: $180,206.28 (24.0%)
  ...

Revenue by Region:
  SOUTHEAST: $188,444.39 (25.1%)
  ...

Monthly Revenue (last 12 months):
  2023-08: $27,437.55
  ...
```

This is around 600–800 tokens — well within every model's context window.
No raw transactions are sent. The LLM only sees what a human analyst would put in a brief.

This design means you can swap any LLM in or out without changing prompts or endpoints.

---

## How to Re-wire the Code (Ollama Example)

When you're ready, the change is in `src/api/llm.py` (currently removed).
The pattern is:

```
1. Restore the _call_llm() async function
2. Change base URL to http://localhost:11434/v1
3. Change auth header to: Authorization: Bearer ollama
4. Change model name to: llama3.1
5. Everything else (prompts, fallback, routes) stays the same
```

For Groq, only the base URL and key change:
```
base URL: https://api.groq.com/openai/v1
auth:     Authorization: Bearer {GROQ_API_KEY}
model:    llama-3.1-70b-versatile
```

For Gemini Flash:
```
base URL: https://generativelanguage.googleapis.com/v1beta/openai
auth:     Authorization: Bearer {GOOGLE_API_KEY}
model:    gemini-1.5-flash
```

---

## Summary

| Question | Answer |
|---|---|
| Can Ollama run in Docker? | Yes. Official `ollama/ollama` image. Add to docker-compose. |
| Can anyone install it with one command? | Yes. `docker compose up` — no manual steps beyond Docker. |
| Is there a one-time setup cost? | One-time model download (~4.7 GB). Cached in a Docker volume after that. |
| Does data leave the machine? | No. Fully local. |
| Does it speak the OpenAI API format? | Yes. Same format — only the base URL and model name change. |
| Is it good enough for analytics Q&A? | Yes. Llama 3.1 8B handles revenue summaries and Q&A well. |
| What if machines are too slow or too small? | Switch to Groq free tier — same code, same format, 50× faster, cloud-hosted. |
| When should we use a paid API? | When you need the highest reasoning quality or a guaranteed uptime SLA. |

---

### Decision Tree

```
Does the team have Docker installed?
        │
        YES
        │
        ▼
Does anyone have 8 GB RAM free?
        │
   YES  │  NO
        │   └──► Use phi3:mini (2.2 GB) or switch to Groq free tier
        ▼
Start with Ollama in Docker compose (llama3.1:8b)
        │
        ▼
Is response speed acceptable (5–15 s)?
        │
   YES  │  NO
        │   └──► Switch to Groq (free, < 1 s, same code)
        ▼
Is data sensitive / must stay on-prem?
        │
   YES  │  NO
        │   └──► Groq or Gemini Flash remain free at analytics volumes
        ▼
Run Ollama on a shared server, point all
instances at it via LLM_BASE_URL env var
```

*Start with Ollama in Docker. It is free, private, and anyone can run it.
Switch to Groq when speed or machine size becomes a constraint.*
