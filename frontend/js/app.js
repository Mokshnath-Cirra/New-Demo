/* AURA Predictive AI - dashboard controller */
const SENSORS = [
  { key: "air_temperature", label: "Air Temperature", unit: "K", min: 295, max: 305, step: 0.1, base: 300 },
  { key: "process_temperature", label: "Process Temperature", unit: "K", min: 305, max: 315, step: 0.1, base: 310 },
  { key: "rotational_speed", label: "Rotational Speed", unit: "RPM", min: 1100, max: 2900, step: 10, base: 1500 },
  { key: "torque", label: "Torque Force", unit: "Nm", min: 3, max: 80, step: 0.1, base: 40 },
  { key: "tool_wear", label: "Tool Wear Duration", unit: "Mins", min: 0, max: 260, step: 1, base: 30 },
];
// Simulated live readings per machine (air K, process K, rpm, torque Nm, wear min)
const LIVE_BASE = [[298.8, 309.1, 1550, 42, 12], [299.4, 309.8, 1480, 38, 25], [300.2, 310.4, 1420, 44, 60], [299.9, 310.0, 1510, 36, 18]];
const STREAM_INTERVAL_MS = 1500;
const LIVE_DRIFT = { temp: 0.15, rpm: 4, torque: 0.3 };   // max random step per tick
const STATUS_CLASS = { HEALTHY: "healthy", WARNING: "warning", CRITICAL: "critical" };
const STATUS_TEXT = { HEALTHY: "NORMAL", WARNING: "ELEVATED", CRITICAL: "HIGH RISK" };
const BANNERS = {
  HEALTHY: ["Parameters Normal", "Machine operating safety within certified thresholds."],
  WARNING: ["Inspection Advised", "Elevated failure probability detected from parameters."],
  CRITICAL: ["Intervention Required", "High failure probability calculated from parameters."],
};
const INFERENCE = { HEALTHY: "Stable", WARNING: "Elevated", CRITICAL: "Critical" };
const BANNER_ICON = {
  HEALTHY: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  WARNING: '<path d="M12 4l9 16H3zM12 10v4M12 17v.5"/>',
  CRITICAL: '<path d="M12 4l9 16H3zM12 10v4M12 17v.5"/>',
};

const state = { assets: [], assetId: null, values: {}, live: false, sound: true, gauge: null, lastResult: null };
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const badge = (code) => `<span class="badge ${STATUS_CLASS[code] || ""}">${code === "CRITICAL" ? "High Risk" : code === "WARNING" ? "Elevated" : "Healthy"}</span>`;
const currentAsset = () => state.assets.find((a) => a.id === state.assetId);

function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`; el.textContent = message;
  $("#toasts").append(el); setTimeout(() => el.remove(), 4500);
}
function beep() {   // short alert tone for high-risk results
  if (!state.sound || !window.AudioContext) return;
  const ctx = new AudioContext(), osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.frequency.value = 660; gain.gain.value = 0.05;
  osc.connect(gain).connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + 0.25);
}

/* ---------- navigation ---------- */
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "fleet") loadFleet();
  if (name === "history") loadHistory();
  if (name === "roi") loadRoi();
}
async function updateCounts() {
  $("#fleetCount").textContent = `(${state.assets.length})`;
  try { $("#historyCount").textContent = `(${(await API.history(200)).length})`; } catch (err) { /* shown elsewhere */ }
}

/* ---------- sensor controls (slider and number box stay in sync) ---------- */
function buildSensors() {
  $("#sensorList").innerHTML = SENSORS.map((s) => `
    <div class="sensor">
      <div class="sensor-top"><span>${s.label}</span>
        <span class="pill"><input type="number" id="num-${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" aria-label="${s.label}"><em>${s.unit}</em></span></div>
      <input type="range" id="rng-${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" aria-label="${s.label} slider">
    </div>`).join("");
  SENSORS.forEach((s) => {
    const num = $(`#num-${s.key}`), rng = $(`#rng-${s.key}`);
    rng.addEventListener("input", () => setSensor(s, rng.value));
    num.addEventListener("input", () => { if (num.value !== "") { rng.value = num.value; state.values[s.key] = Number(num.value); } });
    num.addEventListener("blur", () => setSensor(s, num.value === "" ? s.base : num.value));   // clamp on blur
  });
  calibrate(false);
}
function setSensor(sensor, raw) {
  const v = clamp(Number(raw), sensor.min, sensor.max);
  const value = Number.isFinite(v) ? Number(v.toFixed(1)) : sensor.base;
  state.values[sensor.key] = value;
  $(`#num-${sensor.key}`).value = value; $(`#rng-${sensor.key}`).value = value;
}
function applyReadings(row) { SENSORS.forEach((s, i) => setSensor(s, row[i])); }
function calibrate(notify = true) {
  const asset = currentAsset();
  if (state.live && asset) applyReadings(LIVE_BASE[state.assets.indexOf(asset) % LIVE_BASE.length]);
  else applyReadings(SENSORS.map((s) => s.base));
  $("#qualityType").value = "M";
  if (notify) toast("Sensors reset to baseline readings.");
}

/* ---------- evaluation ---------- */
async function evaluate({ persist = true } = {}) {
  const btn = $("#evalBtn"), label = btn.querySelector("span");
  btn.disabled = true; label.textContent = "Evaluating...";
  try {
    const result = await API.predict({ type: $("#qualityType").value, ...state.values, asset_id: state.assetId, persist });
    state.lastResult = result; renderResult(result);
    if (result.status_code === "CRITICAL" && persist) beep();
    if (persist) { loadAssets(); }
  } catch (err) { toast(err.message, "error"); }
  finally { btn.disabled = false; label.textContent = "Evaluate Risk"; }
}

function renderResult(r) {
  const cls = STATUS_CLASS[r.status_code], [title, text] = BANNERS[r.status_code], asset = currentAsset();
  const eff = $("#effValue"); eff.textContent = `${r.efficiency_percent}%`;
  $("#rulValue").innerHTML = `${Math.round(r.rul_hours)} <small>hrs</small>`;
  const health = $("#healthText"); health.textContent = STATUS_TEXT[r.status_code]; health.className = `big status ${cls}`;
  $("#engineNote").textContent = r.engine === "ml" ? "Physics & Model Analysis" : "Physics rules only (model unavailable)";
  const top3 = [...r.stress_factors].sort((a, b) => b.value - a.value).slice(0, 3);
  const p = r.physics;
  $("#diagBody").className = "";
  $("#diagBody").innerHTML = `
    <div class="banner ${cls}"><svg viewBox="0 0 24 24">${BANNER_ICON[r.status_code]}</svg><div><b>${title}</b><span>${text}</span></div></div>
    <div class="panel gauge-row"><div class="gauge" id="riskGauge"></div><div class="kv">
      <div>Selected Unit <b>${esc(asset ? asset.tag : "MANUAL")}</b></div>
      <div>Model Inference <b class="${cls}">${INFERENCE[r.status_code]}</b></div>
      <div>Temp Delta (&Delta;T) <b>${p.temperature_delta_k} K</b></div></div></div>
    <div class="panel"><div class="note" style="margin-top:0"><b>${esc(r.primary_failure_mode || "No failure mode detected")}</b>${esc(r.diagnosis.root_cause)}</div>
      <div class="note"><b>Recommended action</b>${esc(r.diagnosis.recommended_action)}</div>
      <p class="cap" style="margin-top:10px">Power ${Math.round(p.mechanical_power_watts)} W &middot; Overstrain index ${Math.round(p.overstrain_index)} &middot; ${r.latency_ms} ms</p></div>
    <div class="panel"><h4>Stress Factor Breakdown</h4>${top3.map((s) => `
      <div class="bar"><div class="bar-top"><span>${esc(s.label)}</span><b>${s.value.toFixed(0)}%</b></div>
      <div class="bar-track"><div class="bar-fill ${s.value >= 70 ? "high" : ""}" style="width:${s.value}%"></div></div></div>`).join("")}</div>
    <div class="panel"><h4>Live Telemetry Stream</h4><div class="chart-wrap"><canvas id="telemetryChart" aria-label="Live telemetry stream"></canvas></div></div>`;
  state.gauge = Gauge.mount($("#riskGauge")); state.gauge.set(r.risk_percent, cls);
  TelemetryChart.attach($("#telemetryChart"));
}

/* ---------- machines & connection ---------- */
function refreshLinkUI() {
  const asset = currentAsset(), btn = $("#connectBtn"), on = Boolean(asset && asset.connected);
  btn.textContent = on ? "Connected (Live)" : "Connect Machine";
  btn.classList.toggle("live", on);
  const anyOnline = state.assets.some((a) => a.connected);
  $("#statusPill").classList.toggle("online", anyOnline);
  $("#statusText").textContent = anyOnline ? "Machine Online (IoT)" : "Standby Mode";
  $("#sensorSub").textContent = on && state.live ? "Live feed synchronized from machine" : "Manual override sliders";
}
async function loadAssets() {
  try { state.assets = await API.assets(); } catch (err) { toast(err.message, "error"); return; }
  const sel = $("#machineSelect");
  sel.innerHTML = state.assets.map((a) => `<option value="${a.id}">${esc(a.name)} (${esc(a.tag)})</option>`).join("");
  if (state.assetId == null && state.assets.length) state.assetId = state.assets[0].id;
  if (state.assetId != null) { sel.value = state.assetId; syncMachineFields(); }
  refreshLinkUI(); updateCounts();
}
function syncMachineFields() {
  const a = currentAsset(); if (!a) return;
  $("#ipInput").value = a.ip_address; $("#protoSelect").value = a.protocol;
}
function selectMachine(id) {
  state.assetId = id; state.live = Boolean(currentAsset()?.connected);
  syncMachineFields(); calibrate(false); refreshLinkUI();
}
async function connectMachine() {
  const btn = $("#connectBtn"); btn.disabled = true; btn.textContent = "Connecting...";
  try {
    const res = await API.connect(state.assetId, { ip_address: $("#ipInput").value.trim(), protocol: $("#protoSelect").value });
    $("#connectText").textContent = `${res.message} Handshake ${res.handshake_ms} ms${res.simulated ? " (simulation mode - see README to link real hardware)" : ""}.`;
    $("#connectModal").hidden = false;
    state.live = true; await loadAssets(); calibrate(false); refreshLinkUI();
  } catch (err) { toast(err.status === 422 ? "Enter a valid IPv4 or IPv6 address." : err.message, "error"); refreshLinkUI(); }
  finally { btn.disabled = false; }
}

/* ---------- fleet / history / ROI ---------- */
async function loadFleet() {
  try {
    const [s, assets] = await Promise.all([API.summary(), API.assets()]);
    $("#fleetStats").innerHTML = [["Machines connected", `${s.connected_assets}/${s.total_assets}`, ""], ["Healthy", s.healthy, ""],
      ["Elevated", s.warning, ""], ["High risk", s.critical, ""], ["Fleet health", `${s.fleet_health_score}%`, `average risk ${s.average_risk_percent}%`]]
      .map(([l, v, n]) => `<div class="stat"><span>${l}</span><strong>${v}</strong><small>${n}</small></div>`).join("");
    $("#fleetGrid").innerHTML = assets.map((a) => `
      <article class="machine ${STATUS_CLASS[a.status] || ""}">
        <header><div><h3>${esc(a.name)}</h3><p class="meta">${esc(a.tag)} &middot; ${esc(a.asset_type)}</p></div>${badge(a.status)}</header>
        <p class="risk">${a.last_risk_percent.toFixed(1)}<small class="cap"> % risk</small></p>
        <p class="meta">${esc(a.protocol)} &middot; ${esc(a.ip_address)} &middot; ${a.connected ? "linked" : "not linked"}</p>
        <button class="outline" type="button" data-diagnose="${a.id}">Diagnose</button></article>`).join("") || '<p class="empty">No machines registered yet.</p>';
  } catch (err) { toast(err.message, "error"); }
}
async function loadHistory() {
  try {
    const rows = await API.history(50), today = new Date().toDateString();
    $("#historyRows").innerHTML = rows.map((r) => {
      const d = new Date(r.timestamp), when = d.toDateString() === today ? d.toLocaleTimeString() : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
      return `<tr><td>${esc(when)}</td><td>${esc(r.equipment_tag)}</td><td>${r.risk_percent.toFixed(0)}%</td><td>${badge(r.status)}</td></tr>`;
    }).join("") || '<tr><td colspan="4" class="empty">No evaluations yet. Run one from Single Unit Diagnostics.</td></tr>';
  } catch (err) { toast(err.message, "error"); }
}
async function loadRoi() {
  try {
    const r = await API.roi(), a = r.assumptions;
    $("#roiRows").innerHTML = [
      ["Average Unplanned Downtime Loss / Hour:", money(a.downtime_cost_per_hour_usd), ""],
      ["Prevented Failures This Month:", `${r.prevented_failures} ${r.prevented_failures === 1 ? "Incident" : "Incidents"}`, "good"],
      ["Estimated Equipment Repair Cost Saved:", money(r.repair_cost_saved_usd), "gold"],
      ["Overall Production Efficiency Gain:", `+${r.efficiency_gain_percent}%`, "good"],
    ].map(([l, v, c]) => `<div><dt>${l}</dt><dd class="${c}">${v}</dd></div>`).join("");
    $("#roiNotes").innerHTML = [
      "Each high-risk evaluation in the last 30 days counts as one failure caught early and fixed in a planned stop.",
      `Repair saving per failure = ${money(a.unplanned_repair_cost_usd)} unplanned minus ${money(a.planned_repair_cost_usd)} planned.`,
      `Efficiency gain = downtime hours avoided as a share of ${a.scheduled_hours_per_month} scheduled hours per machine per month.`,
      "Edit these business inputs in your .env file to match your plant.",
    ].map((t) => `<li>${esc(t)}</li>`).join("");
  } catch (err) { toast(err.message, "error"); }
}

/* ---------- live telemetry (simulated) ---------- */
function startStream() {
  setInterval(() => {
    if (state.live) {   // machine feed drifts slightly; sliders follow it
      const d = (m) => (Math.random() * 2 - 1) * m;
      setSensor(SENSORS[0], state.values.air_temperature + d(LIVE_DRIFT.temp));
      setSensor(SENSORS[1], state.values.process_temperature + d(LIVE_DRIFT.temp));
      setSensor(SENSORS[2], state.values.rotational_speed + d(LIVE_DRIFT.rpm));
      setSensor(SENSORS[3], state.values.torque + d(LIVE_DRIFT.torque));
    }
    TelemetryChart.push(new Date().toLocaleTimeString([], { minute: "2-digit", second: "2-digit" }), Math.round(state.values.rotational_speed));
  }, STREAM_INTERVAL_MS);
}

/* ---------- auth, theme, tools ---------- */
function openLogin() { $("#loginError").textContent = ""; $("#loginModal").hidden = false; $("#loginUser").focus(); }
async function submitLogin(e) {
  e.preventDefault();
  try {
    await API.login($("#loginUser").value.trim(), $("#loginPass").value);
    $("#loginModal").hidden = true; $("#authBtn").textContent = "Sign out"; toast("Signed in."); loadAssets();
  } catch (err) { $("#loginError").textContent = err.message; }
}
function toggleTheme() {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem("aura_theme", dark ? "dark" : "light"); TelemetryChart.restyle();
}
async function checkHealth() {
  const tag = $("#aiTag");
  try {
    const h = await API.health();
    tag.textContent = h.model_loaded ? "Backend AI Active" : "Rule Engine Active"; tag.classList.toggle("off", !h.model_loaded);
  } catch (err) { tag.textContent = "Server Offline"; tag.classList.add("off"); }
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#machineSelect").addEventListener("change", (e) => selectMachine(Number(e.target.value)));
  $("#connectBtn").addEventListener("click", connectMachine);
  $("#evalBtn").addEventListener("click", () => evaluate());
  $("#calibrateBtn").addEventListener("click", () => calibrate());
  $("#themeToggle").addEventListener("click", toggleTheme);
  $("#printBtn").addEventListener("click", () => window.print());
  $("#soundBtn").addEventListener("click", (e) => { state.sound = !state.sound; e.currentTarget.setAttribute("aria-pressed", state.sound); });
  $("#loginForm").addEventListener("submit", submitLogin);
  $("#authBtn").addEventListener("click", () => { if (API.isSignedIn()) { API.signOut(); $("#authBtn").textContent = "Sign in"; toast("Signed out."); } else openLogin(); });
  document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => { b.closest(".modal").hidden = true; }));
  $("#fleetGrid").addEventListener("click", (e) => {
    const id = e.target.dataset.diagnose;
    if (id) { $("#machineSelect").value = id; selectMachine(Number(id)); showView("diagnostics"); }
  });
  API.setAuthHandler(openLogin);
}

async function init() {
  if (localStorage.getItem("aura_theme") === "dark") toggleTheme();
  buildSensors(); bindEvents(); startStream();
  if (API.isSignedIn()) $("#authBtn").textContent = "Sign out";
  await Promise.all([checkHealth(), loadAssets()]);
}
document.addEventListener("DOMContentLoaded", init);
