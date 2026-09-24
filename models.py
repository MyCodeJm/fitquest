"""
SQLAlchemy models.

In the original app, everything (xp, streak, completed quest ids, custom
quests, badges) lived in ONE localStorage JSON blob (or, if you signed in
with Google, one Firestore document shaped exactly the same way). Here that
single blob is normalized into four real tables so Postgres can enforce
relationships and so multiple users can't clobber each other's rows.
"""

from datetime import date

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(20), nullable=False, default="Player One")

    xp = db.Column(db.Integer, nullable=False, default=0)
    streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_completion_date = db.Column(db.Date, nullable=True)
    total_quests_completed = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    custom_quests = db.relationship(
        "CustomQuest", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    completions = db.relationship(
        "Completion", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    badges = db.relationship(
        "Badge", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def completed_today_ids(self) -> set:
        today = date.today()
        rows = self.completions.filter(Completion.completed_on == today).all()
        return {r.quest_id for r in rows}

    def badge_codes(self) -> set:
        return {b.code for b in self.badges}


class CustomQuest(db.Model):
    """A user-authored quest (equivalent of state.customQuests[] in the JS)."""

    __tablename__ = "custom_quests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    xp = db.Column(db.Integer, nullable=False, default=15)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def public_id(self) -> str:
        # Mirrors the old "custom_" + Date.now() id scheme closely enough
        # that the frontend's id handling doesn't need to change.
        return f"custom_{self.id}"

    def as_dict(self) -> dict:
        return {
            "id": self.public_id(),
            "name": self.name,
            "category": self.category,
            "xp": self.xp,
            "difficulty": "Medium",
            "tip": None,
        }


class Completion(db.Model):
    """One row per quest completed on a given day.

    The old app only ever needed "was this quest id completed today" plus a
    running xp/streak/total counter, all crammed into one JSON object. Here
    each completion is its own row, which is what actually lets a database
    (rather than a single blob) answer questions like "show me last week's
    history" later on, and is what a real backend is for.
    """

    __tablename__ = "completions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    quest_id = db.Column(db.String(40), nullable=False)
    quest_name = db.Column(db.String(60), nullable=False)
    xp_awarded = db.Column(db.Integer, nullable=False)
    completed_on = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("user_id", "quest_id", "completed_on", name="uq_one_completion_per_day"),
    )


class Badge(db.Model):
    """An unlocked achievement (equivalent of state.badges[] in the JS)."""

    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    earned_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("user_id", "code", name="uq_one_badge_per_user"),
    )
