"""
Game data and pure game-logic for FitQuest.

Everything in this file is intentionally free of Flask/SQLAlchemy imports.
It mirrors the logic that used to live inline in <script> in the original
HTML file (questPool, bossPool, levelFromXp, rankForLevel, the seeded daily
shuffle, and the badge rules) so the *rules of the game* are identical to
the original app - only where the state lives has changed.
"""

import hashlib
import random
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Static content (equivalent of the JS `questPool` / `bossPool` arrays)
# ---------------------------------------------------------------------------

QUEST_POOL = [
    {"id": "s1", "name": "20 Push-ups", "category": "Strength", "difficulty": "Medium", "xp": 15,
     "tip": "Keep your core tight and lower until your elbows hit about 90°."},
    {"id": "s2", "name": "30 Squats", "category": "Strength", "difficulty": "Medium", "xp": 15,
     "tip": "Keep your knees behind your toes and your chest up."},
    {"id": "s3", "name": "1-Minute Plank", "category": "Strength", "difficulty": "Easy", "xp": 10,
     "tip": "Keep your body in a straight line from head to heels."},
    {"id": "s4", "name": "15 Lunges (each leg)", "category": "Strength", "difficulty": "Medium", "xp": 15,
     "tip": "Step forward and lower until both knees are near 90°."},
    {"id": "s5", "name": "20 Sit-ups", "category": "Strength", "difficulty": "Easy", "xp": 10,
     "tip": "Keep feet flat and hands lightly behind your head."},
    {"id": "s6", "name": "10 Burpees", "category": "Strength", "difficulty": "Hard", "xp": 25,
     "tip": "Jump, drop to a push-up, then explode back up."},
    {"id": "c1", "name": "15-Minute Walk or Jog", "category": "Cardio", "difficulty": "Easy", "xp": 10,
     "tip": "Keep a pace where you can still talk, but feel your heart rate up."},
    {"id": "c2", "name": "5-Minute Jump Rope", "category": "Cardio", "difficulty": "Medium", "xp": 15,
     "tip": "Stay light on your feet - use your wrists, not your arms."},
    {"id": "c3", "name": "10-Minute Cycling", "category": "Cardio", "difficulty": "Easy", "xp": 10,
     "tip": "Keep a steady cadence at a moderate effort."},
    {"id": "c4", "name": "Climb 3 Flights of Stairs", "category": "Cardio", "difficulty": "Easy", "xp": 10,
     "tip": "Take stairs two at a time for extra intensity."},
    {"id": "c5", "name": "20-Minute Dance Session", "category": "Cardio", "difficulty": "Medium", "xp": 15,
     "tip": "Pick your favorite playlist and just move."},
    {"id": "c6", "name": "30-Minute Run", "category": "Cardio", "difficulty": "Hard", "xp": 25,
     "tip": "Pace yourself - finishing strong matters more than starting fast."},
    {"id": "f1", "name": "10-Minute Stretch Routine", "category": "Flexibility", "difficulty": "Easy", "xp": 10,
     "tip": "Hold each stretch for 20-30 seconds, don't bounce."},
    {"id": "f2", "name": "5-Minute Yoga Flow", "category": "Flexibility", "difficulty": "Easy", "xp": 10,
     "tip": "Sync your breath with each movement."},
    {"id": "f3", "name": "Touch Your Toes x10", "category": "Flexibility", "difficulty": "Easy", "xp": 5,
     "tip": "Bend from the hips, knees slightly soft."},
    {"id": "f4", "name": "Shoulder & Neck Stretch", "category": "Flexibility", "difficulty": "Easy", "xp": 5,
     "tip": "Great after long hours at a desk."},
    {"id": "f5", "name": "15-Minute Deep Stretch Session", "category": "Flexibility", "difficulty": "Medium", "xp": 15,
     "tip": "Focus on the areas that feel tightest today."},
    {"id": "w1", "name": "Drink 8 Glasses of Water", "category": "Wellness", "difficulty": "Easy", "xp": 10,
     "tip": "Keep a bottle nearby as a visual reminder."},
    {"id": "w2", "name": "Get 7+ Hours of Sleep", "category": "Wellness", "difficulty": "Medium", "xp": 15,
     "tip": "Consistency matters more than the exact bedtime."},
    {"id": "w3", "name": "5-Minute Meditation", "category": "Wellness", "difficulty": "Easy", "xp": 10,
     "tip": "Just focus on your breath - a wandering mind is normal."},
    {"id": "w4", "name": "Eat a Serving of Vegetables", "category": "Wellness", "difficulty": "Easy", "xp": 10,
     "tip": "Any vegetable counts - variety is a bonus."},
    {"id": "w5", "name": "No Screens 30 Min Before Bed", "category": "Wellness", "difficulty": "Medium", "xp": 10,
     "tip": "Try reading or stretching instead."},
    {"id": "w6", "name": "No Added Sugar Today", "category": "Wellness", "difficulty": "Hard", "xp": 20,
     "tip": "Check labels - sugar hides in a lot of packaged food."},
]

BOSS_POOL = [
    {"id": "b1", "name": "50 Push-ups Challenge", "xp": 40, "tip": "Break it into sets if needed - 5x10 works great."},
    {"id": "b2", "name": "5K Run", "xp": 45, "tip": "Pace yourself: aim for a steady, sustainable speed."},
    {"id": "b3", "name": "100 Squats Challenge", "xp": 40, "tip": "Split into rounds of 20 with short rests between."},
    {"id": "b4", "name": "10-Minute Plank Ladder", "xp": 40,
     "tip": "Alternate 30s plank / 15s rest until you hit 10 minutes total."},
    {"id": "b5", "name": "Full Body Circuit (3 Rounds)", "xp": 45,
     "tip": "Push-ups, squats, lunges, plank - 3 rounds, minimal rest."},
]

CATEGORIES = ["Strength", "Cardio", "Flexibility", "Wellness"]
QUESTS_PER_CATEGORY = 2

BADGE_DEFS = [
    {"id": "streak3", "label": "\U0001F525 3-Day Streak"},
    {"id": "streak7", "label": "\U0001F525 7-Day Streak"},
    {"id": "level5", "label": "\u2B50 Level 5"},
    {"id": "level10", "label": "\U0001F3C6 Level 10"},
    {"id": "quests25", "label": "\u2705 25 Quests Done"},
    {"id": "quests100", "label": "\u2705 100 Quests Done"},
    {"id": "boss1", "label": "\u2694 First Boss Defeated"},
]


# ---------------------------------------------------------------------------
# XP / level curve (equivalent of the JS levelFromXp / rankForLevel)
# ---------------------------------------------------------------------------

def level_from_xp(xp: int) -> dict:
    """Same cumulative curve as the original: level N needs N*100 XP."""
    level = 1
    remaining = xp
    while remaining >= level * 100:
        remaining -= level * 100
        level += 1
    return {"level": level, "into": remaining, "need": level * 100}


def rank_for_level(level: int) -> str:
    if level >= 11:
        return "Legend"
    if level >= 8:
        return "Champion"
    if level >= 5:
        return "Warrior"
    if level >= 3:
        return "Challenger"
    return "Rookie"


# ---------------------------------------------------------------------------
# Deterministic "daily" quest selection.
#
# The original JS hashed `todayStr() + "|" + category` into a 32-bit seed and
# fed it into a hand-rolled xorshift PRNG so that reloading the page on the
# same day always produced the same 8 quests, but a new day produced a new
# set. We don't need to reproduce that exact bit-shuffling algorithm - only
# its property (same date -> same picks, different date -> different picks).
# random.Random(seed) gives us that deterministically in the standard
# library, so we hash the same string with sha256 and seed Python's PRNG
# with it.
# ---------------------------------------------------------------------------

def _seed_for(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def todays_default_quests(for_date: date) -> list:
    date_str = for_date.isoformat()
    picks = []
    for category in CATEGORIES:
        in_category = [q for q in QUEST_POOL if q["category"] == category]
        rng = random.Random(_seed_for(f"{date_str}|{category}"))
        shuffled = in_category[:]
        rng.shuffle(shuffled)
        picks.extend(shuffled[:QUESTS_PER_CATEGORY])
    return picks


def todays_boss_quest(for_date: date) -> dict:
    date_str = for_date.isoformat()
    rng = random.Random(_seed_for(f"{date_str}|boss"))
    shuffled = BOSS_POOL[:]
    rng.shuffle(shuffled)
    return shuffled[0]


def quest_by_id(quest_id: str) -> dict | None:
    """Look up a quest by id across the regular pool and the boss pool."""
    for q in QUEST_POOL:
        if q["id"] == quest_id:
            return q
    for q in BOSS_POOL:
        if q["id"] == quest_id:
            return q
    return None


def yesterday(d: date) -> date:
    return d - timedelta(days=1)
