"use strict";

// This file replaces the old loadState()/saveState() + direct localStorage
// writes. Every action (complete a quest, add a custom quest, reset,
// rename) now goes to the Flask API below, which persists to Postgres and
// hands back the freshly computed state; we just splice that state back
// into the DOM. Category filtering stays purely client-side since it
// doesn't need the server at all.

const toast = document.getElementById("toast");
const toastMsg = document.getElementById("toastMsg");
let toastTimer = null;

function showToast(msg) {
  toastMsg.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function markQuestDone(questId) {
  const card = document.querySelector(`[data-quest-id="${CSS.escape(questId)}"]`);
  if (!card) return;
  card.classList.add("done");
  const btn = card.querySelector(".quest-btn");
  if (!btn) return;
  btn.disabled = true;
  if (card.id === "bossCard") {
    btn.textContent = "\u2713 Challenge Complete";
    btn.classList.remove("boss-btn");
  } else {
    btn.textContent = "\u2713 Completed";
    btn.classList.remove("todo");
  }
  btn.classList.add("done-btn");
}

function applyHud(state) {
  document.getElementById("lvNum").textContent = state.level;
  document.getElementById("rankTag").textContent = state.rank;
  document.getElementById("xpFill").style.width = state.xp_pct + "%";
  document.getElementById("xpCaption").textContent = `${state.xp_into_level} / ${state.xp_needed} XP`;
  document.getElementById("streakNum").textContent = state.streak;
}

function applyBadges(state) {
  const row = document.getElementById("badgesRow");
  row.innerHTML = state.badges
    .map((b) => `<span class="badge-chip${b.unlocked ? " unlocked" : ""}">${b.label}</span>`)
    .join("");
}

async function completeQuest(questId) {
  try {
    const { state, message } = await postJSON(`/api/quest/complete/${encodeURIComponent(questId)}`);
    markQuestDone(questId);
    applyHud(state);
    applyBadges(state);
    showToast(message);
  } catch (err) {
    showToast(err.message || "Couldn't complete that quest.");
  }
}

document.getElementById("questGrid").addEventListener("click", (e) => {
  const btn = e.target.closest(".quest-btn.todo");
  if (!btn) return;
  const card = btn.closest(".quest-card");
  completeQuest(card.dataset.questId);
});

const bossCard = document.getElementById("bossCard");
bossCard.addEventListener("click", (e) => {
  const btn = e.target.closest(".quest-btn.boss-btn");
  if (!btn) return;
  completeQuest(bossCard.dataset.questId);
});

document.getElementById("filters").addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  document.querySelectorAll("#filters .chip").forEach((c) => c.classList.remove("active"));
  btn.classList.add("active");
  const filter = btn.dataset.filter;
  document.querySelectorAll("#questGrid .quest-card").forEach((card) => {
    card.classList.toggle("hidden", filter !== "All" && card.dataset.category !== filter);
  });
});

const addToggle = document.getElementById("addToggle");
const addForm = document.getElementById("addForm");
addToggle.addEventListener("click", () => {
  const open = addForm.classList.toggle("open");
  addToggle.setAttribute("aria-expanded", open ? "true" : "false");
  addToggle.textContent = open ? "\u2212 Close" : "+ Add a custom quest";
});

document.getElementById("addQuestBtn").addEventListener("click", async () => {
  const nameInput = document.getElementById("qName");
  const name = nameInput.value.trim();
  const category = document.getElementById("qCat").value;
  const xp = parseInt(document.getElementById("qXp").value, 10) || 15;
  if (!name) {
    nameInput.focus();
    return;
  }
  try {
    await postJSON("/api/quest/custom", { name, category, xp });
    showToast("Custom quest added!");
    // The new quest needs a DOM card too, so just reload - simplest correct
    // option given custom quests also have to be filterable by category.
    location.reload();
  } catch (err) {
    showToast(err.message || "Couldn't add that quest.");
  }
});

document.getElementById("playerName").addEventListener("change", (e) => {
  const name = e.target.value.trim() || "Player One";
  postJSON("/api/profile/name", { name }).catch(() => {});
});

document.getElementById("resetBtn").addEventListener("click", async () => {
  if (!confirm("Reset all FitQuest progress? This can't be undone.")) return;
  try {
    await postJSON("/api/reset");
    location.reload();
  } catch (err) {
    showToast(err.message || "Couldn't reset progress.");
  }
});
