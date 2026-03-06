-- Migration 030: Create economic_calendar table
-- Purpose: Store sanitized economic calendar events with immutability enforcement
-- Author: FASE C Data Integration
-- Date: 2026-03-05

CREATE TABLE IF NOT EXISTS economic_calendar (
    -- Internal ID
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Event Identifier (system-assigned UUID)
    event_id TEXT UNIQUE NOT NULL,
    
    -- Core Event Data
    event_name TEXT NOT NULL,
    country TEXT NOT NULL,
    currency TEXT,
    impact_score TEXT CHECK(impact_score IN ('HIGH', 'MEDIUM', 'LOW', NULL)),
    
    -- Economic Data (optional)
    forecast REAL,
    actual REAL,
    previous REAL,
    
    -- Time and Source
    event_time_utc TEXT NOT NULL,
    provider_source TEXT NOT NULL,
    
    -- Metadata
    is_verified BOOLEAN DEFAULT 0,
    data_version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_economic_calendar_country 
    ON economic_calendar(country);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_event_time 
    ON economic_calendar(event_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_provider 
    ON economic_calendar(provider_source);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_impact 
    ON economic_calendar(impact_score);

-- Composite index for typical filter patterns
CREATE INDEX IF NOT EXISTS idx_economic_calendar_country_time 
    ON economic_calendar(country, event_time_utc DESC);

-- Composite index for provider + time queries
CREATE INDEX IF NOT EXISTS idx_economic_calendar_provider_time 
    ON economic_calendar(provider_source, event_time_utc DESC);
