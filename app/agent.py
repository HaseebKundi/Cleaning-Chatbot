"""
LangGraph graph: quote_request, booking_request, faq, complaint, chitchat
routing + notification logic.

Same core engine as the original AI Customer Support Agent:
  classify -> confidence gate -> route to intent node -> respond
What changed for this domain:
  - order_status is gone; quote_request and booking_request replace it as
    multi-turn slot-filling flows (collect fields across turns, not one lookup).
  - escalate_to_human() is reframed as notify_new_lead() / notify_complaint(),
    firing on *every* quote/booking, not just complaints.
"""
import json
from typing import TypedDict

from groq import Groq
from langgraph.graph import StateGraph, END

from app.config import settings
from app.database import SessionLocal
from app.models import Lead, SupportTicket
from app import memory, rag, notify

_client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

INTENTS = ["quote_request", "booking_request", "faq", "complaint", "chitchat"]

REQUIRED_FIELDS = {
    "quote_request": ["service_type", "home_size", "zip_code"],
    "booking_request": ["name", "phone", "preferred_datetime", "zip_code"],
}
# Fields worth capturing opportunistically even when not required to complete
# the lead — e.g. a customer often volunteers their name during a quote
# request even though a quote doesn't strictly need it. We still only ever
# *ask* for the REQUIRED_FIELDS; this just stops us from throwing away
# identity info the customer already gave us unprompted.
OPTIONAL_FIELDS = ["name", "phone", "email"]

FIELD_QUESTIONS = {
    "service_type": "What kind of cleaning are you looking for — standard, deep, move-out, or recurring?",
    "home_size": "How big is the home (bedrooms/bathrooms, or square footage)?",
    "zip_code": "What's the zip code or area you're in, so I can confirm we service it?",
    "name": "Can I grab your name?",
    "phone": "What's the best phone number to reach you at?",
    "preferred_datetime": "What day/time works best for you?",
}


class AgentState(TypedDict):
    session_id: str
    message: str
    history: list[dict]
    intent: str
    confidence: float
    fields: dict
    response: str
    lead_saved: bool


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _chat(system: str, user: str, json_mode: bool = False) -> str:
    if _client is None:
        # No API key configured — fail loudly in a way that's obvious during a demo,
        # rather than silently returning garbage.
        return '{"error": "GROQ_API_KEY not set"}' if json_mode else (
            "(Demo mode: no GROQ_API_KEY configured, so the assistant can't respond yet.)"
        )
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        **kwargs,
    )
    return resp.choices[0].message.content


def classify_intent(message: str, history: list[dict]) -> tuple[str, float]:
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    system = (
        "You classify messages for a house-cleaning business's chat assistant. "
        f"Pick exactly one intent from: {', '.join(INTENTS)}.\n\n"
        "- quote_request: wants a price estimate for cleaning\n"
        "- booking_request: wants to schedule/book a cleaning\n"
        "- faq: general question (service areas, supplies, insurance, policies, pricing tiers)\n"
        "- complaint: unhappy existing customer, scheduling conflict, anything needing human judgment\n"
        "- chitchat: greetings, thanks, casual talk, questions about the conversation itself\n\n"
        'Respond ONLY as JSON: {"intent": "...", "confidence": 0.0-1.0}. No other text.'
    )
    user = f"Recent conversation:\n{history_text}\n\nLatest message: {message}"
    raw = _chat(system, user, json_mode=True)
    try:
        data = json.loads(raw)
        intent = data.get("intent", "faq")
        confidence = float(data.get("confidence", 0.5))
        if intent not in INTENTS:
            intent = "faq"
        return intent, confidence
    except (json.JSONDecodeError, ValueError):
        return "faq", 0.4


def extract_fields(lead_type: str, message: str, history: list[dict], existing: dict) -> dict:
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    # Always try to capture required fields, plus any optional identity fields
    # (name/phone/email) not already required for this lead_type — so a
    # customer volunteering their name during a quote request doesn't get lost.
    required = REQUIRED_FIELDS[lead_type]
    fields = required + [f for f in OPTIONAL_FIELDS if f not in required]
    system = (
        f"Extract these fields from the conversation if present: {', '.join(fields)}. "
        f"Already known: {json.dumps(existing)}. "
        "Only extract new information from the latest message and recent context. "
        "Only fill a field if the customer actually stated it — never guess or infer. "
        'Respond ONLY as JSON with those exact keys, using null for anything not mentioned. '
        'Example: {"service_type": "deep clean", "home_size": null, "zip_code": "33101"}'
    )
    user = f"Recent conversation:\n{history_text}\n\nLatest message: {message}"
    raw = _chat(system, user, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def generate_reply(system: str, message: str, history: list[dict]) -> str:
    history_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
    user = f"Recent conversation:\n{history_text}\n\nLatest message: {message}"
    return _chat(system, user)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def node_classify(state: AgentState) -> AgentState:
    intent, confidence = classify_intent(state["message"], state["history"])
    state["intent"] = intent
    state["confidence"] = confidence
    return state


def node_slot_filling(state: AgentState) -> AgentState:
    """Shared logic for quote_request and booking_request."""
    intent = state["intent"]
    session_id = state["session_id"]

    extracted = extract_fields(intent, state["message"], state["history"], state["fields"])
    fields = memory.update_lead_fields(session_id, extracted)
    state["fields"] = fields

    required = REQUIRED_FIELDS[intent]
    missing = [f for f in required if f not in fields]

    if missing:
        next_field = missing[0]
        business = settings.BUSINESS_NAME
        system = (
            f"You are the booking assistant for {business}, a house cleaning company. "
            "Reply warmly and briefly (1-2 sentences), acknowledge what the customer just said, "
            f"then ask this specific question naturally: '{FIELD_QUESTIONS[next_field]}' "
            "Do not ask for anything else in this turn."
        )
        state["response"] = generate_reply(system, state["message"], state["history"])
        state["lead_saved"] = False
        return state

    # All required fields present — save the lead and notify the owner.
    db = SessionLocal()
    try:
        lead = Lead(
            session_id=session_id,
            lead_type=intent,
            name=fields.get("name"),
            phone=fields.get("phone"),
            email=fields.get("email"),
            service_type=fields.get("service_type"),
            home_size=fields.get("home_size"),
            zip_code=fields.get("zip_code"),
            preferred_datetime=fields.get("preferred_datetime"),
            notes=fields.get("notes"),
            status="new",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        notify.notify_new_lead(lead)
    finally:
        db.close()

    memory.clear_lead_fields(session_id)
    kind = "quote request" if intent == "quote_request" else "booking request"
    business = settings.BUSINESS_NAME
    system = (
        f"You are the booking assistant for {business}. The customer's {kind} is now complete "
        "and has been sent to the business owner. Thank them warmly, confirm the owner will "
        "follow up shortly (usually same business day), and keep it to 1-2 sentences."
    )
    state["response"] = generate_reply(system, state["message"], state["history"])
    state["lead_saved"] = True
    return state


def node_faq(state: AgentState) -> AgentState:
    hits = rag.search_faq(state["message"], n_results=3)
    context = "\n\n".join(h["text"] for h in hits) if hits else "No matching FAQ content found."
    business = settings.BUSINESS_NAME
    system = (
        f"You are the chat assistant for {business}, a house cleaning company. "
        "Answer the customer's question using ONLY the FAQ context below. "
        "If the context doesn't cover it, say you're not sure and offer to have the "
        "owner follow up directly. Keep answers short and friendly.\n\n"
        f"FAQ CONTEXT:\n{context}"
    )
    state["response"] = generate_reply(system, state["message"], state["history"])
    return state


def node_complaint(state: AgentState) -> AgentState:
    db = SessionLocal()
    try:
        ticket = SupportTicket(
            session_id=state["session_id"],
            message=state["message"],
            status="open",
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        notify.notify_complaint(ticket)
    finally:
        db.close()

    business = settings.BUSINESS_NAME
    system = (
        f"You are the chat assistant for {business}. The customer has a complaint or issue "
        "needing a real person. Acknowledge it with genuine empathy, tell them you've flagged "
        "it for the owner to reach out directly and soon, and do NOT attempt to resolve it "
        "yourself. Keep it to 1-2 sentences."
    )
    state["response"] = generate_reply(system, state["message"], state["history"])
    return state


def node_chitchat(state: AgentState) -> AgentState:
    business = settings.BUSINESS_NAME
    system = (
        f"You are the friendly chat assistant for {business}, a house cleaning company. "
        "Respond naturally and briefly to greetings/thanks/small talk. If it fits, gently "
        "mention you can help with a free quote or booking a cleaning."
    )
    state["response"] = generate_reply(system, state["message"], state["history"])
    return state


def node_low_confidence(state: AgentState) -> AgentState:
    """Confidence-gated fallback, same principle as the original project's escalation gate."""
    state["response"] = (
        "Just to make sure I point you the right way — are you looking for a price quote, "
        "trying to book a cleaning, or do you have a question about our service?"
    )
    return state


def route_after_classify(state: AgentState) -> str:
    if state["confidence"] < settings.CONFIDENCE_THRESHOLD:
        return "low_confidence"
    return state["intent"]


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classify", node_classify)
    graph.add_node("quote_request", node_slot_filling)
    graph.add_node("booking_request", node_slot_filling)
    graph.add_node("faq", node_faq)
    graph.add_node("complaint", node_complaint)
    graph.add_node("chitchat", node_chitchat)
    graph.add_node("low_confidence", node_low_confidence)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "quote_request": "quote_request",
            "booking_request": "booking_request",
            "faq": "faq",
            "complaint": "complaint",
            "chitchat": "chitchat",
            "low_confidence": "low_confidence",
        },
    )
    for node in ["quote_request", "booking_request", "faq", "complaint", "chitchat", "low_confidence"]:
        graph.add_edge(node, END)

    return graph.compile()


_graph = build_graph()


def run_agent(session_id: str, message: str) -> dict:
    history = memory.get_history(session_id)
    fields = memory.get_lead_fields(session_id)

    state: AgentState = {
        "session_id": session_id,
        "message": message,
        "history": history,
        "intent": "",
        "confidence": 0.0,
        "fields": fields,
        "response": "",
        "lead_saved": False,
    }

    result = _graph.invoke(state)

    memory.add_message(session_id, "user", message)
    memory.add_message(session_id, "assistant", result["response"])

    return {
        "reply": result["response"],
        "intent": result["intent"] if result["confidence"] >= settings.CONFIDENCE_THRESHOLD else "clarifying",
        "confidence": result["confidence"],
    }
