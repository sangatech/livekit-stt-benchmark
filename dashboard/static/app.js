const state = {
  calls: new Map(),
  selectedCallId: null,
  providers: {},
  transcripts: { deepgram: "", speechmatics: "" },
  latency: { deepgram: [], speechmatics: [] },
  events: [],
  eventKeys: new Set(),
};

const latencyChart = new Chart(document.getElementById("latencyChart"), {
  type: "line",
  data: {
    labels: [],
    datasets: [
      { label: "Deepgram", data: [], borderColor: "#38bdf8", tension: 0.25 },
      { label: "Speechmatics", data: [], borderColor: "#f59e0b", tension: 0.25 },
    ],
  },
  options: {
    responsive: true,
    animation: false,
    plugins: { legend: { labels: { color: "#d4d4d8" } } },
    scales: {
      x: {
        title: { display: true, text: "Transcript event number", color: "#a1a1aa" },
        ticks: { color: "#a1a1aa" },
        grid: { color: "#27272a" },
      },
      y: {
        beginAtZero: true,
        title: { display: true, text: "Elapsed since first audio (ms)", color: "#a1a1aa" },
        ticks: { color: "#a1a1aa" },
        grid: { color: "#27272a" },
      },
    },
  },
});

function connect() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws/benchmark/live`);
  const socketState = document.getElementById("socketState");
  ws.onopen = () => {
    socketState.textContent = "live";
    socketState.className = "rounded bg-emerald-900 px-2 py-1 text-xs text-emerald-200";
  };
  ws.onclose = () => {
    socketState.textContent = "reconnecting";
    socketState.className = "rounded bg-amber-900 px-2 py-1 text-xs text-amber-200";
    setTimeout(connect, 1000);
  };
  ws.onmessage = (message) => {
    if (message.data === "pong") return;
    handleEvent(JSON.parse(message.data));
  };
  setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 15000);
}

function handleEvent(payload) {
  if (payload.type === "call_started") {
    state.calls.set(payload.call_id, payload);
    if (!state.selectedCallId) selectCall(payload.call_id);
  }
  if (payload.type === "transcript") {
    const event = payload.event;
    state.calls.set(event.call_id, {
      call_id: event.call_id,
      room_id: event.room_id,
      timestamp: event.timestamp,
    });
    if (!state.selectedCallId) state.selectedCallId = event.call_id;
    if (event.call_id === state.selectedCallId) {
      applyEventToSelectedCall(event);
    }
  }
  renderCalls();
}

function applyEventToSelectedCall(event) {
  const key = eventKey(event);
  if (state.eventKeys.has(key)) return;
  state.eventKeys.add(key);
  state.events.push(event);
  state.events.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  state.transcripts[event.provider] = event.transcript;
  updateProviderStatsFromEvent(event);
  if (event.latency_ms !== null && event.latency_ms !== undefined) {
    state.latency[event.provider] = state.latency[event.provider] || [];
    state.latency[event.provider].push(Number(event.latency_ms.toFixed(1)));
  }
  renderComparison();
  renderProviderStats();
  renderSelectedCallSummary();
  renderQualityComparison();
  appendTimelineEvent(event);
  renderChart();
}

async function loadCalls() {
  const calls = await fetch("/api/benchmark/calls").then((response) => response.json());
  calls.forEach((call) => state.calls.set(call.call_id, call));
  if (!state.selectedCallId && calls.length) {
    await selectCall(calls[0].call_id);
  }
  renderCalls();
}

async function selectCall(callId) {
  state.selectedCallId = callId;
  resetSelectedState();
  renderCalls();
  const detail = await fetch(`/api/benchmark/calls/${encodeURIComponent(callId)}`).then((response) => response.json());
  state.calls.set(callId, detail);
  rebuildSelectedState(detail.events || []);
  renderCalls();
}

function resetSelectedState() {
  state.providers = {};
  state.transcripts = { deepgram: "", speechmatics: "" };
  state.latency = { deepgram: [], speechmatics: [] };
  state.events = [];
  state.eventKeys = new Set();
  document.getElementById("timeline").innerHTML = "";
  renderComparison();
  renderProviderStats();
  renderSelectedCallSummary();
  renderQualityComparison();
  renderChart();
}

function rebuildSelectedState(events) {
  resetSelectedState();
  state.events = [...events].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  for (const event of state.events) {
    state.eventKeys.add(eventKey(event));
    state.transcripts[event.provider] = event.transcript;
    updateProviderStatsFromEvent(event);
    if (event.latency_ms !== null && event.latency_ms !== undefined) {
      state.latency[event.provider] = state.latency[event.provider] || [];
      state.latency[event.provider].push(Number(event.latency_ms.toFixed(1)));
    }
  }
  renderComparison();
  renderProviderStats();
  renderSelectedCallSummary();
  renderQualityComparison();
  renderTimeline();
  renderChart();
}

function updateProviderStatsFromEvent(event) {
  const stats = state.providers[event.provider] || {
    provider: event.provider,
    events: 0,
    partial_events: 0,
    final_events: 0,
    latencies: [],
    confidences: [],
    partial_rewrites: 0,
    last_partial: "",
    first_partial_latency_ms: null,
    first_final_latency_ms: null,
  };
  stats.events += 1;
  if (event.is_final) stats.final_events += 1;
  else {
    stats.partial_events += 1;
    if (stats.last_partial && stats.last_partial !== event.transcript) stats.partial_rewrites += 1;
    stats.last_partial = event.transcript;
  }
  if (event.latency_ms !== null && event.latency_ms !== undefined) stats.latencies.push(event.latency_ms);
  if (!event.is_final && stats.first_partial_latency_ms === null && event.latency_ms !== null && event.latency_ms !== undefined) {
    stats.first_partial_latency_ms = event.latency_ms;
  }
  if (event.is_final && stats.first_final_latency_ms === null && event.latency_ms !== null && event.latency_ms !== undefined) {
    stats.first_final_latency_ms = event.latency_ms;
  }
  if (event.confidence !== null && event.confidence !== undefined) stats.confidences.push(event.confidence);
  stats.avg_final_latency_ms = average(stats.latencies);
  stats.avg_confidence = average(stats.confidences);
  stats.transcript_stability = stats.partial_events ? Math.max(0, 1 - stats.partial_rewrites / stats.partial_events) : 1;
  stats.reconnects = 0;
  state.providers[event.provider] = stats;
}

function renderCalls() {
  const calls = Array.from(state.calls.values())
    .sort((a, b) => (b.started_at || b.timestamp || 0) - (a.started_at || a.timestamp || 0))
    .slice(0, 100);
  document.getElementById("calls").innerHTML = calls.map((call) => {
    const selected = call.call_id === state.selectedCallId;
    return `
      <button data-call-id="${escapeAttr(call.call_id)}" class="call-button w-full rounded border ${selected ? "border-sky-500 bg-sky-950/40" : "border-zinc-800 bg-zinc-950"} p-2 text-left hover:border-zinc-600">
        <div class="break-words font-medium">${escapeHtml(call.call_id || "unknown")}</div>
        <div class="break-words text-xs text-zinc-500">${escapeHtml(formatDateTime(call.started_at || call.timestamp))}</div>
      </button>
    `;
  }).join("") || `<div class="text-zinc-500">No calls yet</div>`;

  document.querySelectorAll(".call-button").forEach((button) => {
    button.addEventListener("click", () => selectCall(button.dataset.callId));
  });
}

function renderProviderStats() {
  document.getElementById("providerStats").innerHTML = Object.values(state.providers).map((stats) => `
    <div class="rounded bg-zinc-950 p-2">
      <div class="mb-1 flex items-center justify-between">
        <span class="font-medium">${escapeHtml(stats.provider)}</span>
        <span class="text-xs text-zinc-400">${formatMs(stats.avg_final_latency_ms)}</span>
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs text-zinc-400">
        <span>confidence ${formatPercent(stats.avg_confidence)}</span>
        <span>stability ${formatPercent(stats.transcript_stability)}</span>
        <span>events ${stats.events}</span>
        <span>rewrites ${stats.partial_rewrites}</span>
      </div>
    </div>
  `).join("") || `<div class="text-zinc-500">Waiting for transcripts</div>`;
}

function renderSelectedCallSummary() {
  const call = state.calls.get(state.selectedCallId) || {};
  const deepgram = state.providers.deepgram;
  const speechmatics = state.providers.speechmatics;
  const deepgramAvg = deepgram?.avg_final_latency_ms;
  const speechmaticsAvg = speechmatics?.avg_final_latency_ms;
  const delta = deepgramAvg !== null && deepgramAvg !== undefined && speechmaticsAvg !== null && speechmaticsAvg !== undefined
    ? speechmaticsAvg - deepgramAvg
    : null;

  document.getElementById("selectedCallSummary").innerHTML = `
    ${summaryTile("Selected Call", call.call_id || "No call selected", call.room_id || "")}
    ${summaryTile("Deepgram Events", formatCount(deepgram?.events), `${formatCount(deepgram?.final_events)} final`)}
    ${summaryTile("Speechmatics Events", formatCount(speechmatics?.events), `${formatCount(speechmatics?.final_events)} final`)}
    ${summaryTile("Avg Delta", formatDelta(delta), "Speechmatics minus Deepgram")}
  `;
}

function renderQualityComparison() {
  const deepgram = state.providers.deepgram;
  const speechmatics = state.providers.speechmatics;
  const dgFinal = lastFinalTranscript("deepgram");
  const smFinal = lastFinalTranscript("speechmatics");
  const wer = dgFinal && smFinal ? relativeWer(dgFinal, smFinal) : null;
  const similarity = wer === null ? null : Math.max(0, 1 - wer);
  const dgRewriteRate = rewriteRate(deepgram);
  const smRewriteRate = rewriteRate(speechmatics);
  const latencyWinner = providerWithLowerValue(deepgram?.avg_final_latency_ms, speechmatics?.avg_final_latency_ms);
  const stabilityWinner = providerWithHigherValue(deepgram?.transcript_stability, speechmatics?.transcript_stability);

  document.getElementById("qualityComparison").innerHTML = `
    ${comparisonTile("Relative WER", formatPercent(wer), "Deepgram vs Speechmatics disagreement")}
    ${comparisonTile("Transcript Similarity", formatPercent(similarity), "Higher means providers agree more")}
    ${comparisonTile("Latency Winner", latencyWinner, `${formatMs(deepgram?.avg_final_latency_ms)} vs ${formatMs(speechmatics?.avg_final_latency_ms)}`)}
    ${comparisonTile("Stability Winner", stabilityWinner, `${formatPercent(deepgram?.transcript_stability)} vs ${formatPercent(speechmatics?.transcript_stability)}`)}
    ${comparisonTile("Deepgram Streaming", streamingSummary(deepgram), `rewrite rate ${formatPercent(dgRewriteRate)}`)}
    ${comparisonTile("Speechmatics Streaming", streamingSummary(speechmatics), `rewrite rate ${formatPercent(smRewriteRate)}`)}
    ${comparisonTile("Deepgram First Partial", formatMs(deepgram?.first_partial_latency_ms), `first final ${formatMs(deepgram?.first_final_latency_ms)}`)}
    ${comparisonTile("Speechmatics First Partial", formatMs(speechmatics?.first_partial_latency_ms), `first final ${formatMs(speechmatics?.first_final_latency_ms)}`)}
  `;
}

function comparisonTile(label, value, hint) {
  return `
    <div class="rounded bg-zinc-950 p-3">
      <div class="text-xs uppercase text-zinc-500">${escapeHtml(label)}</div>
      <div class="mt-1 text-sm font-semibold">${escapeHtml(value)}</div>
      <div class="mt-1 text-xs text-zinc-500">${escapeHtml(hint)}</div>
    </div>
  `;
}

function summaryTile(label, value, hint) {
  return `
    <div class="rounded border border-zinc-800 bg-zinc-900 p-3">
      <div class="text-xs uppercase text-zinc-500">${escapeHtml(label)}</div>
      <div class="mt-1 truncate text-sm font-semibold" title="${escapeAttr(value)}">${escapeHtml(value)}</div>
      <div class="mt-1 truncate text-xs text-zinc-500" title="${escapeAttr(hint)}">${escapeHtml(hint)}</div>
    </div>
  `;
}

function renderComparison() {
  document.getElementById("deepgramTranscript").textContent = state.transcripts.deepgram || "";
  document.getElementById("speechmaticsTranscript").textContent = state.transcripts.speechmatics || "";
}

function lastFinalTranscript(provider) {
  const finals = state.events.filter((event) => event.provider === provider && event.is_final && event.transcript);
  return finals.length ? finals[finals.length - 1].transcript : "";
}

function renderTimeline() {
  const timeline = document.getElementById("timeline");
  timeline.innerHTML = "";
  [...state.events].reverse().slice(0, 200).forEach((event) => {
    timeline.appendChild(timelineRow(event));
  });
}

function appendTimelineEvent(event) {
  const timeline = document.getElementById("timeline");
  timeline.prepend(timelineRow(event));
  while (timeline.children.length > 200) {
    timeline.lastChild.remove();
  }
}

function timelineRow(event) {
  const row = document.createElement("div");
  row.className = "rounded bg-zinc-950 p-2";
  row.dataset.eventKey = eventKey(event);
  row.innerHTML = `
    <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
      <span>${escapeHtml(event.provider)}</span>
      <span>${event.is_final ? "final" : "partial"}</span>
      <span>${formatMs(event.latency_ms)}</span>
      <span>#${event.sequence_id}</span>
    </div>
    <div>${escapeHtml(event.transcript)}</div>
  `;
  return row;
}

function eventKey(event) {
  return [
    event.call_id || "",
    event.provider || "",
    event.sequence_id ?? "",
    event.is_final ? "final" : "partial",
    event.timestamp ?? "",
  ].join("|");
}

function renderChart() {
  const maxPoints = Math.max(state.latency.deepgram.length, state.latency.speechmatics.length);
  latencyChart.data.labels = Array.from({ length: maxPoints }, (_, i) => i + 1);
  latencyChart.data.datasets[0].data = state.latency.deepgram;
  latencyChart.data.datasets[1].data = state.latency.speechmatics;
  latencyChart.update();
}

function average(values) {
  return values.length ? values.reduce((sum, value) => sum + Number(value), 0) / values.length : null;
}

function relativeWer(primary, secondary) {
  const a = tokenize(primary);
  const b = tokenize(secondary);
  const distance = editDistance(a, b);
  return distance / Math.max(a.length, b.length, 1);
}

function tokenize(text) {
  return String(text || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function editDistance(a, b) {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const matrix = Array.from({ length: rows }, () => Array(cols).fill(0));
  for (let i = 0; i < rows; i += 1) matrix[i][0] = i;
  for (let j = 0; j < cols; j += 1) matrix[0][j] = j;
  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + cost,
      );
    }
  }
  return matrix[a.length][b.length];
}

function rewriteRate(stats) {
  if (!stats || !stats.partial_events) return null;
  return stats.partial_rewrites / stats.partial_events;
}

function streamingSummary(stats) {
  if (!stats) return "n/a";
  return `${formatPercent(stats.transcript_stability)} stable`;
}

function providerWithLowerValue(deepgramValue, speechmaticsValue) {
  if (deepgramValue === null || deepgramValue === undefined || speechmaticsValue === null || speechmaticsValue === undefined) return "n/a";
  if (deepgramValue === speechmaticsValue) return "Tie";
  return deepgramValue < speechmaticsValue ? "Deepgram" : "Speechmatics";
}

function providerWithHigherValue(deepgramValue, speechmaticsValue) {
  if (deepgramValue === null || deepgramValue === undefined || speechmaticsValue === null || speechmaticsValue === undefined) return "n/a";
  if (deepgramValue === speechmaticsValue) return "Tie";
  return deepgramValue > speechmaticsValue ? "Deepgram" : "Speechmatics";
}

function formatMs(value) {
  return value === null || value === undefined ? "n/a" : `${Number(value).toFixed(0)} ms`;
}

function formatDelta(value) {
  if (value === null || value === undefined) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(0)} ms`;
}

function formatCount(value) {
  return value === null || value === undefined ? "0" : String(value);
}

function formatDateTime(value) {
  if (value === null || value === undefined) return "time unavailable";
  const milliseconds = Number(value) < 1000000000000 ? Number(value) * 1000 : Number(value);
  const date = new Date(milliseconds);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatPercent(value) {
  return value === null || value === undefined ? "n/a" : `${(Number(value) * 100).toFixed(0)}%`;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

loadCalls();
connect();
