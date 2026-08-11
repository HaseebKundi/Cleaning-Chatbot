"""
Lead model replaces the original project's Order model — this table is the
thing that actually generates revenue for the client, so keep it easy to read.
SupportTicket is kept unchanged for genuine complaints.
"""
import datetime
import uuid

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    session_id: Mapped[str] = mapped_column(String, index=True)

    name: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    lead_type: Mapped[str] = mapped_column(String)  # "quote_request" | "booking_request"
    service_type: Mapped[str | None] = mapped_column(String, nullable=True)
    home_size: Mapped[str | None] = mapped_column(String, nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_datetime: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String, default="new")  # new | contacted | booked


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    session_id: Mapped[str] = mapped_column(String, index=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="open")  # open | resolved
