"""SQLAlchemy ORM model for security scan findings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SecurityScan(Base):
    """A security scan run against a repository.

    Attributes:
        id: UUID primary key.
        repo_id: FK to repositories.id.
        scan_types: List of scan module slugs run (secrets, sast, iac).
        status: queued | running | complete | failed.
        progress: 0-100 integer percentage.
        current_stage: Human-readable stage label.
        total_findings: Count of findings discovered.
        critical_count: Count of CRITICAL severity findings.
        high_count: Count of HIGH severity findings.
        medium_count: Count of MEDIUM severity findings.
        low_count: Count of LOW severity findings.
        info_count: Count of INFO severity findings.
        error_message: Error detail if status is failed.
        started_at: When the scan began execution.
        finished_at: When the scan completed.
        created_at: Record creation timestamp.
        updated_at: Auto-updated modification timestamp.
    """

    __tablename__ = "security_scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scan_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    info_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    findings: Mapped[list["SecurityFinding"]] = relationship(
        "SecurityFinding", back_populates="scan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_security_scans_repo_status", "repo_id", "status"),
    )


class SecurityFinding(Base):
    """A single security finding from a scan.

    Attributes:
        id: UUID primary key.
        scan_id: FK to security_scans.id.
        repo_id: Denormalized FK for fast repo-level queries.
        scanner: Source module (secrets | sast | iac).
        rule_id: Rule identifier from the scanner.
        title: Short descriptive title.
        description: Full finding description.
        severity: critical | high | medium | low | info.
        cvss_score: Numeric CVSS score (0.0-10.0).
        file_path: Relative path of the affected file.
        start_line: First affected line number.
        end_line: Last affected line number.
        snippet: Vulnerable code snippet.
        category: Semantic category (injection, xss, secret, iac, …).
        language: Programming language of affected file.
        fingerprint: SHA-256 dedup key for this finding.
        remediation: AI-generated fix suggestion (JSON).
        is_false_positive: Manually marked as false positive.
        suppressed: Suppressed by an allowlist rule.
        extra: Additional scanner metadata (JSONB).
        created_at: Record creation timestamp.
    """

    __tablename__ = "security_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("security_scans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scanner: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    cvss_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="generic")
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    remediation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_false_positive: Mapped[bool] = mapped_column(nullable=False, default=False)
    suppressed: Mapped[bool] = mapped_column(nullable=False, default=False)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped["SecurityScan"] = relationship("SecurityScan", back_populates="findings")

    __table_args__ = (
        UniqueConstraint("scan_id", "fingerprint", name="uq_finding_scan_fingerprint"),
        Index("ix_security_findings_repo_severity", "repo_id", "severity"),
        Index("ix_security_findings_scanner", "scan_id", "scanner"),
        Index("ix_security_findings_file", "scan_id", "file_path"),
    )
