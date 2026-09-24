-- Reference only: db.create_all() (see app.py) creates this schema
-- automatically from models.py on first run. This file is here so you can
-- read the schema at a glance, or run it by hand / adapt it into an Alembic
-- migration if you'd rather manage schema changes explicitly.

CREATE TABLE users (
    id                      SERIAL PRIMARY KEY,
    username                VARCHAR(40) UNIQUE NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    display_name            VARCHAR(20) NOT NULL DEFAULT 'Player One',
    xp                      INTEGER NOT NULL DEFAULT 0,
    streak                  INTEGER NOT NULL DEFAULT 0,
    longest_streak          INTEGER NOT NULL DEFAULT 0,
    last_completion_date    DATE,
    total_quests_completed  INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE custom_quests (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(60) NOT NULL,
    category    VARCHAR(20) NOT NULL,
    xp          INTEGER NOT NULL DEFAULT 15,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE completions (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quest_id      VARCHAR(40) NOT NULL,
    quest_name    VARCHAR(60) NOT NULL,
    xp_awarded    INTEGER NOT NULL,
    completed_on  DATE NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, quest_id, completed_on)
);

CREATE TABLE badges (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code        VARCHAR(20) NOT NULL,
    earned_at   TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, code)
);

CREATE INDEX idx_completions_user_date ON completions(user_id, completed_on);
