-- Production-Ready FinTech Reconciliation Database Schema
-- Includes data integrity, performance, security, and compliance features

-- Create database with proper encoding and collation
CREATE DATABASE fintech_reconciliation 
    WITH ENCODING 'UTF8' 
    LC_COLLATE = 'en_US.UTF-8' 
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE template0;

-- Connect to the database
\c fintech_reconciliation;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For fuzzy text matching
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- For composite indexes

-- Create custom types for better data integrity
CREATE TYPE reconciliation_status AS ENUM ('running', 'completed', 'failed', 'cancelled');
CREATE TYPE transaction_status AS ENUM ('completed', 'pending', 'failed', 'cancelled');
CREATE TYPE audit_action AS ENUM ('insert', 'update', 'delete', 'reconciliation_started', 'reconciliation_completed', 'system_check');

-- ==================================================
-- CORE BUSINESS TABLES
-- ==================================================

-- Reconciliation runs table with enhanced constraints
CREATE TABLE reconciliation_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_date DATE NOT NULL,
    processor_name VARCHAR(50) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    status reconciliation_status DEFAULT 'running' NOT NULL,
    processor_transaction_count INTEGER CHECK (processor_transaction_count >= 0),
    internal_transaction_count INTEGER CHECK (internal_transaction_count >= 0),
    missing_transaction_count INTEGER CHECK (missing_transaction_count >= 0),
    total_discrepancy_amount DECIMAL(15,2) CHECK (total_discrepancy_amount >= 0),
    report_s3_key VARCHAR(500),
    configuration JSONB, -- Store run-specific configuration
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER,
    
    -- Business logic constraints
    CONSTRAINT chk_end_after_start CHECK (end_time IS NULL OR end_time >= start_time),
    CONSTRAINT chk_business_date CHECK (run_date <= CURRENT_DATE + INTERVAL '1 day'), -- Allow slight future dating
    CONSTRAINT chk_completed_has_end_time CHECK (
        status != 'completed' OR end_time IS NOT NULL
    ),
    CONSTRAINT chk_failed_has_error CHECK (
        status != 'failed' OR error_message IS NOT NULL
    ),
    
    -- Prevent duplicate runs
    UNIQUE(run_date, processor_name)
);

-- Missing transactions table with comprehensive validation
CREATE TABLE missing_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reconciliation_run_id UUID NOT NULL REFERENCES reconciliation_runs(id) ON DELETE CASCADE,
    transaction_id VARCHAR(100) NOT NULL,
    processor_name VARCHAR(50) NOT NULL,
    amount DECIMAL(15,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    merchant_id VARCHAR(50),
    transaction_date TIMESTAMP WITH TIME ZONE NOT NULL,
    reference_number VARCHAR(100),
    fee DECIMAL(15,2) CHECK (fee >= 0),
    status transaction_status DEFAULT 'completed',
    metadata JSONB, -- Store additional transaction details
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Business logic constraints  
    CONSTRAINT chk_currency_code CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT chk_transaction_date_reasonable CHECK (
        transaction_date >= CURRENT_DATE - INTERVAL '1 year' AND
        transaction_date <= CURRENT_DATE + INTERVAL '1 day'
    ),
    CONSTRAINT chk_fee_vs_amount CHECK (fee IS NULL OR fee <= amount * 0.5) -- Fee shouldn't exceed 50% of amount
);

-- ==================================================
-- AUDIT AND COMPLIANCE TABLES
-- ==================================================

-- Immutable audit log for compliance
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    action audit_action NOT NULL,
    table_name VARCHAR(50),
    record_id UUID,
    old_values JSONB,
    new_values JSONB,
    user_id VARCHAR(100) DEFAULT CURRENT_USER,
    session_id VARCHAR(100),
    ip_address INET,
    application_name VARCHAR(100) DEFAULT 'reconciliation_system',
    
    -- Immutability constraint (prevent updates/deletes)
    immutable_after TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP + INTERVAL '1 minute'
);

-- Data quality monitoring table
CREATE TABLE data_quality_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reconciliation_run_id UUID NOT NULL REFERENCES reconciliation_runs(id),
    check_name VARCHAR(100) NOT NULL,
    check_result BOOLEAN NOT NULL,
    check_details JSONB,
    severity VARCHAR(20) CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- System health monitoring
CREATE TABLE system_health (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    check_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    component VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('healthy', 'degraded', 'unhealthy')),
    response_time_ms INTEGER CHECK (response_time_ms >= 0),
    error_message TEXT,
    metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Configuration management table
CREATE TABLE system_configuration (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    description TEXT,
    environment VARCHAR(20) DEFAULT 'production',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER
);

-- ==================================================
-- PERFORMANCE INDEXES
-- ==================================================

-- Primary business query indexes
CREATE INDEX idx_reconciliation_runs_date_processor ON reconciliation_runs(run_date DESC, processor_name);
CREATE INDEX idx_reconciliation_runs_status ON reconciliation_runs(status) WHERE status IN ('running', 'failed');
CREATE INDEX idx_reconciliation_runs_processor_date_status ON reconciliation_runs(processor_name, run_date DESC, status);

-- Missing transactions indexes
CREATE INDEX idx_missing_transactions_run_id ON missing_transactions(reconciliation_run_id);
CREATE INDEX idx_missing_transactions_processor_date ON missing_transactions(processor_name, transaction_date DESC);
CREATE INDEX idx_missing_transactions_amount ON missing_transactions(amount DESC); -- For high-value transaction queries
CREATE INDEX idx_missing_transactions_transaction_id ON missing_transactions USING gin(transaction_id gin_trgm_ops);

-- Audit and monitoring indexes
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_action_timestamp ON audit_log(action, timestamp DESC);
CREATE INDEX idx_audit_log_table_record ON audit_log(table_name, record_id) WHERE record_id IS NOT NULL;

CREATE INDEX idx_data_quality_run_severity ON data_quality_checks(reconciliation_run_id, severity);
CREATE INDEX idx_system_health_component_time ON system_health(component, check_time DESC);

-- Partial indexes for common queries
CREATE INDEX idx_reconciliation_runs_recent_completed ON reconciliation_runs(run_date DESC, processor_name) 
    WHERE status = 'completed' AND run_date >= CURRENT_DATE - INTERVAL '90 days';

CREATE INDEX idx_missing_transactions_high_value ON missing_transactions(reconciliation_run_id, amount DESC)
    WHERE amount >= 1000.00;

-- ==================================================
-- ROW LEVEL SECURITY (Multi-tenancy ready)
-- ==================================================

-- Enable RLS on sensitive tables
ALTER TABLE reconciliation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE missing_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Example policies (customize based on your authentication system)
-- CREATE POLICY reconciliation_processor_isolation ON reconciliation_runs
--     FOR ALL TO reconciliation_user
--     USING (processor_name = current_setting('app.current_processor', true));

-- ==================================================
-- ROLES AND PERMISSIONS
-- ==================================================

-- Create application roles
CREATE ROLE reconciliation_reader;
CREATE ROLE reconciliation_writer;
CREATE ROLE reconciliation_admin;

-- Reader permissions
GRANT CONNECT ON DATABASE fintech_reconciliation TO reconciliation_reader;
GRANT USAGE ON SCHEMA public TO reconciliation_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reconciliation_reader;

-- Writer permissions (includes reader)
GRANT reconciliation_reader TO reconciliation_writer;
GRANT INSERT, UPDATE ON reconciliation_runs, missing_transactions, data_quality_checks TO reconciliation_writer;
GRANT INSERT ON audit_log, system_health TO reconciliation_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO reconciliation_writer;

-- Admin permissions (includes writer)
GRANT reconciliation_writer TO reconciliation_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO reconciliation_admin;

-- ==================================================
-- TRIGGERS AND FUNCTIONS
-- ==================================================

-- Automatic updated_at timestamp function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to reconciliation_runs
CREATE TRIGGER update_reconciliation_runs_updated_at 
    BEFORE UPDATE ON reconciliation_runs 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Audit trail trigger function
CREATE OR REPLACE FUNCTION audit_trigger_function()
RETURNS TRIGGER AS $$
BEGIN
    -- Prevent modifications to audit_log after the immutable period
    IF TG_TABLE_NAME = 'audit_log' AND TG_OP IN ('UPDATE', 'DELETE') THEN
        IF OLD.immutable_after < CURRENT_TIMESTAMP THEN
            RAISE EXCEPTION 'Cannot modify immutable audit record';
        END IF;
    END IF;
    
    -- Log changes to audited tables
    IF TG_TABLE_NAME IN ('reconciliation_runs', 'missing_transactions') THEN
        INSERT INTO audit_log (action, table_name, record_id, old_values, new_values)
        VALUES (
            LOWER(TG_OP)::audit_action,
            TG_TABLE_NAME,
            COALESCE(NEW.id, OLD.id),
            CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE NULL END,
            CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) ELSE NULL END
        );
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply audit triggers
CREATE TRIGGER audit_reconciliation_runs
    AFTER INSERT OR UPDATE OR DELETE ON reconciliation_runs
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER audit_missing_transactions
    AFTER INSERT OR UPDATE OR DELETE ON missing_transactions
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER protect_audit_log
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_trigger_function();

-- Data validation function for reconciliation results
CREATE OR REPLACE FUNCTION validate_reconciliation_totals()
RETURNS TRIGGER AS $$
DECLARE
    actual_missing_count INTEGER;
    actual_discrepancy_amount DECIMAL(15,2);
BEGIN
    -- Only validate on completed reconciliations
    IF NEW.status = 'completed' THEN
        SELECT COUNT(*), COALESCE(SUM(amount), 0)
        INTO actual_missing_count, actual_discrepancy_amount
        FROM missing_transactions 
        WHERE reconciliation_run_id = NEW.id;
        
        -- Verify counts match
        IF NEW.missing_transaction_count != actual_missing_count THEN
            RAISE EXCEPTION 'Missing transaction count mismatch: recorded %, actual %', 
                NEW.missing_transaction_count, actual_missing_count;
        END IF;
        
        -- Verify amounts match (within 1 cent tolerance for rounding)
        IF ABS(NEW.total_discrepancy_amount - actual_discrepancy_amount) > 0.01 THEN
            RAISE EXCEPTION 'Discrepancy amount mismatch: recorded %, actual %',
                NEW.total_discrepancy_amount, actual_discrepancy_amount;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply validation trigger
CREATE TRIGGER validate_reconciliation_totals_trigger
    AFTER UPDATE ON reconciliation_runs
    FOR EACH ROW EXECUTE FUNCTION validate_reconciliation_totals();
-- ==================================================
-- VIEWS FOR COMMON QUERIES
-- ==================================================

-- Recent reconciliation summary view
CREATE VIEW v_recent_reconciliations AS
SELECT 
    r.id,
    r.run_date,
    r.processor_name,
    r.status,
    r.processor_transaction_count,
    r.internal_transaction_count,
    r.missing_transaction_count,
    r.total_discrepancy_amount,
    EXTRACT(EPOCH FROM (r.end_time - r.start_time)) / 60 as duration_minutes,
    r.created_at
FROM reconciliation_runs r
WHERE r.run_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY r.run_date DESC, r.processor_name;

-- High-value missing transactions view
CREATE VIEW v_high_value_missing_transactions AS
SELECT 
    r.run_date,
    r.processor_name,
    mt.transaction_id,
    mt.amount,
    mt.merchant_id,
    mt.transaction_date,
    mt.reference_number
FROM missing_transactions mt
JOIN reconciliation_runs r ON mt.reconciliation_run_id = r.id
WHERE mt.amount >= 1000.00
  AND r.run_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY mt.amount DESC;

-- Daily reconciliation metrics view
CREATE VIEW v_daily_reconciliation_metrics AS
SELECT 
    run_date,
    processor_name,
    COUNT(*) as reconciliation_count,
    AVG(missing_transaction_count) as avg_missing_count,
    SUM(total_discrepancy_amount) as total_daily_discrepancy,
    MAX(total_discrepancy_amount) as max_discrepancy,
    COUNT(CASE WHEN missing_transaction_count = 0 THEN 1 END) as perfect_reconciliations
FROM reconciliation_runs
WHERE run_date >= CURRENT_DATE - INTERVAL '90 days'
  AND status = 'completed'
GROUP BY run_date, processor_name
ORDER BY run_date DESC, processor_name;

-- ==================================================
-- INITIAL CONFIGURATION DATA
-- ==================================================

-- Insert default system configuration
INSERT INTO system_configuration (config_key, config_value, description) VALUES
('reconciliation.tolerance_amount', '0.01', 'Tolerance amount for reconciliation matching'),
('reconciliation.max_discrepancy_threshold', '10000.00', 'Maximum discrepancy amount before escalation'),
('notification.high_discrepancy_emails', '["operations@company.com", "finance@company.com"]', 'Email list for high discrepancy alerts'),
('system.retention_days_audit_log', '2555', 'Days to retain audit log records (7 years)'),
('system.retention_days_reconciliation_data', '1095', 'Days to retain reconciliation data (3 years)');

-- ==================================================
-- COMMENTS FOR DOCUMENTATION
-- ==================================================

COMMENT ON TABLE reconciliation_runs IS 'Primary table storing reconciliation execution metadata and results';
COMMENT ON TABLE missing_transactions IS 'Detailed records of transactions found in processor but missing from internal systems';
COMMENT ON TABLE audit_log IS 'Immutable audit trail for compliance and forensic analysis';
COMMENT ON TABLE data_quality_checks IS 'Results of data quality validations performed during reconciliation';
COMMENT ON TABLE system_health IS 'System component health monitoring and performance metrics';
COMMENT ON TABLE system_configuration IS 'Application configuration management with environment support';

-- Grant permissions to views
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reconciliation_reader;

-- Final setup message
SELECT 'Production-ready reconciliation database schema created successfully' as status;