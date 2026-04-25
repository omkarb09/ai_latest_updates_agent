# 🤖 Daily AI Advancements Digest

An AI agent that searches the web every day and delivers a curated digest of the latest AI advancements — research papers, company engineering blogs, model releases, and industry news.

**Powered by:** Claude (claude-sonnet-4) + Anthropic Web Search Tool + GitHub Actions

---

## 📰 Sources Covered

| Category | Sources |
|---|---|
| **Research** | arXiv, Carnegie Mellon University, Stanford AI Lab, MIT CSAIL |
| **Industry Labs** | Google DeepMind, Anthropic, OpenAI, Meta AI, Hugging Face |
| **Company Tech Blogs** | Netflix, DoorDash, Uber Engineering |
| **News** | AI industry news & breakthroughs |

---

## 🚀 Setup (5 minutes)

### 1. Fork / Clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/ai-digest.git
cd ai-digest
```

### 2. Add GitHub Secret

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (or set `ANTHROPIC_API_KEY` for Anthropic as a fallback) |

### 3. Enable GitHub Actions

Go to the **Actions** tab in your repo and enable workflows if prompted.

### 4. Run manually to test

Go to **Actions → Daily AI Digest → Run workflow**

---

## 📧 Optional: Email Delivery

To receive digests via email instead of (or in addition to) committing to the repo:

1. In `.github/workflows/daily-digest.yml`, set `DELIVERY_MODE: email` and uncomment the SMTP variables.
2. Add these secrets to your repo:

| Secret | Description |
|---|---|
| `SMTP_USER` | Your Gmail address |
| `SMTP_PASS` | Gmail [App Password](https://myaccount.google.com/apppasswords) (not your regular password) |
| `RECIPIENT_EMAIL` | Where to send the digest |

---

## 📅 Schedule

By default, the digest runs at **7:00 AM UTC** daily. To change the time, edit the cron expression in `.github/workflows/daily-digest.yml`:

```yaml
- cron: "0 7 * * *"   # 7 AM UTC daily
```

Use [crontab.guru](https://crontab.guru) to build your preferred schedule.

---

## 📁 Output

Digests are saved to the `digests/` folder:
- `digests/YYYY-MM-DD.md` — Human-readable Markdown
- `digests/YYYY-MM-DD.json` — Structured JSON (for building dashboards, etc.)

---

## 🛠 Local Usage

```bash
pip install anthropic

export ANTHROPIC_API_KEY="your-key-here"
export DELIVERY_MODE="file"

python scripts/ai_digest.py
```
