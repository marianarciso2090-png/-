import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ResearchStatus(str, enum.Enum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    ANALYSING = "analysing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    resolved_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[ResearchStatus] = mapped_column(default=ResearchStatus.QUEUED, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence: Mapped[list["EvidenceSnapshot"]] = relationship(
        back_populates="research", cascade="all, delete-orphan", order_by="EvidenceSnapshot.captured_at"
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = (Index("ix_evidence_research_tool", "research_id", "tool_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    research_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    source_server: Mapped[str] = mapped_column(String(32))
    tool_name: Mapped[str] = mapped_column(String(64))
    request_params: Mapped[dict] = mapped_column(JSON)
    response_sha256: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    excerpt: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    research: Mapped[ResearchRun] = relationship(back_populates="evidence")

    @property
    def readable(self) -> dict:
        from app.services.evidence import readable_evidence
        return readable_evidence(self.raw_payload)


class CredentialSession(Base):
    __tablename__ = "credential_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_keys: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(index=True)
