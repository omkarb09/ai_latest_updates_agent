# 🤖 Daily AI Advancements Digest

An AI agent that searches the web each day and delivers a curated digest of the latest AI advancements — research papers, company engineering blogs, model releases, and industry news.

**Powered by:** Tavily (web search) + Groq model + GitHub Actions

---

## 📰 Sources Covered

This project collects results from research sites and company tech blogs, including arXiv, university labs (CMU, Stanford, MIT), industry labs (DeepMind, Anthropic, OpenAI, Meta), Hugging Face, and company engineering blogs (Netflix, DoorDash, Uber).

---

## 🚀 Setup (quick)

### 1. Fork / Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/ai_latest_updates_agent_claude.git
cd ai_latest_updates_agent_claude
```

### 2. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret Name | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (required)
| `TAVILY_API_KEY` | Your Tavily API key (required for live web search)

Optional (for email delivery): `SMTP_USER`, `SMTP_PASS`, `RECIPIENT_EMAIL`.

You may also set `MODEL_NAME` to override the default Groq model id used by the script.

### 3. Install dependencies locally

```bash
pip install -r requirements.txt
```

### 4. Enable GitHub Actions

Enable workflows in the **Actions** tab. The workflow is scheduled daily and supports manual runs.

### 5. Run locally

Dry-run (no API calls):

```bash
python scripts/ai_digest.py --dry-run
```

Real run (requires `GROQ_API_KEY` and `TAVILY_API_KEY`):

```bash
export GROQ_API_KEY="your-groq-key"
export TAVILY_API_KEY="your-tavily-key"
python scripts/ai_digest.py
```

---

## 📧 Optional: Email Delivery

To receive digests by email, set `DELIVERY_MODE: email` in the workflow and provide SMTP secrets listed above.

---

## 📅 Schedule

The digest runs daily by default (see `.github/workflows/daily-digest.yml` for the cron schedule). You can manually trigger the workflow from the Actions UI.

---

## 📁 Output

Digests are saved to the `digests/` folder:
- `digests/YYYY-MM-DD.md` — Human-readable Markdown
- `digests/YYYY-MM-DD.json` — Structured JSON

When parsing fails the script writes debugging files:
- `digests/YYYY-MM-DD_raw.txt` — full model output
- `digests/YYYY-MM-DD_candidate.txt` — extracted JSON candidate (if any)

---

## Notes & Troubleshooting

- This project uses Tavily for web search and Groq for generation. Ensure both `TAVILY_API_KEY` and `GROQ_API_KEY` are set for live runs.
- Use `--dry-run` to test formatting and CI without keys.
- If parsing fails, inspect the raw/candidate files in `digests/` and adjust `MODEL_NAME` or the `SYSTEM_PROMPT` as needed.
