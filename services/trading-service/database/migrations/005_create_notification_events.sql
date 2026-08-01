-- 005_create_notification_events.sql

CREATE TABLE notification_events (

    id BIGSERIAL PRIMARY KEY,

    event_type VARCHAR(50) NOT NULL,

    order_id VARCHAR(100),

    symbol VARCHAR(50),

    severity VARCHAR(20) NOT NULL DEFAULT 'INFO',

    message TEXT NOT NULL,

    payload JSONB DEFAULT '{}'::jsonb,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    sent_at TIMESTAMP WITH TIME ZONE
);


CREATE INDEX idx_notification_events_type
ON notification_events(event_type);


CREATE INDEX idx_notification_events_status
ON notification_events(status);


CREATE INDEX idx_notification_events_order_id
ON notification_events(order_id);


CREATE INDEX idx_notification_events_created_at
ON notification_events(created_at);