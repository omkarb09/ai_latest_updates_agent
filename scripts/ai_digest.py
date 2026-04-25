"""
Daily AI Advancements Digest
Searches research papers, company tech blogs, and AI news using Tavily + Groq.
"""

import os
import json
import ast
import smtplib
import sys
import logging
import time
import re
import html as html_lib
import traceback
import argparse
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configure logging
log_level = os.environ.get("AI_DIGEST_LOG", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s"
)

# ── Configuration ─────────────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "arXiv AI machine learning papers today 2026",
    "Netflix tech blog AI machine learning 2026",
    "DoorDash engineering blog AI ML 2026",
    "Carnegie Mellon University AI research 2026",
    "Google DeepMind research announcement 2026",
    "Hugging Face new model release 2026",
    "OpenAI research blog 2026",
    "Anthropic research blog 2026",
    "Meta AI research blog 2026",
    "Stanford AI lab research 2026",
    "MIT CSAIL AI research 2026",
    "Uber engineering AI blog 2026",
    "AI industry news breakthroughs today 2026",
]

SYSTEM_PROMPT = """You are an expert AI research analyst. Your job is to produce a
well-structured, insightful daily digest of the most significant AI advancements
based on the web search results provided to you.

Focus on:
1. Breakthrough research papers (especially from top universities & labs)
2. New model releases or major updates
3. Interesting engineering insights from company tech blogs (Netflix, DoorDash, Uber, Meta, etc.)
4. Industry-shaping product launches or announcements

Format your output STRICTLY as valid JSON (no markdown fences, no extra text) with this schema:
{
  "date": "YYYY-MM-DD",
  "summary": "2-3 sentence high-level overview of the day in AI",
  "highlights": [
    {
      "category": "Research Paper | Company Blog | Model Release | Industry News",
      "source": "Source name (e.g. Netflix Tech Blog, arXiv, CMU)",
      "title": "Title of the paper/post/announcement",
      "url": "URL if available, else null",
      "insight": "2-4 sentence explanation of why this matters"
    }
  ]
}

Include 8-12 highlights. Prioritize quality over quantity. Be concise but informative.
IMPORTANT: Your entire response must be a single valid JSON object. No prose before or after."""

# ── Web Search via Tavily ─────────────────────────────────────────────────────

def fetch_search_context() -> str:
    """Run all search queries via Tavily and return concatenated results."""
    try:
        from tavily import TavilyClient
    except ImportError:
        logging.error("tavily-python is not installed. Run 'pip install tavily-python'.")
        raise

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logging.error("Missing TAVILY_API_KEY env var.")
        sys.exit(1)

    tavily = TavilyClient(api_key=api_key)
    results = []

    for query in SEARCH_QUERIES:
        try:
            logging.info("Searching: %s", query)
            resp = tavily.search(query=query, max_results=3, search_depth="basic")
            for r in resp.get("results", []):
                title = r.get("title", "").strip()
                url = r.get("url", "").strip()
                content = r.get("content", "").strip()[:400]
                results.append(f"- [{title}]({url}): {content}")
        except Exception as e:
            logging.warning("Tavily search failed for '%s': %s", query, e)
        time.sleep(0.2)  # be polite to the API

    logging.info("Collected %d search results total.", len(results))
    return "\n".join(results)


# ── Core Agent ────────────────────────────────────────────────────────────────

def run_digest_agent() -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logging.error("Missing GROQ_API_KEY env var.")
        sys.exit(1)

    try:
        import groq
    except ImportError:
        logging.error("groq SDK not installed. Run 'pip install groq'.")
        raise

    client = groq.Client(api_key=api_key)
    today = date.today().isoformat()
    model_name = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")

    # Step 1: Fetch real web search results via Tavily
    logging.info("%s Fetching web search results via Tavily...", today)
    search_context = fetch_search_context()

    # Step 2: Ask Groq to summarize into structured JSON
    user_prompt = f"""Today is {today}. Below are fresh web search results gathered from AI research
and engineering sources including arXiv, Netflix Tech Blog, DoorDash Engineering,
Carnegie Mellon University, DeepMind, Hugging Face, OpenAI, Anthropic, Meta AI,
Stanford, MIT, and Uber Engineering:

{search_context}

Based ONLY on these search results, produce the daily AI digest JSON.
Return a single valid JSON object only — no markdown, no explanation."""

    logging.info("Calling Groq model: %s", model_name)

    max_attempts = 3
    backoff = 1
    response_text = None
    last_exc = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4000,
            )
            response_text = resp.choices[0].message.content
            if response_text:
                break
        except Exception as e:
            last_exc = e
            logging.warning("Groq attempt %d failed: %s", attempt, e)
            if attempt < max_attempts:
                time.sleep(backoff)
                backoff *= 2

    if not response_text:
        logging.error("All Groq attempts failed: %s", last_exc)
        raise last_exc

    return parse_json_response(response_text, today)


# ── JSON Parsing ──────────────────────────────────────────────────────────────

def clean_json_string(s: str) -> str:
    """Normalize common LLM JSON quirks."""
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u201C', '"').replace('\u201D', '"')
    s = s.replace('\u202f', ' ').replace('\u00a0', ' ')
    s = s.replace('\u2013', '-').replace('\u2014', '-')
    s = re.sub(r",\s*(\}|\])", r"\1", s)  # trailing commas
    return s.strip()


def try_parse_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        import json5
        return json5.loads(s)
    except Exception:
        pass
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, (dict, list)):
            return obj
    except Exception:
        pass
    return None


def extract_json_substring(s: str) -> str | None:
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def parse_json_response(raw: str, today: str) -> dict:
    # Strip markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate.strip().startswith("json"):
                candidate = candidate.strip()[4:]
            raw = candidate.strip()

    # Try direct parse
    digest = try_parse_json(raw)
    if digest:
        digest.setdefault("highlights", [])
        logging.info("JSON parsed successfully. %d highlights.", len(digest["highlights"]))
        return digest

    # Try substring extraction
    logging.warning("Direct JSON parse failed, trying substring extraction.")
    os.makedirs("digests", exist_ok=True)

    raw_path = f"digests/{today}_raw.txt"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw)
    logging.info("Raw output saved to %s", raw_path)

    candidate = extract_json_substring(raw)
    if candidate:
        digest = try_parse_json(candidate) or try_parse_json(clean_json_string(candidate))
        if digest:
            digest.setdefault("highlights", [])
            logging.info("JSON extracted from substring. %d highlights.", len(digest["highlights"]))
            return digest

    logging.error("All JSON parse attempts failed. Raw output saved to %s", raw_path)
    raise ValueError(f"Could not parse JSON from model output. Raw saved to {raw_path}")


# ── Formatters ────────────────────────────────────────────────────────────────

def to_html(digest: dict) -> str:
    today = digest.get("date", date.today().isoformat())
    summary = html_lib.escape(str(digest.get("summary", "")))
    highlights = digest.get("highlights", [])

    category_colors = {
        "Research Paper": "#4f46e5",
        "Company Blog":   "#0891b2",
        "Model Release":  "#059669",
        "Industry News":  "#d97706",
    }

    rows = ""
    for h in highlights:
        cat = h.get("category", "Other")
        color = category_colors.get(cat, "#6b7280")
        title   = html_lib.escape(str(h.get("title", "Untitled")))
        source  = html_lib.escape(str(h.get("source", "")))
        insight = html_lib.escape(str(h.get("insight", "")))
        url     = h.get("url")
        esc_url = html_lib.escape(str(url), quote=True) if url else None
        title_html = f'<a href="{esc_url}" style="color:#1d4ed8;text-decoration:none;">{title}</a>' if esc_url else title

        rows += f"""
        <tr>
          <td style="padding:16px;border-bottom:1px solid #f0f0f0;vertical-align:top;">
            <span style="background:{color};color:#fff;font-size:11px;font-weight:600;
              padding:3px 8px;border-radius:12px;white-space:nowrap;">{cat}</span>
            <div style="font-size:13px;color:#6b7280;margin-top:6px;">{source}</div>
          </td>
          <td style="padding:16px;border-bottom:1px solid #f0f0f0;">
            <div style="font-weight:600;color:#111;margin-bottom:6px;">{title_html}</div>
            <div style="font-size:14px;color:#374151;line-height:1.6;">{insight}</div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:680px;margin:32px auto;background:#fff;border-radius:12px;
    box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;">
    <div style="background:linear-gradient(135deg,#1e1b4b 0%,#312e81 100%);padding:32px;">
      <div style="font-size:12px;color:#a5b4fc;letter-spacing:2px;text-transform:uppercase;">Daily Digest</div>
      <h1 style="margin:8px 0 4px;color:#fff;font-size:26px;">AI Advancements</h1>
      <div style="color:#c7d2fe;font-size:14px;">{today}</div>
    </div>
    <div style="padding:24px 32px;background:#f5f3ff;border-bottom:1px solid #ede9fe;">
      <p style="margin:0;color:#4c1d95;font-size:15px;line-height:1.7;">{summary}</p>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f9fafb;">
          <th style="padding:12px 16px;text-align:left;font-size:12px;color:#6b7280;
            text-transform:uppercase;letter-spacing:1px;width:160px;">Category</th>
          <th style="padding:12px 16px;text-align:left;font-size:12px;color:#6b7280;
            text-transform:uppercase;letter-spacing:1px;">Highlight</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="padding:20px 32px;background:#f9fafb;border-top:1px solid #f0f0f0;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        Generated by AI Digest Agent · Powered by Tavily + Groq
      </p>
    </div>
  </div>
</body>
</html>"""


def to_markdown(digest: dict) -> str:
    today   = digest.get("date", date.today().isoformat())
    summary = digest.get("summary", "")
    highlights = digest.get("highlights", [])

    lines = [
        f"# 🤖 AI Advancements Digest — {today}", "",
        f"> {summary}", "", "---", "",
    ]
    for h in highlights:
        title  = h.get("title", "Untitled")
        url    = h.get("url")
        cat    = h.get("category", "")
        source = h.get("source", "")
        insight = h.get("insight", "")
        title_md = f"[{title}]({url})" if url else title
        lines += [f"### {title_md}", f"**{cat}** · {source}", "", insight, ""]

    return "\n".join(lines)


def generate_sample_digest() -> dict:
    return {
        "date": date.today().isoformat(),
        "summary": "Sample digest for CI dry-run: no API calls were made.",
        "highlights": [{
            "category": "Industry News",
            "source": "Example Blog",
            "title": "Sample AI release for dry-run",
            "url": None,
            "insight": "This is a synthetic entry used for CI validation and formatting checks."
        }]
    }


# ── Delivery ──────────────────────────────────────────────────────────────────

def send_email(digest: dict):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    recipient = os.environ.get("RECIPIENT_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        logging.error("SMTP_USER and SMTP_PASS must be set for email delivery.")
        raise EnvironmentError("Missing SMTP credentials")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🤖 AI Digest — {digest.get('date', date.today())}"
    msg["From"]    = smtp_user
    msg["To"]      = recipient
    msg.attach(MIMEText(to_markdown(digest), "plain"))
    msg.attach(MIMEText(to_html(digest), "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipient, msg.as_string())
    logging.info("Email sent to %s", recipient)


def save_to_file(digest: dict):
    today = digest.get("date", date.today().isoformat())
    os.makedirs("digests", exist_ok=True)
    with open(f"digests/{today}.json", "w", encoding="utf-8") as f:
        json.dump(digest, f, indent=2)
    with open(f"digests/{today}.md", "w", encoding="utf-8") as f:
        f.write(to_markdown(digest))
    logging.info("Digest saved to digests/%s.json and digests/%s.md", today, today)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Digest runner")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls (CI friendly)")
    args = parser.parse_args()

    try:
        if args.dry_run or os.environ.get("DRY_RUN"):
            logging.info("Dry-run mode: generating sample digest.")
            digest = generate_sample_digest()
        else:
            digest = run_digest_agent()

        delivery = os.environ.get("DELIVERY_MODE", "file")
        if delivery == "email":
            send_email(digest)
        else:
            save_to_file(digest)
            print("\n" + to_markdown(digest))

    except Exception as e:
        logging.exception("Digest run failed: %s", e)
        sys.exit(1)
