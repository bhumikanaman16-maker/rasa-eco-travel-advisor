/**
 * EcoTravel Advisor – Frontend Application
 * Connects to Rasa REST channel at http://localhost:5005
 * Handles: chat, quick replies, GPS location, handover status
 */

"use strict";

// ── CONFIGURATION ───────────────────────────────────────────
const RASA_URL = (window.location.protocol === "file:" || window.location.port === "8080" || window.location.port === "5500")
  ? "http://127.0.0.1:5005/webhooks/rest/webhook"
  : (window.location.origin + "/webhooks/rest/webhook");
const BOT_SENDER_ID = "eco_travel_web_" + Date.now();

// ── STATE ────────────────────────────────────────────────────
let userLocation = null;   // { lat, lng, label }
let isWaiting = false;

// ── DOM REFERENCES ───────────────────────────────────────────
const chatMessages   = document.getElementById("chat-messages");
const quickReplies   = document.getElementById("quick-replies");
const userInput      = document.getElementById("user-input");
const sendBtn        = document.getElementById("send-btn");
const locationDisplay = document.getElementById("location-display");
const handoverCard   = document.getElementById("handover-status-card");

// ── INITIALISE ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  renderWelcomeMessage();
  bindEvents();
});

function renderWelcomeMessage() {
  addBotMessage(
    "Hello! 🌱 Welcome to EcoTravel Advisor.\n\n" +
    "I can help you:\n" +
    "  🗺️  Plan a sustainable trip\n" +
    "  🌍  Calculate your carbon footprint\n" +
    "  🏨  Find eco-friendly accommodation\n" +
    "  🚆  Compare sustainable transport\n" +
    "  🌿  Discover sustainable activities\n\n" +
    "How can I help you today?",
    [
      { title: "🌍 Plan a Trip",          payload: "/plan_trip" },
      { title: "🚆 Sustainable Transport", payload: "/ask_transport" },
      { title: "🏨 Eco Accommodation",     payload: "/ask_accommodation" },
      { title: "🌿 Activities",            payload: "/ask_activities" },
      { title: "🌍 Carbon Footprint",      payload: "/ask_carbon" },
      { title: "🌱 Carbon Offsets",        payload: "/ask_carbon_offset" },
    ]
  );
}

// ── EVENT BINDING ────────────────────────────────────────────
function bindEvents() {
  // Send on button click
  sendBtn.addEventListener("click", handleSend);

  // Send on Enter key
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Nav bar shortcut buttons
  bindNavButton("btn-plan-trip",   "/plan_trip",        "I want to plan a trip");
  bindNavButton("btn-carbon",      "/ask_carbon",       "Calculate my carbon footprint");
  bindNavButton("btn-offsets",     "/ask_carbon_offset","Recommend carbon offset programmes");
  bindNavButton("btn-hotels",      "/ask_accommodation","Recommend eco friendly hotels");
  bindNavButton("btn-flights",     "/ask_flights",      "Search for flight options");
  bindNavButton("btn-transport",   "/ask_transport",    "Recommend sustainable transport");

  // Location buttons
  document.getElementById("btn-use-location").addEventListener("click", requestGPSLocation);
  document.getElementById("btn-manual-location").addEventListener("click", toggleManualForm);
  document.getElementById("btn-set-manual-location").addEventListener("click", setManualLocation);
}

function bindNavButton(id, payload, displayText) {
  const btn = document.getElementById(id);
  if (btn) {
    btn.addEventListener("click", () => {
      addUserMessage(displayText);
      sendToRasa(payload, displayText);
    });
  }
}

// ── CHAT CORE ─────────────────────────────────────────────────
async function handleSend() {
  const text = userInput.value.trim();
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
        "⚠️ I'm having trouble connecting to the advisor server. " +
        "Please ensure the Rasa server is running on http://localhost:5005 " +
        "and the action server is running on http://localhost:5055.\n\n" +
        `Error: HTTP ${response.status}`
      );
      return;
    }

    const messages = await response.json();

    if (!messages || messages.length === 0) {
      addBotMessage(
        "I received your message but the response was empty. " +
        "Please try rephrasing your request."
      );
      return;
    }

    for (const msg of messages) {
      if (msg.text) {
        const buttons = msg.buttons || [];
        addBotMessage(msg.text, buttons);

        // Check for handover signal
        if (
          msg.text.includes("HUMAN ADVISOR HANDOVER") ||
          msg.text.includes("human travel advisor")
        ) {
          showHandoverStatus();
        }
      }

      // Image attachments (if any future expansion)
      if (msg.image) {
        addBotImage(msg.image);
      }
    }

  } catch (err) {
    removeTypingIndicator();

    if (err instanceof TypeError && err.message.includes("fetch")) {
      addBotMessage(
        "⚠️ Unable to connect to the EcoTravel Advisor server.\n\n" +
        "Please make sure:\n" +
        "  1. The Rasa server is running:\n" +
        "     rasa run --enable-api --cors \"*\"\n\n" +
        "  2. The action server is running:\n" +
        "     rasa run actions\n\n" +
        "Both should be running before using the web interface."
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

// ── MESSAGE RENDERING ────────────────────────────────────────
function addUserMessage(text) {
  const msg = createMessageEl("user");
  msg.querySelector(".bubble").textContent = text;
  chatMessages.appendChild(msg);
  scrollToBottom();
}

function addBotMessage(text, buttons = []) {
  const msg = createMessageEl("bot");
  msg.querySelector(".bubble").textContent = text;
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

  locationDisplay.textContent = "📡 Requesting location permission…";

  navigator.geolocation.getCurrentPosition(
    onLocationSuccess,
    onLocationError,
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
}

function onLocationSuccess(position) {
  const { latitude, longitude } = position.coords;

  // Reverse geocode using free Nominatim (no key required)
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
        "Unknown location";
      const country = data.address?.country || "";
      const label = country ? `${city}, ${country}` : city;

      userLocation = { lat: latitude, lng: longitude, label };
      locationDisplay.textContent = `📍 ${label}`;

      // Prepend location context to next chat message automatically
      addBotMessage(
        `📍 I've set your current location as: ${label}.\n` +
        "I'll use this as your origin when you ask to calculate carbon emissions " +
        "or plan a journey from your current location."
      );
    })
    .catch(() => {
      userLocation = { lat: latitude, lng: longitude, label: `${latitude.toFixed(3)}, ${longitude.toFixed(3)}` };
      locationDisplay.textContent = `📍 Coordinates: ${userLocation.label}`;
      addBotMessage(
        `📍 Your GPS coordinates have been recorded: ${userLocation.label}.\n` +
        "Unable to resolve city name — please describe your city in the chat."
      );
    });
}

function onLocationError(err) {
  const messages = {
    1: "Location permission was denied. Please enter your location manually using the button below.",
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
    `📍 I've set your location as: ${input}.\n` +
    "I'll use this as your origin for carbon calculations and journey planning."
  );
}
