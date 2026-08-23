// ═══════════════════════════════════════════════════════
//  AURA-PI Dashboard v2 — chat / voice / devices / camera
// ═══════════════════════════════════════════════════════

const socket = io({ transports: ["websocket", "polling"] });
const $  = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

let state = {
  devices: {},
  rooms: [],
  byRoom: {},
  models: [],
  currentModel: "",
  streamMsg: null,
  streamText: "",
  livePreview: null,
  voiceMode: false,
  recognition: null,
  voiceActive: false,
  voicePaused: false,    // paused while we wait for LLM / TTS
  selectedVoice: null,
  currentUtterance: null,
};

// ─── TAB SWITCHING ──────────────────────────────────────
$$(".tab").forEach(t => {
  t.addEventListener("click", () => {
    $$(".tab").forEach(x => x.classList.remove("active"));
    $$(".view").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $("view-" + t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "devices") renderDevices();
  });
});

// ─── SOCKET EVENTS ──────────────────────────────────────
socket.on("connect",    () => { log("connected", "success"); refreshStatus(); refreshDevices(); });
socket.on("disconnect", () => { log("disconnected", "error"); setPill("ollamaStatus", "⬤ OFFLINE", false); });

socket.on("status_update", (d) => {
  setPill("ollamaStatus", d.ollama ? "⬤ LLM ONLINE" : "⬤ LLM OFFLINE", d.ollama);
  state.currentModel = d.model || "";
  if (d.models) { state.models = d.models; renderModelSelect(); }
});

socket.on("thinking", (d) => {
  $("thinkingBar").classList.toggle("active", d.state);
  $("auraRing").classList.toggle("thinking", d.state);
  $("footerStatus").textContent = d.state ? "PROCESSING..." : "STANDING BY";
  if (state.voiceMode) setVoiceOrb(d.state ? "thinking" : (state.voiceActive ? "listening" : "standby"));
});

socket.on("token", (d) => {
  if (!state.streamMsg) {
    state.streamMsg = createMessage("AURA", "", "aura-msg");
    state.streamText = "";
  }
  state.streamText += d.token;
  state.streamMsg.querySelector(".msg-text").textContent = cleanStream(state.streamText);
  scrollChat();
});

socket.on("response_complete", (d) => {
  const text = d.spoken || d.text || "";

  // get or create the message element
  let msgEl = state.streamMsg;
  if (!msgEl) {
    // tokens were never received (non-streaming or lost) — create bubble now
    if (text) msgEl = createMessage("AURA", text, "aura-msg");
  } else {
    // streaming done — update the final clean text
    msgEl.querySelector(".msg-text").textContent = text || msgEl.querySelector(".msg-text").textContent;
  }

  // append action chips
  if (msgEl && d.actions && d.actions.length) {
    const tail = document.createElement("div");
    tail.style.marginTop = "6px";
    d.actions.forEach(a => {
      const chip = document.createElement("span");
      chip.className = "action-chip";
      chip.textContent = a.success ? (a.message || "✓ " + (a.device || "done")) : ("⚠ " + (a.error || "err"));
      tail.appendChild(chip);
    });
    msgEl.querySelector(".msg-text").appendChild(tail);
  }

  state.streamMsg = null;
  state.streamText = "";
  scrollChat();

  // TTS
  if (text && $("speakToggle") && $("speakToggle").checked) {
    speak(text, () => { if (state.voiceMode && state.voiceActive) resumeVoice(); });
  } else if (state.voiceMode && state.voiceActive) {
    resumeVoice();
  }
});

socket.on("devices_update", (byRoom) => {
  state.byRoom = byRoom;
  flattenDevices();
  renderDevices();
});

socket.on("action_executed", (a) => {
  log(a.success ? (a.message || "action ok") : ("err: " + a.error), a.success ? "action" : "error");
});

socket.on("camera_frame", (d) => showCameraFrame(d.frame, d.caption));
socket.on("log", (d) => log(d.text));

// ─── CHAT INPUT ──────────────────────────────────────────
$("sendBtn").addEventListener("click", sendChat);
$("chatInput").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });
$("dictBtn").addEventListener("click", toggleDictation);
$$(".qc-btn").forEach(b => b.addEventListener("click", () => {
  $("chatInput").value = b.dataset.cmd; sendChat();
}));
$("clearBtn").addEventListener("click", clearHistory);

function sendChat() {
  const input = $("chatInput");
  const text = input.value.trim();
  if (!text) return;
  createMessage("YOU", text, "user-msg");
  socket.emit("chat_message", { message: text });
  input.value = "";
}

function cleanStream(t) {
  // strip ACTION blocks (including multiline JSON)
  let out = t.replace(/ACTION:\s*\{[\s\S]*?\}/gi, "");
  // strip SPOKEN: prefix wherever it appears
  out = out.replace(/SPOKEN:\s*/gi, "");
  return out.trim();
}

function createMessage(label, text, cls) {
  const c = $("chatMessages");
  const div = document.createElement("div");
  div.className = "msg " + cls;
  div.innerHTML = `<span class="msg-label">${label}</span><div class="msg-text"></div>`;
  div.querySelector(".msg-text").textContent = text;
  c.appendChild(div);
  scrollChat();
  return div;
}
function scrollChat() { const c = $("chatMessages"); c.scrollTop = c.scrollHeight; }

// ─── DICTATION (one-shot speech-to-text in chat input) ─
function toggleDictation() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert("Browser doesn't support speech recognition. Use Chrome/Edge."); return; }
  const btn = $("dictBtn");
  if (btn.classList.contains("active")) { state.recognition && state.recognition.stop(); return; }
  const rec = new SR();
  rec.lang = "en-US"; rec.continuous = false; rec.interimResults = true;
  rec.onstart = () => { btn.classList.add("active"); log("🎤 listening...", "action"); };
  rec.onresult = (e) => {
    let txt = "";
    for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
    $("chatInput").value = txt;
  };
  rec.onend = () => { btn.classList.remove("active"); state.recognition = null;
    if ($("chatInput").value.trim()) sendChat();
  };
  rec.onerror = (e) => { btn.classList.remove("active"); log("mic error: " + e.error, "error");
    if (e.error === "not-allowed") alert("Microphone permission denied. Click the camera/lock icon in the address bar and allow microphone access.");
  };
  state.recognition = rec;
  rec.start();
}

// ─── VOICE CONVERSATION MODE ────────────────────────────
$("voiceStartBtn").addEventListener("click", startVoiceMode);
$("voiceStopBtn").addEventListener("click", stopVoiceMode);

function setVoiceOrb(mode) {
  const orb = $("voiceOrb");
  orb.classList.remove("listening", "thinking", "speaking");
  $("voiceState").textContent = mode.toUpperCase();
  if (mode === "listening") orb.classList.add("listening");
  else if (mode === "thinking") orb.classList.add("thinking");
  else if (mode === "speaking") orb.classList.add("speaking");
}

function startVoiceMode() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert("Voice mode requires Chrome or Edge."); return; }
  state.voiceMode = true;
  state.voiceActive = true;
  $("voiceStartBtn").disabled = true;
  $("voiceStopBtn").disabled = false;
  appendTranscript("vt-placeholder", "Listening... start talking.");
  startRecognition();
}

function startRecognition() {
  if (!state.voiceActive) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SR();
  rec.lang = "en-US";
  rec.continuous = $("continuousToggle").checked;
  rec.interimResults = true;
  let finalText = "";
  let partialNode = null;

  rec.onstart = () => { setVoiceOrb("listening"); };
  rec.onresult = (e) => {
    let interim = ""; finalText = "";
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript;
      else interim += r[0].transcript;
    }
    if (!partialNode) partialNode = appendTranscript("vt-partial", "");
    partialNode.textContent = "🎤 " + (finalText + interim);

    if (finalText && rec.continuous) {
      finalText = finalText.trim();
      processVoiceTurn(finalText);
      partialNode = null;
    }
  };
  rec.onerror = (e) => {
    log("voice error: " + e.error, "error");
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      alert("Microphone permission denied. Allow mic in your browser (lock icon → Site settings → Microphone → Allow), then reload.");
      stopVoiceMode();
    } else if (e.error === "network") {
      // Chrome's built-in STT needs Google servers
      appendTranscript("vt-aura", "⚠ Voice recognition needs internet (Chrome uses Google's servers). Try the CHAT tab with keyboard input, or type in the chat box and hit Enter.");
      stopVoiceMode();
    } else if (e.error === "no-speech") {
      // just restart silently
      if (state.voiceActive && !state.voicePaused) setTimeout(() => startRecognition(), 300);
    }
  };
  rec.onend = () => {
    // if non-continuous and we have something final, send it
    if (!rec.continuous && finalText.trim()) {
      processVoiceTurn(finalText.trim());
    } else if (state.voiceActive && !state.voicePaused) {
      // auto-restart
      setTimeout(() => startRecognition(), 200);
    }
  };
  state.recognition = rec;
  try { rec.start(); } catch (err) { log("rec start failed: " + err.message, "error"); }
}

function processVoiceTurn(text) {
  if (!text) return;
  state.voicePaused = true;
  try { state.recognition && state.recognition.stop(); } catch (e) {}
  appendTranscript("vt-user", "YOU: " + text);
  createMessage("YOU", "🎤 " + text, "user-msg");
  setVoiceOrb("thinking");
  // send via socket to use the streaming pipeline + actions
  socket.emit("chat_message", { message: text });
}

function resumeVoice() {
  if (!state.voiceActive) return;
  state.voicePaused = false;
  setTimeout(() => startRecognition(), 250);
}

function stopVoiceMode() {
  state.voiceMode = false;
  state.voiceActive = false;
  state.voicePaused = false;
  try { state.recognition && state.recognition.stop(); } catch (e) {}
  window.speechSynthesis.cancel();
  $("voiceStartBtn").disabled = false;
  $("voiceStopBtn").disabled = true;
  setVoiceOrb("standby");
}

function appendTranscript(cls, txt) {
  const c = $("voiceTranscript");
  // clear placeholder on first real msg
  const ph = c.querySelector(".vt-placeholder");
  if (ph && cls !== "vt-placeholder") ph.remove();
  const span = document.createElement("div");
  span.className = cls;
  span.textContent = txt;
  c.appendChild(span);
  c.scrollTop = c.scrollHeight;
  return span;
}

// ─── BROWSER TTS ───────────────────────────────────────
function loadVoices() {
  const voices = window.speechSynthesis.getVoices();
  const sel = $("voiceSelect");
  sel.innerHTML = "";
  voices.forEach(v => {
    const o = document.createElement("option");
    o.value = v.name;
    o.textContent = `${v.name} (${v.lang})`;
    sel.appendChild(o);
  });
  // prefer an english male / "David" / "Daniel" voice for Aura
  const pref = voices.find(v => /david|daniel|google.*uk.*male/i.test(v.name) && /en/i.test(v.lang))
            || voices.find(v => /en/i.test(v.lang));
  if (pref) { sel.value = pref.name; state.selectedVoice = pref; }
}
window.speechSynthesis.onvoiceschanged = loadVoices;
$("voiceSelect").addEventListener("change", e => {
  state.selectedVoice = window.speechSynthesis.getVoices().find(v => v.name === e.target.value);
});

function speak(text, done) {
  if (!text) { done && done(); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  if (state.selectedVoice) u.voice = state.selectedVoice;
  u.rate = 1.05; u.pitch = 1.0; u.volume = 1.0;
  u.onstart = () => { setVoiceOrb("speaking"); $("auraRing").classList.add("speaking"); $("ttsStatus").classList.add("online"); };
  u.onend = () => { $("auraRing").classList.remove("speaking"); $("ttsStatus").classList.remove("online");
    if (state.voiceMode && state.voiceActive) setVoiceOrb("listening");
    done && done();
  };
  u.onerror = () => done && done();
  state.currentUtterance = u;
  window.speechSynthesis.speak(u);
}

// ─── DEVICES TAB ───────────────────────────────────────
function flattenDevices() {
  state.devices = {};
  Object.values(state.byRoom || {}).forEach(r => r.devices.forEach(d => { state.devices[d.id] = d; }));
}

async function refreshDevices() {
  const r = await fetch("/api/devices"); const d = await r.json();
  state.byRoom = d.by_room; state.rooms = d.rooms; flattenDevices();
  renderDevices(); populateRoomSelects();
}

function renderDevices() {
  const c = $("roomsContainer");
  c.innerHTML = "";
  const entries = Object.entries(state.byRoom || {});
  if (!entries.length) { c.innerHTML = '<div style="color:var(--text-dim);padding:20px">No rooms.</div>'; return; }
  entries.forEach(([rid, room]) => {
    if (!room.devices.length && rid === "_unassigned") return;
    const sec = document.createElement("div");
    sec.className = "room-section";
    sec.innerHTML = `
      <div class="room-header">
        <div><span class="room-icon">${room.info.icon || "🏠"}</span><span class="room-title">${room.info.name.toUpperCase()}</span></div>
        <div class="room-count">${room.devices.length} device${room.devices.length !== 1 ? "s" : ""}</div>
      </div>
      <div class="device-grid"></div>`;
    const grid = sec.querySelector(".device-grid");
    room.devices.forEach(d => grid.appendChild(deviceCard(d)));
    c.appendChild(sec);
  });
}

function deviceCard(d) {
  const card = document.createElement("div");
  card.className = "device-card" + (d.state ? " on" : "");
  card.innerHTML = `
    <div class="dc-top">
      <div class="dc-icon">${d.icon || "🔌"}</div>
      <div class="dc-info">
        <div class="dc-name">${d.name.toUpperCase()}</div>
        <div class="dc-meta">${d.type.toUpperCase()} · GPIO ${d.gpio_pin}</div>
      </div>
      <div class="dc-toggle" title="Toggle"></div>
    </div>
    <div class="dc-slider">
      <input type="range" min="0" max="100" value="${d.intensity}" ${d.dimmable ? "" : "disabled"}>
      <span class="dc-pct">${d.intensity}%</span>
    </div>
    <div class="dc-actions">
      <button class="dc-btn" data-act="rename">Edit</button>
      <button class="dc-btn del" data-act="delete">Delete</button>
    </div>`;
  card.querySelector(".dc-toggle").addEventListener("click", () => {
    fetch(`/api/devices/${d.id}/toggle`, { method: "POST" });
  });
  const slider = card.querySelector("input[type=range]");
  const pct = card.querySelector(".dc-pct");
  slider.addEventListener("input", () => { pct.textContent = slider.value + "%"; });
  slider.addEventListener("change", () => {
    fetch(`/api/devices/${d.id}/set`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intensity: parseInt(slider.value) }),
    });
  });
  card.querySelector("[data-act=delete]").addEventListener("click", async () => {
    if (!confirm(`Delete ${d.name}?`)) return;
    await fetch(`/api/devices/${d.id}`, { method: "DELETE" });
  });
  card.querySelector("[data-act=rename]").addEventListener("click", async () => {
    const newName = prompt("New name:", d.name);
    if (!newName) return;
    await fetch(`/api/devices/${d.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName }),
    });
  });
  return card;
}

// ─── ADD DEVICE / ROOM ──────────────────────────────────
$("addDeviceBtn").addEventListener("click", () => { populateRoomSelects(); openModal("addDeviceModal"); });
$("addRoomBtn").addEventListener("click", () => openModal("addRoomModal"));
$$("[data-close]").forEach(b => b.addEventListener("click", e => closeModal(e.target.closest(".modal-backdrop").id)));
$$(".modal-backdrop").forEach(m => m.addEventListener("click", e => { if (e.target === m) closeModal(m.id); }));

$("ndSave").addEventListener("click", async () => {
  const payload = {
    name: $("ndName").value.trim(),
    type: $("ndType").value,
    room: $("ndRoom").value,
    icon: $("ndIcon").value.trim() || "💡",
    gpio_pin: parseInt($("ndPin").value),
    dimmable: $("ndDimmable").checked,
  };
  if (!payload.name) { alert("Name required"); return; }
  const r = await fetch("/api/devices/add", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json();
  if (data.success) { closeModal("addDeviceModal"); $("ndName").value = ""; log("Added " + payload.name, "action"); }
  else alert("Error: " + data.error);
});

$("nrSave").addEventListener("click", async () => {
  const payload = { name: $("nrName").value.trim(), icon: $("nrIcon").value.trim() || "🏠" };
  if (!payload.name) { alert("Name required"); return; }
  const r = await fetch("/api/rooms", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json();
  if (data.success) { closeModal("addRoomModal"); $("nrName").value = ""; refreshDevices(); }
  else alert("Error: " + data.error);
});

$("allOnBtn").addEventListener("click", () => socket.emit("chat_message", { message: "turn on all lights" }));
$("allOffBtn").addEventListener("click", () => socket.emit("chat_message", { message: "turn off all lights" }));

function populateRoomSelects() {
  const sel = $("ndRoom");
  sel.innerHTML = "";
  (state.rooms || []).forEach(r => {
    const o = document.createElement("option");
    o.value = r.id; o.textContent = `${r.icon || "🏠"} ${r.name}`;
    sel.appendChild(o);
  });
}

function openModal(id) { $(id).classList.add("open"); }
function closeModal(id) { $(id).classList.remove("open"); }

// ─── CAMERA TAB ────────────────────────────────────────
$("capBtn").addEventListener("click", async () => {
  log("📷 capturing...", "action");
  const r = await fetch("/api/camera/capture", { method: "POST" });
  const d = await r.json();
  if (d.success) {
    showCameraFrame(d.base64);
    $("camResultBody").textContent = "Analyzing image...";
    const ar = await fetch("/api/camera/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "Describe what you see in detail." }),
    });
    const ad = await ar.json();
    $("camResultBody").textContent = ad.description || ("Error: " + (ad.error || "unknown"));
    if (state.voiceMode || $("speakToggle")?.checked) speak(ad.description);
  } else {
    $("camResultBody").textContent = "Camera unavailable: " + (d.error || "unknown");
  }
});

$("livePrevBtn").addEventListener("click", () => {
  if (state.livePreview) {
    clearInterval(state.livePreview); state.livePreview = null;
    $("livePrevBtn").textContent = "▶ LIVE PREVIEW";
    return;
  }
  $("livePrevBtn").textContent = "⏹ STOP";
  state.livePreview = setInterval(async () => {
    const r = await fetch("/api/camera/preview"); const d = await r.json();
    if (d.success) showCameraFrame(d.frame);
  }, 350);
});

$("askImgBtn").addEventListener("click", async () => {
  const prompt = $("camPrompt").value.trim() || "What's in this image?";
  $("camResultBody").textContent = "Analyzing...";
  const r = await fetch("/api/camera/analyze", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  const d = await r.json();
  $("camResultBody").textContent = d.description || ("Error: " + (d.error || "unknown"));
});

function showCameraFrame(base64, caption = null) {
  const canvas = $("cameraCanvas");
  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // letterbox
    const r = Math.min(canvas.width / img.width, canvas.height / img.height);
    const w = img.width * r, h = img.height * r;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    if (caption) {
      ctx.fillStyle = "rgba(0,5,10,.78)"; ctx.fillRect(0, canvas.height - 38, canvas.width, 38);
      ctx.fillStyle = "#00d4ff"; ctx.font = "12px 'Share Tech Mono'";
      ctx.fillText(caption.substring(0, 90), 10, canvas.height - 16);
    }
  };
  img.src = "data:image/jpeg;base64," + base64;
  $("camOverlay").style.display = "none";
}

// ─── STATUS / MODEL SELECT ─────────────────────────────
async function refreshStatus() {
  try {
    const r = await fetch("/api/status"); const d = await r.json();
    setPill("ollamaStatus", d.ollama ? "⬤ LLM ONLINE" : "⬤ LLM OFFLINE", d.ollama);
    state.models = d.models || [];
    state.currentModel = d.current_model || "";
    renderModelSelect();
  } catch (e) { log("status err", "error"); }
}

function renderModelSelect() {
  const sel = $("modelSelect");
  sel.innerHTML = "";
  if (!state.models.length) {
    const o = document.createElement("option"); o.textContent = "NO MODELS"; sel.appendChild(o); return;
  }
  state.models.forEach(m => {
    const o = document.createElement("option"); o.value = m; o.textContent = m.toUpperCase();
    if (m === state.currentModel) o.selected = true;
    sel.appendChild(o);
  });
}
$("modelSelect").addEventListener("change", async e => {
  await fetch("/api/model/set", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: e.target.value }) });
  log("model → " + e.target.value, "action");
});

async function clearHistory() {
  await fetch("/api/clear_history", { method: "POST" });
  $("chatMessages").innerHTML = "";
  createMessage("AURA", "Memory cleared. Ready for a fresh conversation.", "system-msg");
  log("memory cleared", "action");
}

// ─── UTIL ───────────────────────────────────────────────
function setPill(id, txt, online = null) {
  const el = $(id); if (!el) return;
  el.textContent = txt;
  if (online === true)  el.classList.add("online");
  if (online === false) el.classList.remove("online");
}
function log(text, type = "") {
  const strip = $("logStrip");
  const s = document.createElement("span");
  s.className = type;
  s.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  strip.appendChild(s);
  // keep only the latest 8
  while (strip.children.length > 8) strip.removeChild(strip.firstChild);
}

// init
window.addEventListener("load", () => {
  log("dashboard online");
  loadVoices();
  setTimeout(loadVoices, 500);
  refreshStatus();
});
