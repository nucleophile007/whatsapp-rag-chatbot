"""
Database models using SQLAlchemy ORM
"""

from sqlalchemy import (
    Column, String, Integer, Boolean, Text, TIMESTAMP, 
    ForeignKey, ARRAY, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    flows = relationship("Flow", back_populates="user", cascade="all, delete-orphan")


class WhatsAppGroup(Base):
    __tablename__ = "whatsapp_groups"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    member_count = Column(Integer, default=0)
    avatar_url = Column(Text)
    is_enabled = Column(Boolean, default=False)
    synced_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    last_message_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    flow_groups = relationship("FlowGroup", back_populates="group", cascade="all, delete-orphan")
    workspace_groups = relationship("WorkspaceGroup", back_populates="group", cascade="all, delete-orphan")
    executions = relationship("FlowExecution", back_populates="group")
    
    # Indexes
    __table_args__ = (
        Index('idx_whatsapp_groups_enabled', 'is_enabled'),
        Index('idx_whatsapp_groups_chat_id', 'chat_id'),
    )


class KnowledgeBase(Base):
    """Represents a Qdrant collection of indexed documents"""
    __tablename__ = "knowledge_bases"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False) # Maps to Qdrant collection name
    description = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class Workspace(Base):
    """Unified configuration for prompts and Knowledge Base assignment"""
    __tablename__ = "workspaces"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    knowledge_base_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_bases.id', ondelete='SET NULL'))
    
    system_prompt = Column(Text)
    user_prompt_template = Column(Text)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    knowledge_base = relationship("KnowledgeBase")
    workspace_groups = relationship("WorkspaceGroup", back_populates="workspace", cascade="all, delete-orphan")
    flows = relationship("Flow", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceGroup(Base):
    """Mapping between Workspaces and WhatsApp Groups (Many-to-Many)"""
    __tablename__ = "workspace_groups"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='CASCADE'))
    group_id = Column(UUID(as_uuid=True), ForeignKey('whatsapp_groups.id', ondelete='CASCADE'))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    
    # Relationships
    workspace = relationship("Workspace", back_populates="workspace_groups")
    group = relationship("WhatsAppGroup", back_populates="workspace_groups")
    
    __table_args__ = (
        UniqueConstraint('workspace_id', 'group_id', name='uq_workspace_group'),
        Index('idx_workspace_groups_workspace_id', 'workspace_id'),
        Index('idx_workspace_groups_group_id', 'group_id'),
    )


class Flow(Base):
    __tablename__ = "flows"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    workspace_id = Column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='CASCADE'))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Flow definition stored as JSON
    definition = Column(JSONB, nullable=False)
    
    # Trigger configuration
    trigger_type = Column(String(50), nullable=False)
    trigger_config = Column(JSONB, nullable=False)
    
    # Status
    is_enabled = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    
    # Metadata
    tags = Column(ARRAY(Text))
    category = Column(String(50))
    
    # Timestamps
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    last_executed_at = Column(TIMESTAMP)
    
    # Relationships
    user = relationship("User", back_populates="flows")
    workspace = relationship("Workspace", back_populates="flows")
    flow_groups = relationship("FlowGroup", back_populates="flow", cascade="all, delete-orphan")
    executions = relationship("FlowExecution", back_populates="flow", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_flows_user_id', 'user_id'),
        Index('idx_flows_enabled', 'is_enabled'),
        Index('idx_flows_trigger_type', 'trigger_type'),
    )


class FlowGroup(Base):
    __tablename__ = "flow_groups"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id = Column(UUID(as_uuid=True), ForeignKey('flows.id', ondelete='CASCADE'))
    group_id = Column(UUID(as_uuid=True), ForeignKey('whatsapp_groups.id', ondelete='CASCADE'))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    
    # Relationships
    flow = relationship("Flow", back_populates="flow_groups")
    group = relationship("WhatsAppGroup", back_populates="flow_groups")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('flow_id', 'group_id', name='uq_flow_group'),
        Index('idx_flow_groups_flow_id', 'flow_id'),
        Index('idx_flow_groups_group_id', 'group_id'),
    )


class FlowExecution(Base):
    __tablename__ = "flow_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id = Column(UUID(as_uuid=True), ForeignKey('flows.id', ondelete='CASCADE'))
    group_id = Column(UUID(as_uuid=True), ForeignKey('whatsapp_groups.id', ondelete='SET NULL'))
    
    # Trigger data
    trigger_data = Column(JSONB, nullable=False)
    
    # Execution details
    status = Column(String(20), nullable=False)  # 'running', 'completed', 'failed'
    nodes_executed = Column(JSONB)
    
    # Error handling
    error_message = Column(Text)
    error_node_id = Column(String(50))
    
    # Performance
    started_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    completed_at = Column(TIMESTAMP)
    duration_ms = Column(Integer)
    
    # Context
    context_data = Column(JSONB)
    
    # Relationships
    flow = relationship("Flow", back_populates="executions")
    group = relationship("WhatsAppGroup", back_populates="executions")
    
    # Indexes
    __table_args__ = (
        Index('idx_flow_executions_flow_id', 'flow_id'),
        Index('idx_flow_executions_status', 'status'),
        Index('idx_flow_executions_started_at', 'started_at'),
    )


class NodeType(Base):
    __tablename__ = "node_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type_key = Column(String(50), unique=True, nullable=False)
    category = Column(String(50), nullable=False)  # 'trigger', 'condition', 'action'
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50))
    
    # Configuration schema (JSON Schema)
    config_schema = Column(JSONB, nullable=False)
    
    # UI metadata
    ui_config = Column(JSONB)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
