CREATE TABLE IF NOT EXISTS teams(
    id    VARCHAR(256) NOT NULL PRIMARY KEY,
    token   CHAR(32) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS admins(
    name        VARCHAR(256) NOT NULL PRIMARY KEY,
    password    CHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS runs(
    id          VARCHAR(256) NOT NULL PRIMARY KEY,
    team_id     VARCHAR(256) NOT NULL,
    description TEXT NOT NULL,
    track_persona BOOLEAN,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS requests(
    timestamp       DATETIME NOT NULL PRIMARY KEY,
    run_id          VARCHAR(256) NOT NULL,
    team_id         VARCHAR(256) NOT NULL,
    session_id      CHAR(36) NOT NULL,
    topic_id        VARCHAR(20) NOT NULL,
    user_id         CHAR(36) NOT NULL,
    api             VARCHAR(10) NOT NULL,
    user_utterance  TEXT NOT NULL,
    response        TEXT,
    citations       TEXT,
    ptkbs           TEXT,
    count_towards_credits BOOLEAN DEFAULT true,
    rubrik          VARCHAR(255),
    rubrik_score    INTEGER,
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY (team_id) REFERENCES teams(id)
);