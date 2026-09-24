# FitQuest — Flask + PostgreSQL edition

A port of the original single-file HTML/CSS/JS "FitQuest" gamified workout
tracker into a real Python web app with a Postgres-backed, multi-user
backend. Every game rule (XP curve, ranks, streaks, badges, the daily
quest rotation, the daily "boss" challenge) behaves exactly like the
original — only *where the state lives* changed.

## Project layout

```
fitquest/
  app.py              Flask app: routes, auth, request handlers
  models.py            SQLAlchemy models (User, CustomQuest, Completion, Badge)
  quests.py            Quest/boss data + pure game-logic (no Flask/DB imports)
  templates/
    base.html
    login.html
    register.html
    index.html          the dashboard (HUD, quests, boss, badges)
  static/
    style.css           ported from the original <style> block
    app.js               fetch()-based interactivity
  schema.sql            reference SQL schema (informational)
  requirements.txt
  .env.example
```

## Running it locally

1. **Install PostgreSQL** and create a database + user:
   ```sql
   CREATE USER fitquest WITH PASSWORD 'fitquest';
   CREATE DATABASE fitquest OWNER fitquest;
   ```
2. **Install Python deps:**
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure:** copy `.env.example` to `.env` and adjust `DATABASE_URL` /
   `SECRET_KEY` if needed.
4. **Create the tables and run:**
   ```bash
   python app.py
   ```
   `app.py`'s `__main__` block calls `db.create_all()` once at startup for
   local dev convenience — that creates the four tables from `models.py` if
   they don't already exist (equivalent to running `schema.sql` by hand).
   For a real deployment, swap this for Alembic migrations so schema
   changes are tracked instead of inferred.
5. Visit `http://localhost:5000`, register an account, and play.

## Why this architecture

**The core question the rewrite has to answer** is: the original app kept
its *entire* state — XP, streak, which quests are done today, custom
quests, unlocked badges — in one JSON object, either in `localStorage`
(per-browser) or, if you signed in with Google, in one matching Firestore
document (per-account). That's fine for a toy, but it means there's no
real multi-user backend and no relational structure to the data. Moving to
Python + Postgres meant deciding how to split that one blob into an actual
schema:

- **`users`** holds the counters that used to be scalar fields on the blob
  (`xp`, `streak`, `longest_streak`, `last_completion_date`,
  `total_quests_completed`) plus real auth (`username` +
  `password_hash`, hashed with Werkzeug's `generate_password_hash`,
  which is why Flask-Login-style sessions replaced the old Firebase
  Google sign-in — there's no OAuth provider wired up here, so plain
  username/password is the honest equivalent; swapping in real Google
  OAuth later would only touch the two auth routes).
- **`custom_quests`** replaces `state.customQuests[]` — one row per
  user-authored quest instead of an array embedded in the blob.
- **`completions`** replaces `state.completedToday[]`. This is the
  biggest structural change: the original only ever tracked *today's*
  completions (it recomputed "is it a new day" and reset the list). A
  real database has no reason to throw that history away, so every
  completion is its own permanent row (`user_id`, `quest_id`,
  `completed_on`, `xp_awarded`). "Completed today" is just
  `WHERE completed_on = today`, but the history now exists if you ever
  want a calendar view or a weekly report — that's the actual advantage
  of a real backend over a JSON blob, so I designed for it even though
  the current UI doesn't expose it yet.
- **`badges`** replaces `state.badges[]` — one row per unlocked
  achievement per user, with a unique constraint so the same badge can't
  be double-awarded.

**`quests.py` stays plain Python with no Flask/SQLAlchemy imports on
purpose.** The quest pool, the boss pool, the XP curve, and the
deterministic "same 8 quests all day, new set tomorrow" trick are *rules
of the game*, not state — they don't belong in the database, exactly like
they weren't in Firestore in the original (only completions/xp/custom
quests were saved; the pools themselves were hardcoded in the `<script>`
tag). I kept that split. The one implementation detail I didn't try to
reproduce exactly: the original hand-rolled an xorshift PRNG seeded from a
hashed string so "today's date + category" always shuffles the same way.
Python's `random.Random(seed)` gives the same *property* (deterministic
per seed, well-distributed) from the standard library, so I hash the date
string with `sha256` and seed Python's PRNG with that instead of
reimplementing the bit-twiddling — same behavior, more idiomatic Python.

**Routes are split into "pages" vs. "actions."** `GET /` server-renders
the whole dashboard from a `build_state()` call that reads the DB and
merges it with `quests.py`'s pool — this is the direct replacement for the
old `renderHud()`/`renderQuests()`/`renderBoss()`/`checkAndRenderBadges()`
functions, except now it runs once on the server instead of on every
`localStorage` read. The four `/api/...` POST routes (`complete`,
`custom`, `profile/name`, `reset`) are what `static/app.js` calls with
`fetch()` — they mirror the original event handlers
(`completeQuest`, the add-quest button, the name `change` listener, the
reset button) almost 1:1, just hitting a server instead of mutating an
in-memory object. Each one returns the freshly computed state as JSON so
the page can patch itself without a full reload — that's the "make it not
static" part: the frontend is still snappy and doesn't hard-reload on
every click, but the source of truth is now Postgres, shared across
devices and sessions, instead of one browser's `localStorage`.

**Badge/streak/level logic moved server-side unchanged in spirit.**
`completeQuest()` (JS) and `complete_quest()` (Python route) do the same
three things in the same order: record the completion, update the
streak (only on the *first* completion of the day, checking whether
yesterday's date matches to decide "continue streak" vs. "reset to 1"),
then check every badge rule against the new counters. The only behavior
change is that this now runs inside a transaction against real rows
instead of a mutable object, so it's safe if two requests land
concurrently.

## What's genuinely different from the original (and why)

- **Accounts are real.** The original was single-player-per-browser with
  optional Firebase cloud sync bolted on as an afterthought (and it
  silently no-ops if you never fill in a Firebase config). Since the ask
  was "make it not static" with a real database, I made accounts the
  primary path — you register/sign in, and everything is tied to your
  `user_id` from the start, rather than being a local guest profile that
  *might* sync.
- **History isn't thrown away.** The JS reset `completedToday` on every
  new day. The `completions` table keeps every row, so nothing about the
  current UI needed a history view, but a future "show my last 30 days"
  feature is just a query away instead of a schema change.
- **No client-only persistence.** There's no `localStorage` fallback for
  guests — if you're not signed in, you're redirected to `/login`. That's
  a deliberate simplification: mixing "local guest state" with "real
  account state" was most of the complexity in the original's Firebase
  code, and the ask here was specifically to replace static/local state
  with a database.

## Known gaps if you want to take this further

- No password-reset flow, no email verification — `username` +
  `password` only, since that's the minimum to demonstrate real
  multi-user auth.
- No Alembic migrations; `db.create_all()` is dev-only.
- No tests included beyond the manual checks used while building this
  (quest-selection determinism, template rendering) — a `pytest` suite
  against a test database would be the natural next step.
