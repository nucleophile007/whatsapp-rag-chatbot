"""
SQLModel table mappings (phased migration, side-by-side with SQLAlchemy models).

These models map to existing tables and are intentionally introduced without
changing current runtime query paths yet.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlmodel import SQLModel, Field
from sqlalchemy import Boolean, Column, Integer, String, Text, TIMESTAMP, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.sql import func


class KnowledgeBaseSQLModel(SQLModel, table=True):
    __tablename__ = "knowledge_bases"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    name: str = Field(sa_column=Column(String(255), unique=True, nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class KnowledgeBaseRetrievalProfileSQLModel(SQLModel, table=True):
    __tablename__ = "knowledge_base_retrieval_profiles"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    knowledge_base_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), nullable=False, unique=True),
    )
    final_context_k: Optional[int] = Field(default=None, sa_column=Column(Integer))
    retrieval_candidates: Optional[int] = Field(default=None, sa_column=Column(Integer))
    grounding_threshold: Optional[float] = Field(default=None, sa_column=Column(Float))
    require_citations: Optional[bool] = Field(default=None, sa_column=Column(Boolean))
    min_context_chars: Optional[int] = Field(default=None, sa_column=Column(Integer))
    query_variants_limit: Optional[int] = Field(default=None, sa_column=Column(Integer))
    clarification_enabled: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    clarification_threshold: Optional[float] = Field(default=None, sa_column=Column(Float))
    chunk_size: Optional[int] = Field(default=None, sa_column=Column(Integer))
    chunk_overlap: Optional[int] = Field(default=None, sa_column=Column(Integer))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class WorkspaceSQLModel(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    name: str = Field(sa_column=Column(String(255), nullable=False))
    knowledge_base_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True)),
    )
    system_prompt: Optional[str] = Field(default=None, sa_column=Column(Text))
    user_prompt_template: Optional[str] = Field(default=None, sa_column=Column(Text))
    low_quality_clarification_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    contact_filter_mode: str = Field(default="all", sa_column=Column(String(20), nullable=False, default="all"))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class FlowSQLModel(SQLModel, table=True):
    __tablename__ = "flows"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    user_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True)))
    workspace_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True)))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))

    definition: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    trigger_type: str = Field(sa_column=Column(String(50), nullable=False))
    trigger_config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))

    is_enabled: bool = Field(default=True, sa_column=Column(Boolean, default=True))
    version: int = Field(default=1, sa_column=Column(Integer, default=1))

    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class WhatsAppGroupSQLModel(SQLModel, table=True):
    __tablename__ = "whatsapp_groups"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    chat_id: str = Field(sa_column=Column(String(255), unique=True, nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    member_count: int = Field(default=0, sa_column=Column(Integer, default=0))
    avatar_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_enabled: bool = Field(default=False, sa_column=Column(Boolean, default=False))
    synced_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    last_message_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class WhatsAppContactSQLModel(SQLModel, table=True):
    __tablename__ = "whatsapp_contacts"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    chat_id: str = Field(sa_column=Column(String(255), unique=True, nullable=False))
    display_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    phone_number: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    waha_contact_id: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    lid: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    phone_jid: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    source: str = Field(default="webhook", sa_column=Column(String(30), nullable=False, default="webhook"))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    last_seen_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )


class WorkspaceGroupSQLModel(SQLModel, table=True):
    __tablename__ = "workspace_groups"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    workspace_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    group_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class WorkspaceContactSQLModel(SQLModel, table=True):
    __tablename__ = "workspace_contacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "contact_id", name="uq_workspace_contacts_workspace_contact"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    workspace_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    contact_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class WorkspaceFlowSQLModel(SQLModel, table=True):
    __tablename__ = "workspace_flows"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    workspace_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    flow_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class FlowGroupSQLModel(SQLModel, table=True):
    __tablename__ = "flow_groups"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    flow_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    group_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class FlowExecutionSQLModel(SQLModel, table=True):
    __tablename__ = "flow_executions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    flow_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    group_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True)))
    trigger_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    status: str = Field(sa_column=Column(String(20), nullable=False))
    nodes_executed: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_node_id: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    started_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    completed_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP))
    duration_ms: Optional[int] = Field(default=None, sa_column=Column(Integer))
    context_data: Optional[Any] = Field(default=None, sa_column=Column(JSONB))


class RAGEvalScorecardSQLModel(SQLModel, table=True):
    __tablename__ = "rag_eval_scorecards"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    collection_name: str = Field(sa_column=Column(String(255), nullable=False))
    knowledge_base_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(PGUUID(as_uuid=True)))
    total_cases: int = Field(sa_column=Column(Integer, nullable=False))
    fallback_rate: float = Field(sa_column=Column(Float, nullable=False))
    citation_ok_rate: float = Field(sa_column=Column(Float, nullable=False))
    grounding_pass_rate: float = Field(sa_column=Column(Float, nullable=False))
    expectation_hit_rate: float = Field(sa_column=Column(Float, nullable=False))
    avg_latency_ms: float = Field(sa_column=Column(Float, nullable=False))
    rag_options: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class RAGEvalCaseResultSQLModel(SQLModel, table=True):
    __tablename__ = "rag_eval_case_results"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    scorecard_id: uuid.UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    case_index: int = Field(sa_column=Column(Integer, nullable=False))
    question: str = Field(sa_column=Column(Text, nullable=False))
    answer: str = Field(sa_column=Column(Text, nullable=False))
    expected_contains: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    expectation_hit: bool = Field(sa_column=Column(Boolean, nullable=False))
    fallback_used: bool = Field(sa_column=Column(Boolean, nullable=False))
    citation_ok: bool = Field(sa_column=Column(Boolean, nullable=False))
    grounding: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    latency_ms: float = Field(sa_column=Column(Float, nullable=False))
    retrieved_chunks: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))


class ConversationLongTermMemorySQLModel(SQLModel, table=True):
    __tablename__ = "conversation_long_term_memories"
    __table_args__ = (
        UniqueConstraint("client_id", "memory_key", name="uq_conversation_ltm_client_key"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    )
    client_id: str = Field(sa_column=Column(String(255), nullable=False))
    memory_key: str = Field(sa_column=Column(String(160), nullable=False))
    memory_text: str = Field(sa_column=Column(Text, nullable=False))
    memory_category: str = Field(default="general", sa_column=Column(String(50), nullable=False, default="general"))
    confidence: float = Field(default=0.0, sa_column=Column(Float, nullable=False, default=0.0))
    source_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    memory_metadata: Optional[Any] = Field(default=None, sa_column=Column("metadata", JSONB))
    hit_count: int = Field(default=1, sa_column=Column(Integer, nullable=False, default=1))
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    last_seen_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP))
    created_at: Optional[Any] = Field(default=None, sa_column=Column(TIMESTAMP, server_default=func.current_timestamp()))
    updated_at: Optional[Any] = Field(
        default=None,
        sa_column=Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()),
    )
