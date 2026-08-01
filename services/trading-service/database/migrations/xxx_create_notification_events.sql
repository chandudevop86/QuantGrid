CREATE TABLE notification_events (

    id BIGSERIAL PRIMARY KEY,

    event_type VARCHAR(100) NOT NULL,

    subject TEXT NOT NULL,

    message TEXT NOT NULL,

    channel VARCHAR(30) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    reference_type VARCHAR(50),

    reference_id VARCHAR(100),

    payload JSONB DEFAULT '{}'::jsonb,

    error TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    sent_at TIMESTAMP WITH TIME ZONE
);


CREATE INDEX idx_notification_status
ON notification_events(status);


CREATE INDEX idx_notification_event_type
ON notification_events(event_type);


CREATE INDEX idx_notification_reference
ON notification_events(reference_id);