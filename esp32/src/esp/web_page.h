// =============================================================================
// web_page.h - The single-page web UI served at "/"
// =============================================================================
//
// Renders genmon's report trees generically (the same JSON other tools read
// from /cmd/...), so new report fields appear without UI changes. Settings
// are edited through a form generated from /api/settings.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <pgmspace.h>


namespace genmon {

// =============================================================================
// Page
// =============================================================================

const char kWebPage[] PROGMEM = R"HTML(<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generator Monitor</title>
<style>
:root { --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#5f6b7a; --line:#dde2e8; --accent:#1f6feb; --bad:#c62828; --good:#2e7d32; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#12151b; --card:#1b2029; --ink:#e6e9ef; --muted:#9aa5b4; --line:#2c3340; --accent:#4c8dff; --bad:#ff6b6b; --good:#5fd068; }
}
* { box-sizing: border-box; }
body { margin:0; font:15px/1.45 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:var(--bg); color:var(--ink); }
header { padding:14px 16px; background:var(--card); border-bottom:1px solid var(--line); display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; }
header h1 { font-size:18px; margin:0; }
#summary { color:var(--muted); }
nav { display:flex; flex-wrap:wrap; gap:4px; padding:8px 12px; }
nav button { border:1px solid var(--line); background:var(--card); color:var(--ink); padding:6px 12px; border-radius:6px; cursor:pointer; }
nav button.active { background:var(--accent); border-color:var(--accent); color:#fff; }
main { padding:0 12px 24px; max-width:960px; }
section { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; margin-top:10px; overflow-x:auto; }
h2 { font-size:15px; margin:4px 0 8px; }
table { border-collapse:collapse; width:100%; }
td { padding:4px 6px; border-bottom:1px solid var(--line); vertical-align:top; }
td.k { color:var(--muted); width:42%; }
.alarm { color:var(--bad); font-weight:600; }
.ok { color:var(--good); }
.controls button { margin:4px 6px 4px 0; padding:8px 12px; border-radius:6px; border:1px solid var(--line); background:var(--bg); color:var(--ink); cursor:pointer; }
.controls button.danger { border-color:var(--bad); color:var(--bad); }
label { display:block; margin:6px 0 2px; color:var(--muted); font-size:13px; }
input, select { width:100%; max-width:360px; padding:6px 8px; border:1px solid var(--line); border-radius:5px; background:var(--bg); color:var(--ink); }
input[type=checkbox] { width:auto; }
.row { display:flex; gap:8px; flex-wrap:wrap; align-items:end; }
.row > div { flex:1 1 140px; }
#message { margin-top:8px; min-height:1.4em; }
pre { white-space:pre-wrap; margin:0; }
</style>
</head>
<body>
<header><h1 id="site">Generator Monitor</h1><span id="summary">Connecting…</span></header>
<nav id="tabs"></nav>
<main id="content"></main>
<script>
"use strict";
const TABS = [
  ["Status", () => report("status_json")],
  ["Maintenance", () => report("maint_json")],
  ["Outage", () => report("outage_json")],
  ["Logs", () => report("logs_json")],
  ["Monitor", monitorTab],
  ["Control", controlTab],
  ["Settings", settingsTab],
];
const SETTING_GROUPS = {
  "Network": ["wifi_ssid","wifi_password","hostname","timezone","ntp_server","admin_password"],
  "Generator": ["sitename","model","fueltype","nominalkw","nominalrpm","nominalfrequency","phase","nominallinevolts"],
  "Controller": ["address","uart_rx_pin","uart_tx_pin","evolutioncontroller","liquidcooled","enhancedexercise",
                 "uselegacysetexercise","currentdivider","currentoffset","additionalrunhours","serialnumberifmissing",
                 "ignore_unknown","nexus_legacy_freq","disableoutagecheck","synctime"],
  "MQTT broker": ["mqtt_address","mqtt_port","username","password","client_id"],
  "Home Assistant (genhomeassistant)": ["ha_enabled","discovery_prefix","base_topic","device_id","device_name",
                 "blacklist","include_monitor_stats","poll_interval","discovery_interval"],
  "Plain MQTT topics (genmqtt)": ["genmqtt_enabled","root_topic","numeric_json","retain","remove_spaces",
                 "genmqtt_blacklist","genmqtt_allow_commands","genmqtt_poll_interval"],
};
const TRISTATE = ["evolutioncontroller", "liquidcooled"];
let current = 0, timer = null;

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return node;
};

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || response.statusText);
  return response.json();
}

async function post(url, body, type = "text/plain") {
  const response = await fetch(url, { method: "POST", body, headers: type ? { "Content-Type": type } : {} });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data.result || "OK";
}

// genmon reports are lists of single-key objects; render them as nested tables.
function render(node) {
  if (node === null || typeof node !== "object") return document.createTextNode(node === null ? "" : String(node));
  const table = el("table");
  const addRow = (key, value) => {
    const cell = el("td");
    cell.append(render(value));
    if (key === "System In Alarm") cell.className = "alarm";
    table.append(el("tr", {}, el("td", { class: "k" }, key), cell));
  };
  if (Array.isArray(node)) {
    node.forEach(item => {
      if (item && typeof item === "object" && !Array.isArray(item)) Object.entries(item).forEach(([k, v]) => addRow(k, v));
      else table.append(el("tr", {}, el("td", { colspan: 2 }, String(item))));
    });
  } else {
    Object.entries(node).forEach(([k, v]) => addRow(k, v));
  }
  return table;
}

function show(...sections) {
  const content = document.getElementById("content");
  content.replaceChildren(...sections);
}

async function report(name) {
  const data = await getJson("/cmd/" + name);
  show(...Object.entries(data).map(([title, body]) => el("section", {}, el("h2", {}, title), render(body))));
}

async function monitorTab() {
  const [monitor, events, registers] = await Promise.all([
    getJson("/cmd/monitor_json"), getJson("/api/events"), getJson("/api/registers")]);
  const eventList = el("table");
  events.Events.forEach(e => eventList.append(el("tr", {},
    el("td", { class: "k" }, e.epoch > 1e9 ? new Date(e.epoch * 1000).toLocaleString() : "—"), el("td", {}, e.text))));
  show(el("section", {}, el("h2", {}, "Monitor"), render(monitor.Monitor)),
       el("section", {}, el("h2", {}, "Recent events"), eventList),
       el("section", {}, el("h2", {}, "Registers"), render(registers.Registers)));
}

function controlTab() {
  stopRefresh();
  const message = el("div", { id: "message" });
  const run = async command => {
    message.textContent = "Sending " + command + "…";
    try { message.textContent = await post("/api/command", command); } catch (e) { message.textContent = "Error: " + e.message; }
  };
  const button = (label, command, danger) =>
    el("button", { class: danger ? "danger" : "", onclick: () => {
      if (!danger || confirm(label + "?")) run(command);
    } }, label);

  const day = el("select", {}, ...["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"].map(d => el("option", {}, d)));
  const time = el("input", { type: "time", value: "12:00" });
  const freq = el("select", {}, el("option", {}, "weekly"), el("option", {}, "biweekly"), el("option", {}, "monthly"));
  const firmware = el("input", { type: "file", accept: ".bin" });

  show(
    el("section", { class: "controls" }, el("h2", {}, "Remote control"),
      button("Start", "setremote=start", true), button("Start and transfer", "setremote=starttransfer", true),
      button("Start exercise", "setremote=startexercise", true), button("Stop", "setremote=stop", true),
      el("br"), button("Auto", "setremote=auto"), button("Manual", "setremote=manual", true),
      button("Off", "setremote=off", true), button("Reset alarm", "setremote=resetalarm"),
      el("br"), button("Set generator time", "settime"),
      button("Quiet mode on", "setquiet=on"), button("Quiet mode off", "setquiet=off")),
    el("section", { class: "controls" }, el("h2", {}, "Exercise schedule"),
      el("div", { class: "row" },
        el("div", {}, el("label", {}, "Day (or 1-28 for monthly)"), day),
        el("div", {}, el("label", {}, "Time"), time),
        el("div", {}, el("label", {}, "Frequency"), freq)),
      el("button", { onclick: () => {
        const dayValue = freq.value === "monthly" ? prompt("Day of month (1-28)", "1") : day.value;
        if (dayValue) run(`setexercise=${dayValue},${time.value},${freq.value}`);
      } }, "Set exercise time")),
    el("section", { class: "controls" }, el("h2", {}, "Firmware"),
      firmware,
      el("button", { onclick: async () => {
        if (!firmware.files.length) return;
        const form = new FormData(); form.append("firmware", firmware.files[0]);
        message.textContent = "Uploading…";
        try { message.textContent = await post("/api/update", form, null); } catch (e) { message.textContent = "Error: " + e.message; }
      } }, "Upload and install"),
      el("button", { class: "danger", onclick: async () => {
        if (confirm("Restart the monitor?")) message.textContent = await post("/api/reboot", "").catch(e => "Error: " + e.message);
      } }, "Restart monitor")),
    message);
}

async function settingsTab() {
  stopRefresh();
  let data;
  try { data = await getJson("/api/settings"); }
  catch (e) { show(el("section", {}, "Settings unavailable: " + e.message)); return; }

  const inputs = {};
  const field = key => {
    let input;
    if (key + "_set" in data) {
      input = el("input", { type: "password", placeholder: data[key + "_set"] ? "(unchanged)" : "(not set)" });
    } else if (TRISTATE.includes(key)) {
      input = el("select", {}, ...["auto", "true", "false"].map(v => el("option", { value: v }, v)));
      input.value = data[key];
    } else if (typeof data[key] === "boolean") {
      input = el("input", { type: "checkbox" }); input.checked = data[key];
    } else if (typeof data[key] === "number") {
      input = el("input", { type: "number", step: "any", value: data[key] });
    } else {
      input = el("input", { type: "text", value: data[key] ?? "" });
    }
    inputs[key] = input;
    return el("div", {}, el("label", {}, key), input);
  };

  const message = el("div", { id: "message" });
  const sections = Object.entries(SETTING_GROUPS).map(([title, keys]) =>
    el("section", {}, el("h2", {}, title), ...keys.filter(k => k in data || k + "_set" in data).map(field)));
  const save = el("button", { onclick: async () => {
    const out = {};
    for (const [key, input] of Object.entries(inputs)) {
      if (input.type === "checkbox") out[key] = input.checked;
      else if (input.type === "number") out[key] = Number(input.value);
      else if (input.type === "password") { if (input.value) out[key] = input.value; }
      else out[key] = input.value;
    }
    message.textContent = "Saving…";
    try { message.textContent = await post("/api/settings", JSON.stringify(out), "application/json"); }
    catch (e) { message.textContent = "Error: " + e.message; }
  } }, "Save and restart");
  show(...sections, el("section", { class: "controls" }, save, message));
}

function stopRefresh() { if (timer) { clearInterval(timer); timer = null; } }

async function select(index) {
  current = index;
  document.querySelectorAll("nav button").forEach((b, i) => b.classList.toggle("active", i === index));
  stopRefresh();
  const load = async () => {
    try { await TABS[index][1](); } catch (e) { show(el("section", {}, "Error: " + e.message)); }
  };
  await load();
  if (index <= 4) timer = setInterval(load, 5000);
}

async function updateHeader() {
  try {
    const [info, status] = await Promise.all([getJson("/api/info"), getJson("/cmd/status_json")]);
    document.getElementById("site").textContent = info.sitename;
    document.title = info.sitename + " – Generator";
    const engine = Object.assign({}, ...(status.Status[0]?.Engine || []));
    const summary = document.getElementById("summary");
    summary.textContent = [engine["Switch State"], engine["Engine State"], engine["System In Alarm"],
                           info.setup_ap ? "Setup AP: " + info.setup_ap_name : "", "Monitor: " + info.health]
                          .filter(Boolean).join(" · ");
    summary.className = engine["System In Alarm"] ? "alarm" : "";
  } catch (e) {
    document.getElementById("summary").textContent = "Monitor unreachable";
  }
}

TABS.forEach(([name], i) => document.getElementById("tabs").append(el("button", { onclick: () => select(i) }, name)));
select(0);
updateHeader();
setInterval(updateHeader, 5000);
</script>
</body>
</html>
)HTML";

}  // namespace genmon
