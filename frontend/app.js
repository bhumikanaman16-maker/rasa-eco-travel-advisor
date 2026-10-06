/**
 * EcoTravel Advisor – Professional Frontend Application
 * Connects to Rasa REST channel at http://localhost:5005
 * Features: Rich Markdown Formatting, Live Trip Profile Tracker,
 * Dynamic Quick Replies, Geolocation Hub, and Handover Dossier
 */

"use strict";

// ── CONFIGURATION ───────────────────────────────────────────
const RASA_URL = (window.location.protocol === "file:" || window.location.port === "8080" || window.location.port === "5500")
  ? "http://127.0.0.1:5005/webhooks/rest/webhook"
  : (window.location.origin + "/webhooks/rest/webhook");

let BOT_SENDER_ID = "eco_travel_web_" + Date.now();

// ── STATE ────────────────────────────────────────────────────
let userLocation = null;   // { lat, lng, label }
let isWaiting = false;
let tripProfile = {
  destination: null,
  duration: null,
  party: null,
  style: null,
  budget: null,
  sustainability: "High"
};

// ── DOM REFERENCES ───────────────────────────────────────────
const chatMessages    = document.getElementById("chat-messages");
const quickReplies    = document.getElementById("quick-replies");
const userInput       = document.getElementById("user-input");
const sendBtn         = document.getElementById("send-btn");
const locationDisplay = document.getElementById("location-display");
const handoverCard    = document.getElementById("handover-status-card");

// ── INITIALISE ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  renderWelcomeMessage();
  bindEvents();
});

function renderWelcomeMessage() {
  addBotMessage(
    "Hello! 🌱 Welcome to **EcoTravel Advisor** — your professional sustainable journey planner and eco-travel intelligence companion.\n\n" +
    "I can help you:\n" +
    "  • 🌍 **Plan a bespoke sustainable trip** tailored to your pace & style\n" +
    "  • 🗓️ **Generate day-by-day low-carbon itineraries** (morning, afternoon, evening)\n" +
    "  • 🥗 **Discover farm-to-table & zero-waste dining**\n" +
    "  • 🎒 **Check zero-waste packing lists & eco tips**\n" +
    "  • 🚆 **Compare transport modes & flight emissions**\n" +
    "  • 🏨 **Find certified green hotels & eco-lodges**\n" +
    "  • 📊 **Calculate live carbon footprints** with Climatiq\n\n" +
    "How can I assist your sustainable travels today?",
    [
      { title: "🌍 Plan a Trip",          payload: "/plan_trip" },
      { title: "🗓️ Custom Itinerary",     payload: "/ask_itinerary" },
      { title: "🥗 Green Dining Guide",    payload: "/ask_dining" },
      { title: "🎒 Zero-Waste Packing",   payload: "/ask_packing_tips" },
      { title: "🚆 Transport Compare",    payload: "/ask_transport" },
      { title: "🏨 Eco Accommodation",    payload: "/ask_accommodation" },
      { title: "📊 Carbon Footprint",      payload: "/ask_carbon" },
      { title: "🌱 Verified Offsets",     payload: "/ask_carbon_offset" },
      { title: "💡 Eco Travel Tips",      payload: "/ask_eco_tips" },
    ]
  );
}

// ── EVENT BINDING ────────────────────────────────────────────
function bindEvents() {
  // Send on button click
  sendBtn.addEventListener("click", () => handleSend());

  // Send on Enter key
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Sidebar shortcut buttons
  bindNavButton("btn-plan-trip",   "/plan_trip",         "I want to plan a sustainable trip");
  bindNavButton("btn-itinerary",   "/ask_itinerary",     "Generate a day-by-day sustainable itinerary");
  bindNavButton("btn-dining",      "/ask_dining",        "Recommend green and farm-to-table dining");
  bindNavButton("btn-packing",     "/ask_packing_tips",  "Give me a zero-waste packing checklist");
  bindNavButton("btn-transport",   "/ask_transport",     "Recommend sustainable transport options");
  bindNavButton("btn-hotels",      "/ask_accommodation", "Recommend eco friendly hotels");
  bindNavButton("btn-activities",  "/ask_activities",    "Recommend sustainable activities");
  bindNavButton("btn-carbon",      "/ask_carbon",        "Calculate my carbon footprint");
  bindNavButton("btn-offsets",     "/ask_carbon_offset", "Recommend verified carbon offset standards");
  bindNavButton("btn-eco-tips",    "/ask_eco_tips",      "Give me sustainable travel tips");

  // Top Bar New Trip button
  const newTripBtn = document.getElementById("btn-new-trip");
  if (newTripBtn) {
    newTripBtn.addEventListener("click", resetConsultation);
  }

  // Suggestion prompt chips
  document.querySelectorAll(".prompt-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt") || chip.textContent;
      userInput.value = prompt;
      handleSend();
    });
  });

  // Location buttons
  const useLocBtn = document.getElementById("btn-use-location");
  if (useLocBtn) useLocBtn.addEventListener("click", requestGPSLocation);

  const manualLocBtn = document.getElementById("btn-manual-location");
  if (manualLocBtn) manualLocBtn.addEventListener("click", toggleManualForm);

  const setManualBtn = document.getElementById("btn-set-manual-location");
  if (setManualBtn) setManualBtn.addEventListener("click", setManualLocation);
}

function bindNavButton(id, payload, displayText) {
  const btn = document.getElementById(id);
  if (btn) {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sidebar-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      addUserMessage(displayText);
      sendToRasa(payload, displayText);
    });
  }
}

function resetConsultation() {
  BOT_SENDER_ID = "eco_travel_web_" + Date.now();
  chatMessages.innerHTML = "";
  clearQuickReplies();
  tripProfile = {
    destination: null,
    duration: null,
    party: null,
    style: null,
    budget: null,
    sustainability: "High"
  };
  refreshProfileWidget();
  renderWelcomeMessage();
}

// ── CHAT CORE ─────────────────────────────────────────────────
async function handleSend(customText = null) {
  const text = (customText || userInput.value).trim();
  if (!text || isWaiting) return;

  userInput.value = "";
  clearQuickReplies();
  addUserMessage(text);
  await sendToRasa(text, text);
}

async function sendToRasa(payload, displayText) {
  setWaiting(true);
  showTypingIndicator();

  try {
    const response = await fetch(RASA_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sender: BOT_SENDER_ID,
        message: payload,
      }),
    });

    removeTypingIndicator();

    if (!response.ok) {
      addBotMessage(
        "⚠️ **Advisor Server Offline**\n\n" +
        "Please make sure the Rasa server is active on `http://localhost:5005` and custom actions on `http://localhost:5055`.\n\n" +
        `Error: HTTP ${response.status}`
      );
      return;
    }

    const messages = await response.json();

    if (!messages || messages.length === 0) {
      addBotMessage(
        "I received your message. Could you please specify your preferred destination, duration, or travel style?"
      );
      return;
    }

    for (const msg of messages) {
      if (msg.text) {
        const buttons = msg.buttons || [];
        addBotMessage(msg.text, buttons);

        // Update live trip profile widget from message contents
        parseAndUpdateProfile(msg.text);

        // Check for handover signal
        if (
          msg.text.includes("HUMAN ADVISOR") ||
          msg.text.includes("human travel advisor") ||
          msg.text.includes("ESCALATION DOSSIER")
        ) {
          showHandoverStatus();
        }
      }

      if (msg.image) {
        addBotImage(msg.image);
      }
    }

  } catch (err) {
    removeTypingIndicator();

    if (err instanceof TypeError && err.message.includes("fetch")) {
      addBotMessage(
        "⚠️ **EcoTravel Server Connection Notice**\n\n" +
        "The web interface cannot reach the Rasa Core backend.\n\n" +
        "To start the full system, run:\n" +
        "```bash\npython main.py\n```\n" +
        "Or start services separately on ports 5005 & 5055."
      );
    } else {
      addBotMessage(
        "An unexpected error occurred. Please try again."
      );
      console.error("EcoTravel Advisor error:", err);
    }
  } finally {
    setWaiting(false);
  }
}

// ── RICH MARKDOWN FORMATTER ─────────────────────────────────
function formatMarkdown(text) {
  if (!text) return "";

  // 1. Escape HTML
  let str = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // 2. Bold: **text** -> <strong>text</strong>
  str = str.replace(/\*\*(.*?)\*\*/g, '<strong class="md-bold">$1</strong>');

  // 3. Section dividers: ════ or ────
  str = str.replace(/[═─]{4,}/g, '<div class="md-divider"></div>');

  // 4. Day & Topic Headers: 📌 DAY 1: ... or ✨ MASTER ... or 📊 ECO ...
  str = str.replace(/(📌 DAY \d+: [^\n]+)/g, '<div class="md-day-title">$1</div>');
  str = str.replace(/(✨ MASTER SUSTAINABLE TRIP PLAN:[^\n]+)/g, '<div class="md-master-title">$1</div>');
  str = str.replace(/(📊 ECO IMPACT SCORECARD:)/g, '<div class="md-section-title">$1</div>');
  str = str.replace(/(🗺️ DAY-BY-DAY ITINERARY PREVIEW[^\n]*:)/g, '<div class="md-section-title">$1</div>');
  str = str.replace(/(🥗 SUSTAINABLE & FARM-TO-TABLE DINING:[^\n]+)/g, '<div class="md-master-title">$1</div>');
  str = str.replace(/(🎒 ZERO-WASTE ECO-PACKING CHECKLIST:[^\n]+)/g, '<div class="md-master-title">$1</div>');

  // 5. Bullet items: "  • " or "  - "
  str = str.replace(/^[ \t]*•[ \t]+([^\n]+)/gm, '<div class="md-bullet"><span class="bullet-dot">•</span> <span>$1</span></div>');

  // 6. Numbered sub-items: "  1. " or "  2. "
  str = str.replace(/^[ \t]*(\d+)\.[ \t]+([^\n]+)/gm, '<div class="md-numbered"><span class="num-badge">$1</span> <span>$2</span></div>');

  // 7. Green/Amber badges
  str = str.replace(/(🟢 Lower emissions|🟢 [0-9.]+\/10)/g, '<span class="eco-badge badge-green">$1</span>');
  str = str.replace(/(🟡 Moderate emissions)/g, '<span class="eco-badge badge-amber">$1</span>');
  str = str.replace(/(🔴 Higher emissions)/g, '<span class="eco-badge badge-red">$1</span>');

  // 8. Line breaks
  str = str.replace(/\n/g, "<br>");

  return str;
}

// ── MESSAGE RENDERING ────────────────────────────────────────
function addUserMessage(text) {
  const msg = createMessageEl("user");
  msg.querySelector(".bubble").textContent = text;
  chatMessages.appendChild(msg);
  scrollToBottom();
}

function addBotMessage(text, buttons = []) {
  const msg = createMessageEl("bot");
  msg.querySelector(".bubble").innerHTML = formatMarkdown(text);
  chatMessages.appendChild(msg);
  scrollToBottom();

  if (buttons && buttons.length > 0) {
    renderQuickReplies(buttons);
  }
}

function addBotImage(url) {
  const wrapper = document.createElement("div");
  wrapper.className = "message bot";
  const img = document.createElement("img");
  img.src = url;
  img.alt = "Image from EcoTravel Advisor";
  img.style.cssText = "max-width:100%;border-radius:12px;margin-top:8px;";
  wrapper.appendChild(img);
  chatMessages.appendChild(wrapper);
  scrollToBottom();
}

function createMessageEl(role) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;
  wrapper.setAttribute("role", "listitem");

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "bot" ? "🌱" : "👤";

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);
  return wrapper;
}

function renderQuickReplies(buttons) {
  clearQuickReplies();
  buttons.forEach(btn => {
    const chip = document.createElement("button");
    chip.className = "quick-reply-chip";
    chip.textContent = btn.title;
    chip.setAttribute("aria-label", `Quick reply: ${btn.title}`);
    chip.addEventListener("click", () => {
      clearQuickReplies();
      addUserMessage(btn.title);
      sendToRasa(btn.payload || btn.title, btn.title);
    });
    quickReplies.appendChild(chip);
  });
}

function clearQuickReplies() {
  quickReplies.innerHTML = "";
}

// ── LIVE TRIP PROFILE TRACKER ───────────────────────────────
function parseAndUpdateProfile(text) {
  if (!text) return;

  const destMatch = text.match(/Destination:\s*([^\n\r,]+)/i);
  if (destMatch) tripProfile.destination = destMatch[1].trim();

  const durMatch = text.match(/Duration:\s*([^\n\r,]+)/i);
  if (durMatch) tripProfile.duration = durMatch[1].trim();

  const partyMatch = text.match(/Travel Party:\s*([^\n\r,]+)/i);
  if (partyMatch) tripProfile.party = partyMatch[1].trim();

  const styleMatch = text.match(/Trip Style[^\n\r:]*:\s*([^\n\r,]+)/i);
  if (styleMatch) tripProfile.style = styleMatch[1].trim();

  const budgetMatch = text.match(/Budget[^\n\r:]*:\s*([^\n\r,]+)/i);
  if (budgetMatch) tripProfile.budget = budgetMatch[1].trim();

  const ecoMatch = text.match(/Sustainability[^\n\r:]*:\s*([^\n\r,]+)/i);
  if (ecoMatch) tripProfile.sustainability = ecoMatch[1].trim();

  refreshProfileWidget();
}

function refreshProfileWidget() {
  const dDest = document.getElementById("prof-dest");
  const dDur  = document.getElementById("prof-dur");
  const dPart = document.getElementById("prof-party");
  const dSty  = document.getElementById("prof-style");
  const dBud  = document.getElementById("prof-budget");
  const dEco  = document.getElementById("prof-eco");
  const badge = document.getElementById("profile-status-badge");

  if (dDest) dDest.textContent = tripProfile.destination || "Not set";
  if (dDur)  dDur.textContent  = tripProfile.duration || "Not set";
  if (dPart) dPart.textContent = tripProfile.party || "Not set";
  if (dSty)  dSty.textContent  = tripProfile.style || "Not set";
  if (dBud)  dBud.textContent  = tripProfile.budget || "Not set";
  if (dEco)  dEco.textContent  = tripProfile.sustainability || "High";

  if (badge) {
    if (tripProfile.destination && tripProfile.duration) {
      badge.textContent = "Plan Active";
      badge.className = "dock-card-tag tag-live";
    } else {
      badge.textContent = "In Progress";
      badge.className = "dock-card-tag";
    }
  }
}

// ── TYPING INDICATOR ─────────────────────────────────────────
function showTypingIndicator() {
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  indicator.id = "typing-indicator";

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = "🌱";

  const dots = document.createElement("div");
  dots.className = "typing-dots";
  dots.setAttribute("aria-label", "Advisor is typing");
  for (let i = 0; i < 3; i++) {
    dots.appendChild(document.createElement("span"));
  }

  indicator.appendChild(avatar);
  indicator.appendChild(dots);
  chatMessages.appendChild(indicator);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

// ── UTILITIES ─────────────────────────────────────────────────
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setWaiting(state) {
  isWaiting = state;
  sendBtn.disabled = state;
  userInput.disabled = state;
}

function showHandoverStatus() {
  handoverCard.classList.remove("hidden");
  handoverCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ── LOCATION ──────────────────────────────────────────────────
function requestGPSLocation() {
  if (!navigator.geolocation) {
    locationDisplay.textContent =
      "Geolocation is not supported by your browser. Please enter your location manually.";
    return;
  }

  locationDisplay.textContent = "📡 Requesting GPS coordinates…";

  navigator.geolocation.getCurrentPosition(
    onLocationSuccess,
    onLocationError,
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
}

function onLocationSuccess(position) {
  const { latitude, longitude } = position.coords;

  fetch(
    `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
    { headers: { "Accept-Language": "en" } }
  )
    .then(r => r.json())
    .then(data => {
      const city =
        data.address?.city ||
        data.address?.town ||
        data.address?.village ||
        data.address?.county ||
        "Current Location";
      const country = data.address?.country || "";
      const label = country ? `${city}, ${country}` : city;

      userLocation = { lat: latitude, lng: longitude, label };
      locationDisplay.textContent = `📍 ${label}`;

      addBotMessage(
        `📍 I've recorded your starting location as: **${label}**.\n\n` +
        "I'll automatically use this as your origin for carbon calculations and low-carbon transport routing."
      );
    })
    .catch(() => {
      userLocation = { lat: latitude, lng: longitude, label: `${latitude.toFixed(3)}, ${longitude.toFixed(3)}` };
      locationDisplay.textContent = `📍 Coordinates: ${userLocation.label}`;
      addBotMessage(
        `📍 Your GPS coordinates have been recorded: ${userLocation.label}.\n` +
        "Please feel free to specify your departure city name directly in the chat."
      );
    });
}

function onLocationError(err) {
  const messages = {
    1: "Location permission was denied. Please enter your location manually.",
    2: "Your location could not be determined. Please enter it manually.",
    3: "Location request timed out. Please enter your location manually.",
  };
  locationDisplay.textContent =
    "⚠️ " + (messages[err.code] || "Location unavailable.");
}

function toggleManualForm() {
  const form = document.getElementById("manual-location-form");
  form.classList.toggle("hidden");
  if (!form.classList.contains("hidden")) {
    document.getElementById("manual-location-input").focus();
  }
}

function setManualLocation() {
  const input = document.getElementById("manual-location-input").value.trim();
  if (!input) return;

  userLocation = { label: input };
  locationDisplay.textContent = `📍 ${input}`;
  document.getElementById("manual-location-form").classList.add("hidden");

  addBotMessage(
    `📍 I've set your origin location as: **${input}**.\n\n` +
    "I'll use this for your route carbon calculations and sustainable rail/flight options."
  );
}
