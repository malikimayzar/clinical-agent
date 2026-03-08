CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
    paper_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arxiv_id    VARCHAR(50) UNIQUE,
    title       TEXT NOT NULL,
    abstract    TEXT,
    authors     TEXT[],
    date        TIMESTAMP DEFAULT NOW(),
    source      VARCHAR(20) DEFAULT 'arxiv',
    processed   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id          UUID REFERENCES papers(paper_id),
    text              TEXT NOT NULL,
    confidence        FLOAT,
    faithfulness_score FLOAT,
    topic_tags        TEXT[],
    embedding         vector(768),
    status            VARCHAR(20) CHECK (status IN ('NEW','CONFIRMED','CONFLICT','UNCERTAIN')),
    severity          VARCHAR(10) CHECK (severity IN ('minor','major','critical')),
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID,
    paper_id    UUID REFERENCES papers(paper_id),
    claim_id    UUID REFERENCES claims(claim_id),
    node        VARCHAR(50),
    action      TEXT,
    score       FLOAT,
    label       VARCHAR(20),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    run_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at       TIMESTAMP DEFAULT NOW(),
    finished_at      TIMESTAMP,
    status           VARCHAR(20) CHECK (status IN ('running','success','failed')),
    papers_processed INT DEFAULT 0,
    claims_extracted INT DEFAULT 0,
    conflicts_found  INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS claims_embedding_idx
    ON claims USING ivfflat (embedding vector_cosine_ops);
