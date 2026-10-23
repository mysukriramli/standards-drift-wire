CREATE SEQUENCE IF NOT EXISTS seq_commit_id START 1;

CREATE TABLE IF NOT EXISTS standards (
    doc_id VARCHAR PRIMARY KEY,
    title VARCHAR,
    current_status VARCHAR,
    publication_year INTEGER,
    publication_month VARCHAR,
    stream VARCHAR,
    area VARCHAR,
    obsoletes_json VARCHAR,
    obsoleted_by_json VARCHAR,
    updates_json VARCHAR,
    updated_by_json VARCHAR,
    content_hash VARCHAR,
    last_updated_utc VARCHAR
);

CREATE TABLE IF NOT EXISTS ledger (
    commit_id BIGINT PRIMARY KEY,
    timestamp_utc VARCHAR,
    operation VARCHAR,
    doc_id VARCHAR,
    old_status VARCHAR,
    new_status VARCHAR,
    obsoleted_by VARCHAR
);
