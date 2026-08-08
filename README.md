# AI Lead & Booking Assistant — House Cleaning Businesses

A website chatbot for local house-cleaning companies. Its job isn't answering
support tickets — it's capturing quote requests and booking inquiries so the
business never loses a lead, especially outside business hours.

Built on the same core engine as the original AI Customer Support Agent:
**LangGraph + FastAPI + SQLAlchemy + Chroma/FastEmbed RAG + Groq.**

---

## 1. What's different from the original Support Agent project

| Original | This project |
|---|---|
| `Order` model | `Lead` model |
| `order_status` intent | `quote_request` + `booking_request` (multi-turn slot filling) |
| Escalation = human support | Escalation = **owner notification** (SMS/Slack/email) on every lead |
| `/tickets` endpoint | `/leads` + `/tickets` endpoints |
| — | `app/notify.py` (new file) |

`faq`, `complaint`, and `chitchat` intents work the same way as before —
only the domain content changed.

---

## 2. Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_key_here

BUSINESS_NAME=Sparkle Clean Co.
ALLOWED_ORIGINS=*

# Optional — leave blank to run in demo/log-only notification mode
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
OWNER_PHONE_NUMBER=
SLACK_WEBHOOK_URL=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
OWNER_EMAIL=
```

Build the database and FAQ index:

```bash
python seed_data.py
```

Run the server:

```bash
uvicorn app.main:app --reload --port 8000
```

Open the widget at `http://localhost:8000/widget/` and try:
- "I need a quote for a 3 bedroom deep clean"
- "Can I book a cleaning next Tuesday?"
- "Are you insured?"
- "This is my third bad experience, I want to cancel"

Check captured leads:

```bash
curl http://localhost:8000/leads
```

---

## 3. Customizing for a new client

1. **`data/faq.json`** — replace with the client's real policies (don't guess
   pricing or cancellation terms — ask the client directly).
2. **`.env`** — set `BUSINESS_NAME`, notification credentials, and
   `ALLOWED_ORIGINS` to the client's actual domain.
3. **`static/index.html`** — swap colors (`--brand` / `--brand-dark`), the
   header title, and the greeting message to match their branding.
4. Run `python seed_data.py` again after editing `faq.json`.

No agent code changes are needed for a standard client — this is the "no
booking-tool integration" path from the spec (fastest to deliver, still
solves the core problem). If a client uses Housecall Pro, Jobber, or Google
Calendar, that's an additive integration in `node_slot_filling` — not a
rewrite.

---

## 4. Deploying (Render)

Same process as the original project:

1. Push this project to a GitHub repo (manual upload is fine).
2. Create a new Web Service on Render, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add all `.env` variables under Render's Environment settings.
6. Swap `DATABASE_URL` to a Postgres connection string (Render's free
   Postgres works fine) — **don't ship on SQLite**, a redeploy wipes it.

Then update `API_BASE` in `static/index.html` to the deployed Render URL,
and embed the widget on the client's site with an `<iframe>` or by copying
the widget's HTML/CSS/JS into their page.

---

## 5. Before handing this to a real client

- [ ] Lock `ALLOWED_ORIGINS` to their actual domain (not `*`)
- [ ] Add an API key or rate limit on `/chat` (not yet included — see note below)
- [ ] Switch to PostgreSQL
- [ ] Configure at least one real notification channel — this is not optional,
      a missed lead is the exact problem this project solves
- [ ] Consider a paid Render tier to avoid cold-start delays on a live client site

**Note on rate limiting:** this build ships without one so it's easy to demo
immediately. Before a real client, add `slowapi` (a couple lines around the
`/chat` route) or put the whole app behind Cloudflare's free tier.

---

## 6. File structure

```
app/main.py          FastAPI app: /chat, /chat/stream, /leads, /tickets, /health
app/agent.py          LangGraph graph: quote_request, booking_request, faq, complaint, chitchat
app/memory.py         Per-session conversation history + in-progress lead fields
app/rag.py            Chroma vector store + FAQ similarity search
app/models.py         Lead model, SupportTicket
app/database.py       SQLAlchemy engine/session
app/schemas.py         Request/response models
app/notify.py          Sends SMS/email/Slack alert on new lead
app/config.py          Env-based settings
data/faq.json           Cleaning-business FAQ content (edit per client)
static/index.html       Floating chat widget
seed_data.py            Creates tables + loads FAQ into Chroma
```
