-- WhatsApp Flow Builder Database Schema
-- PostgreSQL 14+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table (for future multi-user support)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- WhatsApp groups synced from WAHA
CREATE TABLE whatsapp_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id VARCHAR(255) UNIQUE NOT NULL,  -- e.g., "120363402503743273@g.us"
    name VARCHAR(255) NOT NULL,
    description TEXT,
    member_count INTEGER DEFAULT 0,
    avatar_url TEXT,
    is_enabled BOOLEAN DEFAULT false,  -- Whether bot is active in this group
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge Bases (Qdrant collections)
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Client API keys for public chat endpoint
CREATE TABLE client_api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(120) UNIQUE NOT NULL,
    description TEXT,
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    key_prefix VARCHAR(24) NOT NULL,
    allow_all_collections BOOLEAN DEFAULT false,
    allowed_collections JSONB DEFAULT '[]'::jsonb NOT NULL,
    default_collection_name VARCHAR(255),
    daily_limit_per_device INTEGER,
    default_system_prompt TEXT,
    default_user_prompt_template TEXT,
    default_prompt_technique VARCHAR(40) DEFAULT 'balanced',
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workspaces (Unified configuration)
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    system_prompt TEXT,
    user_prompt_template TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workspace-Group associations (many-to-many)
CREATE TABLE workspace_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    group_id UUID REFERENCES whatsapp_groups(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(workspace_id, group_id)
);

CREATE INDEX idx_workspace_groups_workspace_id ON workspace_groups(workspace_id);
CREATE INDEX idx_workspace_groups_group_id ON workspace_groups(group_id);
CREATE INDEX idx_client_api_keys_active ON client_api_keys(is_active);
CREATE INDEX idx_client_api_keys_name ON client_api_keys(name);

-- Add update trigger for new tables
CREATE TRIGGER update_knowledge_bases_updated_at BEFORE UPDATE ON knowledge_bases
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workspaces_updated_at BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Flows (automation workflows) - Keeping for legacy support
CREATE TABLE flows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Flow definition stored as JSON
    definition JSONB NOT NULL,
    
    -- Trigger configuration
    trigger_type VARCHAR(50) NOT NULL,  -- 'whatsapp_message', 'whatsapp_mention', 'schedule'
    trigger_config JSONB NOT NULL,
    
    -- Status
    is_enabled BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,
    
    -- Metadata
    tags TEXT[],
    category VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed_at TIMESTAMP
);

-- Workspace-Flow associations (many-to-many)
CREATE TABLE workspace_flows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    flow_id UUID REFERENCES flows(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(workspace_id, flow_id)
);

-- Flow-Group associations (many-to-many)
CREATE TABLE flow_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flow_id UUID REFERENCES flows(id) ON DELETE CASCADE,
    group_id UUID REFERENCES whatsapp_groups(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(flow_id, group_id)
);

-- Flow executions (logs)
CREATE TABLE flow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flow_id UUID REFERENCES flows(id) ON DELETE CASCADE,
    group_id UUID REFERENCES whatsapp_groups(id) ON DELETE SET NULL,
    
    -- Trigger data
    trigger_data JSONB NOT NULL,
    
    -- Execution details
    status VARCHAR(20) NOT NULL,  -- 'running', 'completed', 'failed'
    nodes_executed JSONB,  -- Array of executed nodes with results
    
    -- Error handling
    error_message TEXT,
    error_node_id VARCHAR(50),
    
    -- Performance
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    
    -- Context
    context_data JSONB
);

-- Node type registry (for UI and validation)
CREATE TABLE node_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type_key VARCHAR(50) UNIQUE NOT NULL,  -- e.g., 'rag_query', 'send_message'
    category VARCHAR(50) NOT NULL,  -- 'trigger', 'condition', 'action'
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50),  -- Icon name for UI
    
    -- Configuration schema (JSON Schema)
    config_schema JSONB NOT NULL,
    
    -- UI metadata
    ui_config JSONB,
    
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_flows_user_id ON flows(user_id);
CREATE INDEX idx_flows_enabled ON flows(is_enabled);
CREATE INDEX idx_flows_trigger_type ON flows(trigger_type);
CREATE INDEX idx_workspace_flows_workspace_id ON workspace_flows(workspace_id);
CREATE INDEX idx_workspace_flows_flow_id ON workspace_flows(flow_id);

CREATE INDEX idx_whatsapp_groups_enabled ON whatsapp_groups(is_enabled);
CREATE INDEX idx_whatsapp_groups_chat_id ON whatsapp_groups(chat_id);

CREATE INDEX idx_flow_executions_flow_id ON flow_executions(flow_id);
CREATE INDEX idx_flow_executions_status ON flow_executions(status);
CREATE INDEX idx_flow_executions_started_at ON flow_executions(started_at DESC);

CREATE INDEX idx_flow_groups_flow_id ON flow_groups(flow_id);
CREATE INDEX idx_flow_groups_group_id ON flow_groups(group_id);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_flows_updated_at BEFORE UPDATE ON flows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_whatsapp_groups_updated_at BEFORE UPDATE ON whatsapp_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_client_api_keys_updated_at BEFORE UPDATE ON client_api_keys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default node types
INSERT INTO node_types (type_key, category, name, description, icon, config_schema) VALUES
-- Triggers
('whatsapp_message', 'trigger', 'WhatsApp Message', 'Triggered when any message is received', 'message-square', '{
    "type": "object",
    "properties": {
        "bot_lid": {"type": "string", "description": "Bot LID to filter mentions"}
    }
}'),

('whatsapp_mention', 'trigger', 'Bot Mentioned', 'Triggered when bot is mentioned in a message', 'at-sign', '{
    "type": "object",
    "properties": {
        "bot_lid": {"type": "string", "description": "Bot LID", "required": true}
    }
}'),

('schedule', 'trigger', 'Schedule', 'Triggered on a schedule (cron)', 'clock', '{
    "type": "object",
    "properties": {
        "cron": {"type": "string", "description": "Cron expression", "required": true}
    }
}'),

-- Conditions
('text_contains', 'condition', 'Text Contains', 'Check if text contains a pattern', 'search', '{
    "type": "object",
    "properties": {
        "input": {"type": "string", "description": "Text to check"},
        "pattern": {"type": "string", "description": "Pattern to search for"},
        "case_sensitive": {"type": "boolean", "default": false}
    }
}'),

('text_not_empty', 'condition', 'Text Not Empty', 'Check if text is not empty', 'check-circle', '{
    "type": "object",
    "properties": {
        "input": {"type": "string", "description": "Text to check"}
    }
}'),

-- Actions
('rag_query', 'action', 'RAG Query', 'Query PDF documents using RAG', 'book-open', '{
    "type": "object",
    "properties": {
        "collection_name": {"type": "string", "description": "Qdrant collection name", "required": true},
        "query": {"type": "string", "description": "Query text", "required": true},
        "top_k": {"type": "integer", "default": 4, "description": "Number of results"},
        "model": {"type": "string", "default": "gemini-2.5-flash", "enum": ["gemini-2.5-flash", "gemini-1.5-pro"]},
        "include_conversation_history": {"type": "boolean", "default": true}
    }
}'),

('send_whatsapp_message', 'action', 'Send WhatsApp Message', 'Send a message to WhatsApp', 'send', '{
    "type": "object",
    "properties": {
        "chat_id": {"type": "string", "description": "Chat ID to send to", "required": true},
        "text": {"type": "string", "description": "Message text", "required": true},
        "reply_to": {"type": "string", "description": "Message ID to reply to"}
    }
}'),

('http_request', 'action', 'HTTP Request', 'Make an HTTP request to an external API', 'globe', '{
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to request", "required": true},
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
        "headers": {"type": "object", "description": "Request headers"},
        "body": {"type": "string", "description": "Request body (JSON)"}
    }
}'),

('delay', 'action', 'Delay', 'Wait for a specified duration', 'pause', '{
    "type": "object",
    "properties": {
        "seconds": {"type": "integer", "description": "Seconds to wait", "required": true}
    }
}');

-- Example data for testing
-- Insert a test user
INSERT INTO users (email, password_hash, full_name) VALUES
('test@example.com', 'hashed_password_here', 'Test User');

-- Insert a test WhatsApp group
INSERT INTO whatsapp_groups (chat_id, name, description, member_count, is_enabled) VALUES
('120363402503743273@g.us', 'Tech Support Team', 'Customer support group', 24, true);

-- Insert a test flow
INSERT INTO flows (user_id, name, description, definition, trigger_type, trigger_config, tags, category)
SELECT 
    u.id,
    'PDF Q&A Bot',
    'Answers questions from PDF documents using RAG',
    '{
        "nodes": [
            {
                "id": "node_1",
                "type": "condition",
                "name": "Check if question is valid",
                "config": {
                    "condition_type": "text_not_empty",
                    "input": "{{trigger.message.body}}"
                },
                "on_success": "node_2",
                "on_failure": "node_error"
            },
            {
                "id": "node_2",
                "type": "action",
                "name": "Search PDF with RAG",
                "action_type": "rag_query",
                "config": {
                    "collection_name": "hehe huhu",
                    "query": "{{trigger.message.body}}",
                    "top_k": 4,
                    "model": "gemini-2.5-flash",
                    "include_conversation_history": true
                },
                "next": "node_3"
            },
            {
                "id": "node_3",
                "type": "action",
                "name": "Send reply to WhatsApp",
                "action_type": "send_whatsapp_message",
                "config": {
                    "chat_id": "{{trigger.message.chat_id}}",
                    "text": "{{node_2.rag_result}}",
                    "reply_to": "{{trigger.message.id}}"
                },
                "next": null
            }
        ]
    }'::jsonb,
    'whatsapp_mention',
    '{"bot_lid": "35077249618150"}'::jsonb,
    ARRAY['rag', 'pdf', 'qa'],
    'customer_support'
FROM users u
WHERE u.email = 'test@example.com';

-- Link flow to group
INSERT INTO flow_groups (flow_id, group_id)
SELECT f.id, g.id
FROM flows f, whatsapp_groups g
WHERE f.name = 'PDF Q&A Bot' AND g.chat_id = '120363402503743273@g.us';
