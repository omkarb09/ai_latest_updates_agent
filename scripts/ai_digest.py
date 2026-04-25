"""
Daily AI Advancements Digest
Searches research papers, company tech blogs, and AI news using Claude + web search.
"""

import os
import json
import ast
import smtplib
import sys
import logging
import time
import html as html_lib
import traceback
import argparse
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configure logging
log_level = os.environ.get("AI_DIGEST_LOG", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

# ── Configuration ─────────────────────────────────────────────────────────────

SOURCES = [
    # Research / Academia
    "arxiv.org AI papers",
    "Carnegie Mellon University AI research",
    "Stanford AI lab research",
    "MIT CSAIL research",
    "Google DeepMind research blog",
    # Industry Tech Blogs
    "Netflix tech blog AI machine learning",
    "DoorDash engineering blog AI ML",
    "Uber engineering AI blog",
    "Meta AI research blog",
    "OpenAI research blog",
    "Anthropic research blog",
    "Hugging Face blog",
    # News
    "AI industry news breakthroughs",
]

SYSTEM_PROMPT = """You are an expert AI research analyst. Your job is to produce a 
well-structured, insightful daily digest of the most significant AI advancements.

Focus on:
1. Breakthrough research papers (especially from top universities & labs)
2. New model releases or major updates
3. Interesting engineering insights from company tech blogs (Netflix, DoorDash, Uber, Meta, etc.)
4. Industry-shaping product launches or announcements

Format your output STRICTLY as valid JSON (no markdown, no extra text) with this schema:
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

Include 8-12 highlights. Prioritize quality over quantity. Be concise but informative."""

# ── Core Agent ────────────────────────────────────────────────────────────────

def run_digest_agent() -> dict:
    # Use GROQ exclusively
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logging.error("Missing GROQ_API_KEY env var. Set it and retry.")
        sys.exit(1)

    try:
        import groq
    except Exception:
        logging.error("Groq SDK is not installed. Run 'pip install groq' and try again.")
        raise

    client = groq.Client(api_key=api_key)
    today = date.today().isoformat()

    search_targets = "\n".join(f"- {s}" for s in SOURCES)

    user_prompt = f"""Today is {today}. Search across ALL of these source categories to find 
the most important AI advancements from the past 24-48 hours:

{search_targets}

Make sure to specifically check:
- arXiv for new AI/ML papers submitted today
- Netflix Tech Blog (netflixtechblog.com)
- DoorDash Engineering Blog (doordash.engineering)
- Carnegie Mellon University AI/ML research announcements
- Hugging Face daily papers (huggingface.co/papers)
- Major AI lab blogs (DeepMind, Anthropic, OpenAI, Meta AI)

Return results as JSON only."""

    logging.info("%s Running AI digest agent...", today)
    # Prepare model selection and attempt calls with retry/backoff
    max_attempts = 3
    backoff = 1
    response_text = None
    last_exc = None

    # Determine model name (allow override via env)
    model_name = os.environ.get("MODEL_NAME") or "openai/gpt-oss-120b"

    # helper extractor for Anthropic-style responses
    def _extract_text(resp) -> str:
        try:
            raw = ""
            if hasattr(resp, "content"):
                for block in resp.content:
                    t = getattr(block, "type", None)
                    if t == "text":
                        raw += getattr(block, "text", "")
            elif hasattr(resp, "text"):
                raw = resp.text
            elif isinstance(resp, dict):
                for k in ("content", "text", "completion", "output"):
                    if k in resp and isinstance(resp[k], str):
                        raw += resp[k]
            else:
                raw = str(resp)
            return raw
        except Exception:
            logging.debug("Exception extracting text: %s", traceback.format_exc())
            return str(resp)

    for attempt in range(1, max_attempts + 1):
        try:
            # Groq-only invocation
            try:
                if hasattr(client, "chat") and hasattr(client.chat, "completions"):
                    resp = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
                        max_tokens=4000,
                    )
                    response_text = _extract_text(resp)
                elif hasattr(client, "generate"):
                    prompt = SYSTEM_PROMPT + "\n" + user_prompt
                    resp = client.generate(model=model_name, prompt=prompt, max_tokens=4000)
                    response_text = _extract_text(resp)
                else:
                    raise RuntimeError("Groq client does not expose supported methods; please install/update the groq SDK.")
            except Exception:
                raise

            # success; break retry loop
            if response_text is not None:
                break

        except Exception as e:
            last_exc = e
            logging.warning("API attempt %s failed: %s", attempt, str(e))
            if attempt < max_attempts:
                time.sleep(backoff)
                backoff *= 2

    if response_text is None:
        logging.error("Failed to call provider API after %s attempts: %s", max_attempts, last_exc)
        raise last_exc

    raw_text = str(response_text).strip()

    # Remove triple-backtick fences if present
    if raw_text.startswith("```"):
        parts = raw_text.split("```")
        # find the first fenced block that looks like JSON
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate.strip().startswith("json"):
                candidate = candidate.strip()[4:]
            raw_text = candidate

    raw_text = raw_text.strip()

    # Try to parse JSON robustly; if it fails, attempt to extract a balanced JSON object
    def _extract_json_substring(s: str) -> str | None:
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
                    return s[start:i+1]
        return None

    # Robust JSON parsing with fallbacks for slightly malformed outputs
    def _try_parse_json(s: str):
        # 1) strict JSON
        try:
            return json.loads(s)
        except Exception:
            pass

        # 2) try json5 (allows single quotes, trailing commas, unquoted keys)
        try:
            import json5

            try:
                return json5.loads(s)
            except Exception:
                pass
        except Exception:
            logging.debug("json5 not available; skip json5 fallback")

        # 3) try ast.literal_eval for Python-like dicts
        try:
            obj = ast.literal_eval(s)
            # ensure it becomes JSON-serializable dict/list
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass

        return None

    digest = _try_parse_json(raw_text)
    if digest is None:
        logging.warning("Initial JSON parse failed, attempting to extract JSON substring.")
        # Save the raw output for inspection and log a preview
        os.makedirs("digests", exist_ok=True)
        raw_path = f"digests/{today}_raw.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        logging.info("Saved raw model output to %s", raw_path)
        logging.info("Model output preview: %s", raw_text[:800].replace("\n", " "))

        candidate = _extract_json_substring(raw_text)
        if candidate:
            # save candidate substring too for debugging
            cand_path = f"digests/{today}_candidate.txt"
            with open(cand_path, "w", encoding="utf-8") as f:
                f.write(candidate)
            logging.info("Saved extracted JSON candidate to %s", cand_path)

            digest = _try_parse_json(candidate)
            if digest is None:
                logging.error("JSON parse failed after extraction using strict/json5/ast fallbacks.")
                raise ValueError(f"Parsed JSON invalid after fallbacks; raw saved to {raw_path}, candidate saved to {cand_path}")
        else:
            logging.error("Could not locate JSON substring in model output.")
            raise ValueError(f"No JSON found in model output; raw saved to {raw_path}")

    # Ensure schema defaults
    if not isinstance(digest, dict):
        raise ValueError("Parsed digest is not a JSON object")

    digest.setdefault("highlights", [])
    logging.info("%s Agent returned %d highlights.", today, len(digest.get('highlights', [])))
    return digest


# ── Formatters ────────────────────────────────────────────────────────────────

def to_html(digest: dict) -> str:
    today = digest.get("date", date.today().isoformat())
    summary = digest.get("summary", "")
    highlights = digest.get("highlights", [])

    category_colors = {
        "Research Paper": "#4f46e5",
        "Company Blog": "#0891b2",
        "Model Release": "#059669",
        "Industry News": "#d97706",
    }

    rows = ""
    for h in highlights:
        cat = h.get("category", "Other")
        color = category_colors.get(cat, "#6b7280")
        title = h.get("title", "Untitled")
        url = h.get("url")
        source = h.get("source", "")
        insight = h.get("insight", "")

        # Escape model-provided content for safe HTML embedding
        esc_title = html_lib.escape(str(title))
        esc_source = html_lib.escape(str(source))
        esc_insight = html_lib.escape(str(insight))
        esc_url = html_lib.escape(str(url), quote=True) if url else None

        title_html = f'<a href="{esc_url}" style="color:#1d4ed8;text-decoration:none;">{esc_title}</a>' if esc_url else esc_title

        rows += f"""
        <tr>
          <td style="padding:16px;border-bottom:1px solid #f0f0f0;vertical-align:top;">
            <span style="background:{color};color:#fff;font-size:11px;font-weight:600;
              padding:3px 8px;border-radius:12px;white-space:nowrap;">{cat}</span>
            <div style="font-size:13px;color:#6b7280;margin-top:6px;">{esc_source}</div>
          </td>
          <td style="padding:16px;border-bottom:1px solid #f0f0f0;">
            <div style="font-weight:600;color:#111;margin-bottom:6px;">{title_html}</div>
            <div style="font-size:14px;color:#374151;line-height:1.6;">{esc_insight}</div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:680px;margin:32px auto;background:#fff;border-radius:12px;
    box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e1b4b 0%,#312e81 100%);padding:32px;">
      <div style="font-size:12px;color:#a5b4fc;letter-spacing:2px;text-transform:uppercase;">Daily Digest</div>
      <h1 style="margin:8px 0 4px;color:#fff;font-size:26px;">AI Advancements</h1>
      <div style="color:#c7d2fe;font-size:14px;">{today}</div>
    </div>

    <!-- Summary -->
    <div style="padding:24px 32px;background:#f5f3ff;border-bottom:1px solid #ede9fe;">
      <p style="margin:0;color:#4c1d95;font-size:15px;line-height:1.7;">{summary}</p>
    </div>

    <!-- Highlights -->
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

    <!-- Footer -->
    <div style="padding:20px 32px;background:#f9fafb;border-top:1px solid #f0f0f0;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        Generated by AI Digest Agent · Powered by Claude + Web Search
      </p>
    </div>
  </div>
</body>
</html>"""


def to_markdown(digest: dict) -> str:
    today = digest.get("date", date.today().isoformat())
    summary = digest.get("summary", "")
    highlights = digest.get("highlights", [])

    lines = [
        f"# 🤖 AI Advancements Digest — {today}",
        "",
        f"> {summary}",
        "",
        "---",
        "",
    ]
    for h in highlights:
        title = h.get("title", "Untitled")
        url = h.get("url")
        cat = h.get("category", "")
        source = h.get("source", "")
        insight = h.get("insight", "")
        title_md = f"[{title}]({url})" if url else title
        lines += [
            f"### {title_md}",
            f"**{cat}** · {source}",
            "",
            insight,
            "",
        ]

    return "\n".join(lines)


def generate_sample_digest() -> dict:
    today = date.today().isoformat()
    sample = {
        "date": today,
        "summary": "Sample digest for CI dry-run: no API calls were made.",
        "highlights": [
            {
                "category": "Industry News",
                "source": "Example Blog",
                "title": "Sample AI release for dry-run",
                "url": None,
                "insight": "This is a synthetic entry used for CI validation and formatting checks."
            }
        ]
    }
    return sample


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
    msg["From"] = smtp_user
    msg["To"] = recipient

    msg.attach(MIMEText(to_markdown(digest), "plain"))
    msg.attach(MIMEText(to_html(digest), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        logging.info("Email sent to %s", recipient)
    except Exception as e:
        logging.error("Failed to send email: %s", str(e))
        raise


def save_to_file(digest: dict):
    today = digest.get("date", date.today().isoformat())
    try:
        os.makedirs("digests", exist_ok=True)

        # Save JSON
        with open(f"digests/{today}.json", "w", encoding="utf-8") as f:
            json.dump(digest, f, indent=2)

        # Save Markdown
        with open(f"digests/{today}.md", "w", encoding="utf-8") as f:
            f.write(to_markdown(digest))

        logging.info("Digest saved to digests/%s.json and digests/%s.md", today, today)
    except Exception as e:
        logging.error("Failed to save digest to file: %s", str(e))
        raise


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Digest runner")
    parser.add_argument("--dry-run", action="store_true", help="Run without calling external APIs (CI friendly)")
    args = parser.parse_args()

    try:
        if args.dry_run or os.environ.get("DRY_RUN"):
            logging.info("Running in dry-run mode; generating sample digest.")
            digest = generate_sample_digest()
        else:
            digest = run_digest_agent()

        delivery = os.environ.get("DELIVERY_MODE", "file")  # "email" or "file"

        if delivery == "email":
            send_email(digest)
        else:
            save_to_file(digest)
            print("\n" + to_markdown(digest))
    except Exception as e:
        logging.exception("Digest run failed: %s", str(e))
        sys.exit(1)
