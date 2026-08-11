"""
FastAPI app: /chat, /chat/stream, /leads, /health

Streaming note: the agent itself runs as one LangGraph invocation per turn
(same as the original project), so /chat/stream simulates a typed effect by
chunking the final reply — it gives the widget a natural typing indicator
without needing token-level streaming from every graph node.
"""
import asyncio
import logging

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db, run_lightweight_migrations
from app.models import Lead, SupportTicket
from app.schemas import ChatRequest, ChatResponse, LeadOut, TicketOut
from app.agent import run_agent
from app import rag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title=f"{settings.BUSINESS_NAME} — Lead & Booking Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    try:
        count = rag.load_faq_into_chroma()
        logger.info(f"Loaded {count} FAQ entries into Chroma.")
    except Exception as e:
        logger.warning(f"Could not load FAQ into Chroma on startup: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "business": settings.BUSINESS_NAME}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    result = run_agent(req.session_id, req.message)
    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        intent=result["intent"],
        confidence=result["confidence"],
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    result = run_agent(req.session_id, req.message)

    async def token_stream():
        words = result["reply"].split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield chunk
            await asyncio.sleep(0.02)

    return StreamingResponse(token_stream(), media_type="text/plain")


@app.get("/leads", response_model=list[LeadOut])
def get_leads(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Lead).order_by(Lead.created_at.desc())
    if status:
        query = query.filter(Lead.status == status)
    return query.all()


@app.get("/tickets", response_model=list[TicketOut])
def get_tickets(db: Session = Depends(get_db)):
    return db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).all()


# Serve the chat widget statically at /widget
app.mount("/widget", StaticFiles(directory="static", html=True), name="widget")
