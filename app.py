"""
FitQuest - Flask + PostgreSQL edition.

This is a straight port of a single-file HTML/CSS/JS toy (localStorage for
persistence, optional Firebase for cross-device sync) into a small but real
server-rendered web app:

  browser  <-- HTML from Jinja2 templates, small fetch() calls for actions
     |
   Flask   <-- routes below: auth, quest completion, custom quests, reset
     |
 PostgreSQL <-- users / custom_quests / completions / badges (models.py)

Game rules (XP curve, ranks, the deterministic "same 8 quests all day,
different set tomorrow" trick, badge thresholds) live in quests.py and are
unchanged from the original - only *where state is stored* changed, from a
browser-only JSON blob to real database rows shared across devices.
"""

import os
from datetime import date

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from models import Badge, Completion, CustomQuest, User, db
import quests as game

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg2://fitquest:fitquest@localhost:5432/fitquest"
    )
    # Render/Heroku-style hosts hand out "postgres://" URLs; SQLAlchemy 1.4+
    # only accepts the "postgresql://" scheme, so normalize it here rather
    # than asking whoever deploys this to edit the env var by hand.
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    # Create tables on startup if they don't exist yet. This runs whether the
    # app is launched with `python app.py` (dev) or `gunicorn app:app` (prod,
    # e.g. on Render) since gunicorn imports this module without executing
    # the __main__ block below. Fine at this scale; swap for Alembic
    # migrations if the schema starts changing often.
    with app.app_context():
        db.create_all()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        return db.session.get(User, user_id)

    def login_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    # ------------------------------------------------------------------
    # Core game-state assembly - turns DB rows + quests.py data into the
    # same shape the Jinja2 template (and the old JS render functions) need.
    # ------------------------------------------------------------------
    def build_state(user: User) -> dict:
        today = date.today()
        default_quests = game.todays_default_quests(today)
        boss = game.todays_boss_quest(today)
        custom = [cq.as_dict() for cq in user.custom_quests]
        all_quests = default_quests + custom

        completed_today = user.completed_today_ids()
        lv = game.level_from_xp(user.xp)

        return {
            "player_name": user.display_name,
            "level": lv["level"],
            "rank": game.rank_for_level(lv["level"]),
            "xp_into_level": lv["into"],
            "xp_needed": lv["need"],
            "xp_pct": round((lv["into"] / lv["need"]) * 100) if lv["need"] else 0,
            "streak": user.streak,
            "quests": [
                {**q, "done": q["id"] in completed_today} for q in all_quests
            ],
            "boss": {**boss, "done": boss["id"] in completed_today},
            "badges": [
                {**b, "unlocked": b["id"] in user.badge_codes()} for b in game.BADGE_DEFS
            ],
        }

    # ------------------------------------------------------------------
    # Auth routes
    # ------------------------------------------------------------------
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return render_template("register.html")

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "").strip() or "Player One"

        if not username or not password:
            return render_template("register.html", error="Username and password are required.")
        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="That username is already taken.")

        user = User(username=username, display_name=display_name[:20])
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        return redirect(url_for("index"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            return render_template("login.html", error="Incorrect username or password.")

        session["user_id"] = user.id
        return redirect(url_for("index"))

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @app.route("/")
    @login_required
    def index():
        user = current_user()
        return render_template("index.html", state=build_state(user), category_filters=["All"] + game.CATEGORIES)

    # ------------------------------------------------------------------
    # Actions (called via fetch() from static/app.js; return JSON so the
    # page can update in place instead of doing a full reload - this is
    # the "make it not static" part of the request)
    # ------------------------------------------------------------------
    @app.route("/api/quest/complete/<quest_id>", methods=["POST"])
    @login_required
    def complete_quest(quest_id):
        user = current_user()
        today = date.today()

        if quest_id in user.completed_today_ids():
            return jsonify({"error": "already completed"}), 400

        quest = game.quest_by_id(quest_id)
        if quest is None and quest_id.startswith("custom_"):
            custom = db.session.get(CustomQuest, int(quest_id.split("_", 1)[1]))
            if custom and custom.user_id == user.id:
                quest = custom.as_dict()
        if quest is None:
            return jsonify({"error": "unknown quest"}), 404

        prev_level = game.level_from_xp(user.xp)["level"]

        db.session.add(Completion(
            user_id=user.id, quest_id=quest_id, quest_name=quest["name"],
            xp_awarded=quest["xp"], completed_on=today,
        ))
        user.xp += quest["xp"]
        user.total_quests_completed += 1

        completed_today = user.completed_today_ids() | {quest_id}
        if len(completed_today) == 1:  # first completion today -> touch the streak
            if user.last_completion_date == game.yesterday(today):
                user.streak += 1
            elif user.last_completion_date != today:
                user.streak = 1
            user.last_completion_date = today
        user.longest_streak = max(user.longest_streak, user.streak)

        db.session.commit()  # commit completion + counters before evaluating badges

        new_badges = _check_badges(user)
        db.session.commit()

        new_level = game.level_from_xp(user.xp)["level"]
        if new_level > prev_level:
            message = f"Level up! You're now level {new_level} \u2014 {game.rank_for_level(new_level)}!"
        elif new_badges:
            message = f"Achievement unlocked: {new_badges[0]}"
        else:
            message = f"+{quest['xp']} XP \u2014 quest complete!"

        return jsonify({"state": build_state(user), "message": message})

    @app.route("/api/quest/custom", methods=["POST"])
    @login_required
    def add_custom_quest():
        user = current_user()
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()[:40]
        category = data.get("category") if data.get("category") in game.CATEGORIES else "Strength"
        xp = data.get("xp", 15)
        try:
            xp = max(5, min(100, int(xp)))
        except (TypeError, ValueError):
            xp = 15

        if not name:
            return jsonify({"error": "name is required"}), 400

        db.session.add(CustomQuest(user_id=user.id, name=name, category=category, xp=xp))
        db.session.commit()
        return jsonify({"state": build_state(user), "message": "Custom quest added!"})

    @app.route("/api/profile/name", methods=["POST"])
    @login_required
    def update_name():
        user = current_user()
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()[:20]
        user.display_name = name or "Player One"
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reset", methods=["POST"])
    @login_required
    def reset_progress():
        user = current_user()
        Completion.query.filter_by(user_id=user.id).delete()
        Badge.query.filter_by(user_id=user.id).delete()
        CustomQuest.query.filter_by(user_id=user.id).delete()
        user.xp = 0
        user.streak = 0
        user.longest_streak = 0
        user.last_completion_date = None
        user.total_quests_completed = 0
        db.session.commit()
        return jsonify({"state": build_state(user)})

    # ------------------------------------------------------------------
    def _check_badges(user: User) -> list:
        """Evaluate badge rules against current counters; persist new ones."""
        lv = game.level_from_xp(user.xp)["level"]
        boss_ids_done_today = {b["id"] for b in game.BOSS_POOL} & user.completed_today_ids()
        known = user.badge_codes()

        earned_now = {
            "streak3": user.longest_streak >= 3,
            "streak7": user.longest_streak >= 7,
            "level5": lv >= 5,
            "level10": lv >= 10,
            "quests25": user.total_quests_completed >= 25,
            "quests100": user.total_quests_completed >= 100,
            "boss1": "boss1" in known or bool(boss_ids_done_today),
        }

        newly = []
        for code, earned in earned_now.items():
            if earned and code not in known:
                db.session.add(Badge(user_id=user.id, code=code))
                label = next(b["label"] for b in game.BADGE_DEFS if b["id"] == code)
                newly.append(label)
        return newly

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
