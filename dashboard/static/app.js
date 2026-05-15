const state = {
  calls: new Map(),
  selectedCallId: null,
  providers: {},
  transcripts: {},
  latency: {},
  events: [],
  turns: [],
  callWerSummary: null,
  callReferenceTranscript: "",
  callProviderTranscripts: {},
  callProviderSegments: {},
  callProviderWer: {},
  allCallsWer: null,
  referenceError: "",
  eventKeys: new Set(),
  ingestCounter: 0,
  settings: null,
  settingsMeta: null,
};

const PROVIDER_META = {
  deepgram: { label: "Deepgram", color: "#38bdf8", borderClass: "border-sky-900/80" },
  speechmatics: { label: "Speechmatics", color: "#f59e0b", borderClass: "border-amber-900/80" },
  soniox: { label: "Soniox", color: "#22c55e", borderClass: "border-emerald-900/80" },
};

const latencyChart = new Chart(document.getElementById("latencyChart"), {
  type: "line",
  data: {
    labels: [],
    datasets: [],
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
      ingest_order: state.ingestCounter,
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
  if (event.ingest_order === undefined || event.ingest_order === null) {
    event.ingest_order = state.ingestCounter;
    state.ingestCounter += 1;
  }
  state.events.push(event);
  state.events.sort(compareEvents);
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
  renderTimeline();
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
  const detail = await fetchJson(`/api/benchmark/calls/${encodeURIComponent(callId)}`);
  state.calls.set(callId, detail);
  rebuildSelectedState(detail.events || []);
  await loadReferenceTurns(callId);
  await loadAllCallsWer();
  renderCalls();
}

function resetSelectedState() {
  state.providers = {};
  state.transcripts = {};
  state.latency = {};
  state.events = [];
  state.turns = [];
  state.callWerSummary = null;
  state.callReferenceTranscript = "";
  state.callProviderTranscripts = {};
  state.callProviderSegments = {};
  state.callProviderWer = {};
  state.referenceError = "";
  state.eventKeys = new Set();
  document.getElementById("timeline").innerHTML = "";
  document.getElementById("referenceTurns").innerHTML = "";
  renderComparison();
  renderProviderStats();
  renderSelectedCallSummary();
  renderQualityComparison();
  renderCallReference();
  renderReferenceTurns();
  renderAllCallsWer();
  renderChart();
}

async function loadReferenceTurns(callId) {
  if (!callId) return;
  try {
    const detail = await fetchJson(`/api/benchmark/calls/${encodeURIComponent(callId)}/turns`);
    state.turns = detail.turns || [];
    state.callWerSummary = detail.wer_summary || null;
    state.callReferenceTranscript = detail.call_reference_transcript || "";
    state.callProviderTranscripts = detail.call_provider_transcripts || {};
    state.callProviderSegments = detail.call_provider_segments || {};
    state.callProviderWer = detail.call_provider_wer || {};
    state.referenceError = "";
  } catch (error) {
    state.turns = [];
    state.callWerSummary = null;
    state.callReferenceTranscript = "";
    state.callProviderTranscripts = {};
    state.callProviderSegments = {};
    state.callProviderWer = {};
    state.referenceError = error.message;
  }
  renderQualityComparison();
  renderCallReference();
  renderReferenceTurns();
}

async function loadAllCallsWer() {
  try {
    state.allCallsWer = await fetchJson("/api/benchmark/wer/summary");
  } catch (error) {
    state.allCallsWer = { error: error.message };
  }
  renderAllCallsWer();
}

async function loadSettings() {
  const payload = await fetchJson("/api/settings");
  state.settings = payload.settings || {};
  state.settingsMeta = payload;
  renderSettings();
}

function renderSettings() {
  const settings = state.settings || {};
  const providers = state.settingsMeta?.providers || ["deepgram", "speechmatics", "soniox"];
  const modes = state.settingsMeta?.modes || ["production", "shadow", "comparison"];
  const deepgramModels = uniqueOptions([settings.deepgram_stt_model, ...(state.settingsMeta?.deepgram_models || [])]);
  const sonioxModels = uniqueOptions([settings.soniox_stt_model, ...(state.settingsMeta?.soniox_models || [])]);
  const speechmaticsPoints = state.settingsMeta?.speechmatics_operating_points || ["enhanced", "standard"];

  document.getElementById("settingsPanel").innerHTML = `
    ${selectField("stt_benchmark_mode", "Mode", settings.stt_benchmark_mode, modes)}
    ${selectField("stt_primary_provider", "Primary", settings.stt_primary_provider, providers)}
    ${selectField("stt_shadow_provider", "Shadow", settings.stt_shadow_provider, providers)}
    ${comboField("deepgram_stt_model", "Deepgram Model", settings.deepgram_stt_model, deepgramModels)}
    ${selectField("speechmatics_operating_point", "Speechmatics Quality", settings.speechmatics_operating_point, speechmaticsPoints)}
    ${numberField("speechmatics_max_delay", "Speechmatics Max Delay", settings.speechmatics_max_delay, "0.1", "0")}
    ${comboField("soniox_stt_model", "Soniox Model", settings.soniox_stt_model, sonioxModels)}
    ${numberField("soniox_max_endpoint_delay_ms", "Soniox Endpoint Ms", settings.soniox_max_endpoint_delay_ms, "100", "500", "3000")}
    ${checkboxField("benchmark_publish_events", "Publish Events", settings.benchmark_publish_events)}
    ${textField("benchmark_api_url", "Benchmark API URL", settings.benchmark_api_url)}
    ${textField("benchmark_storage_root", "Storage Root", settings.benchmark_storage_root)}
  `;
}

async function saveSettings() {
  const form = document.getElementById("settingsPanel");
  const payload = {};
  form.querySelectorAll("[data-setting]").forEach((input) => {
    if (input.type === "checkbox") payload[input.dataset.setting] = input.checked;
    else payload[input.dataset.setting] = input.value;
  });
  const status = document.getElementById("settingsStatus");
  status.textContent = "saving";
  const response = await fetchJson("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.settings = response.settings || {};
  status.textContent = "Saved. Applies to new calls.";
  renderSettings();
}

function rebuildSelectedState(events) {
  resetSelectedState();
  state.events = [...events].map((event, index) => ({
    ...event,
    ingest_order: event.id ?? index,
  })).sort(compareEvents);
  state.ingestCounter = Math.max(state.ingestCounter, state.events.length);
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
  renderReferenceTurns();
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
        <span class="font-medium">${escapeHtml(providerLabel(stats.provider))}</span>
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
  const providerTiles = providerNames().map((provider) => {
    const stats = state.providers[provider];
    const label = providerLabel(provider);
    return summaryTile(`${label} Events`, formatCount(stats?.events), `${formatCount(stats?.final_events)} final`, `Total ${label} transcript events received for this call. Events include partial and final transcript updates.`);
  }).join("");

  document.getElementById("selectedCallSummary").innerHTML = `
    ${summaryTile("Selected Call", call.call_id || "No call selected", call.room_id || "", "The currently selected LiveKit call/session. Click a call on the left to inspect its transcript timeline and provider metrics.")}
    ${providerTiles}
  `;
}

function renderQualityComparison() {
  const providers = providerNames();
  const latencyWinner = providerWithBestValue(providers, (provider) => state.providers[provider]?.avg_final_latency_ms, "lower");
  const stabilityWinner = providerWithBestValue(providers, (provider) => state.providers[provider]?.transcript_stability, "higher");
  const werTiles = providers.map((provider) => {
    const label = providerLabel(provider);
    return comparisonTile(`${label} Call WER`, formatPercent(state.callProviderWer[provider]?.wer), `${formatCount(state.callProviderSegments[provider])} final segments`, `${label} word error rate against the saved whole-call human reference transcript.`);
  }).join("");
  const streamingTiles = providers.map((provider) => {
    const stats = state.providers[provider];
    const label = providerLabel(provider);
    return comparisonTile(`${label} Streaming`, streamingSummary(stats), `rewrite rate ${formatPercent(rewriteRate(stats))}`, `${label} streaming quality based on partial transcript stability. A rewrite is counted when a partial update changes from the previous partial.`);
  }).join("");
  const firstPartialTiles = providers.map((provider) => {
    const stats = state.providers[provider];
    const label = providerLabel(provider);
    return comparisonTile(`${label} First Partial`, formatMs(stats?.first_partial_latency_ms), `first final ${formatMs(stats?.first_final_latency_ms)}`, `Elapsed time from first mirrored audio frame to ${label}'s first partial transcript. The hint shows time to first final transcript.`);
  }).join("");

  document.getElementById("qualityComparison").innerHTML = `
    ${werTiles}
    ${comparisonTile("Latency Winner", latencyWinner.label, latencyWinner.hint, "Compares average elapsed transcript event time for providers in this call. Lower is treated as faster.")}
    ${comparisonTile("Stability Winner", stabilityWinner.label, stabilityWinner.hint, "Compares how often partial transcripts changed. Higher stability means fewer partial rewrites.")}
    ${streamingTiles}
    ${firstPartialTiles}
  `;
}

function renderAllCallsWer() {
  const summary = state.allCallsWer || {};
  if (summary.error) {
    document.getElementById("allCallsWer").innerHTML = `
      <div class="rounded border border-red-900 bg-red-950/30 p-3 text-sm text-red-200 md:col-span-3">${escapeHtml(summary.error)}</div>
    `;
    return;
  }
  const providers = summary.providers || {};
  const providerTiles = Object.keys(providers).sort().map((provider) => {
    const label = providerLabel(provider);
    return summaryTile(`${label} All-Calls WER`, formatPercent(providers[provider]?.wer), `${formatCount(providers[provider]?.turns)} turns`, `${label} aggregate WER against all saved human reference transcripts.`);
  }).join("");
  document.getElementById("allCallsWer").innerHTML = `
    ${summaryTile("Reviewed Calls", formatCount(summary.reviewed_calls), `${formatCount(summary.reviewed_turns)} turns`, "Calls and turns that have saved human reference transcripts.")}
    ${providerTiles}
  `;
}

function renderCallReference() {
  const container = document.getElementById("callReference");
  if (!state.selectedCallId || state.referenceError) {
    container.innerHTML = "";
    return;
  }
  const finalCounts = providerNames().map((provider) => `
    <span>${escapeHtml(providerLabel(provider))} finals ${formatCount(state.callProviderSegments[provider])}</span>
  `).join("");
  container.innerHTML = `
    <div class="rounded border border-zinc-800 bg-zinc-950 p-3">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div class="font-medium">Call-Level Reference</div>
        <div class="flex flex-wrap gap-2 text-xs text-zinc-400">
          ${finalCounts}
        </div>
      </div>
      <label class="mb-1 block text-xs uppercase text-zinc-500" for="call-reference-input">Human Reference</label>
      <textarea id="call-reference-input" class="min-h-28 w-full rounded border border-zinc-700 bg-zinc-900 p-2 text-sm text-zinc-100">${escapeHtml(state.callReferenceTranscript || "")}</textarea>
      <div class="mt-2 flex items-center justify-between gap-3">
        <div class="text-xs text-zinc-500">Use the full correct caller transcript for this call. WER is calculated against concatenated final transcripts.</div>
        <button id="save-call-reference" class="rounded bg-sky-700 px-3 py-1 text-xs font-medium text-white hover:bg-sky-600">Save Call Reference</button>
      </div>
    </div>
  `;
  document.getElementById("save-call-reference").addEventListener("click", saveCallReference);
}

function renderReferenceTurns() {
  const container = document.getElementById("referenceTurns");
  if (!state.selectedCallId) {
    container.innerHTML = `<div class="text-zinc-500">Select a call to review reference transcripts.</div>`;
    return;
  }
  if (state.referenceError) {
    container.innerHTML = `<div class="rounded border border-red-900 bg-red-950/30 p-3 text-red-200">${escapeHtml(state.referenceError)}</div>`;
    return;
  }
  if (!state.turns.length) {
    container.innerHTML = `<div class="text-zinc-500">No final transcript segments yet.</div>`;
    return;
  }
  container.innerHTML = `
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      ${providerNames().map((provider) => providerSegmentsCard(provider)).join("")}
    </div>
  `;
}

function providerSegmentsCard(provider) {
  const segments = state.turns
    .map((turn) => turn.transcripts?.[provider])
    .filter((transcript) => transcript && transcript.trim());
  return `
    <div class="rounded border border-zinc-800 bg-zinc-950 p-3">
      <div class="mb-2 flex items-center justify-between">
        <div class="font-medium">${escapeHtml(providerLabel(provider))}</div>
        <div class="text-xs text-zinc-400">${segments.length} final segments</div>
      </div>
      <div class="space-y-2">
        ${segments.map((segment, index) => `
          <div class="rounded bg-black/30 p-2">
            <div class="mb-1 text-xs text-zinc-500">Final ${index + 1}</div>
            <div class="leading-6">${escapeHtml(segment)}</div>
          </div>
        `).join("") || `<div class="text-zinc-500">No final segments</div>`}
      </div>
    </div>
  `;
}

async function saveCallReference() {
  const input = document.getElementById("call-reference-input");
  const reference = input ? input.value : "";
  const detail = await fetchJson(`/api/benchmark/calls/${encodeURIComponent(state.selectedCallId)}/reference`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reference_transcript: reference }),
  });
  state.turns = detail.turns || [];
  state.callWerSummary = detail.wer_summary || null;
  state.callReferenceTranscript = detail.call_reference_transcript || "";
  state.callProviderTranscripts = detail.call_provider_transcripts || {};
  state.callProviderSegments = detail.call_provider_segments || {};
  state.callProviderWer = detail.call_provider_wer || {};
  state.referenceError = "";
  renderQualityComparison();
  renderCallReference();
  renderReferenceTurns();
  await loadAllCallsWer();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function selectField(name, label, value, options) {
  return `
    <label class="grid gap-1">
      <span class="uppercase text-zinc-500">${escapeHtml(label)}</span>
      <select data-setting="${escapeAttr(name)}" class="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100">
        ${options.map((option) => `<option value="${escapeAttr(option)}" ${String(option) === String(value) ? "selected" : ""}>${escapeHtml(providerOrValueLabel(option))}</option>`).join("")}
      </select>
    </label>
  `;
}

function comboField(name, label, value, options) {
  const listId = `${name}-options`;
  return `
    <label class="grid gap-1">
      <span class="uppercase text-zinc-500">${escapeHtml(label)}</span>
      <input data-setting="${escapeAttr(name)}" list="${escapeAttr(listId)}" value="${escapeAttr(value || "")}" class="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100" />
      <datalist id="${escapeAttr(listId)}">
        ${options.map((option) => `<option value="${escapeAttr(option)}"></option>`).join("")}
      </datalist>
    </label>
  `;
}

function numberField(name, label, value, step, min, max = "") {
  return `
    <label class="grid gap-1">
      <span class="uppercase text-zinc-500">${escapeHtml(label)}</span>
      <input data-setting="${escapeAttr(name)}" type="number" value="${escapeAttr(value)}" step="${escapeAttr(step)}" min="${escapeAttr(min)}" ${max ? `max="${escapeAttr(max)}"` : ""} class="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100" />
    </label>
  `;
}

function textField(name, label, value) {
  return `
    <label class="grid gap-1">
      <span class="uppercase text-zinc-500">${escapeHtml(label)}</span>
      <input data-setting="${escapeAttr(name)}" value="${escapeAttr(value || "")}" class="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-100" />
    </label>
  `;
}

function checkboxField(name, label, value) {
  return `
    <label class="flex items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950 px-2 py-1">
      <span class="uppercase text-zinc-500">${escapeHtml(label)}</span>
      <input data-setting="${escapeAttr(name)}" type="checkbox" ${value ? "checked" : ""} class="h-4 w-4 accent-sky-600" />
    </label>
  `;
}

function comparisonTile(label, value, hint, description) {
  return `
    <div class="rounded bg-zinc-950 p-3">
      <div class="flex items-center gap-1 text-xs uppercase text-zinc-500">
        <span>${escapeHtml(label)}</span>
        ${infoIcon(description)}
      </div>
      <div class="mt-1 text-sm font-semibold">${escapeHtml(value)}</div>
      <div class="mt-1 text-xs text-zinc-500">${escapeHtml(hint)}</div>
    </div>
  `;
}

function summaryTile(label, value, hint, description) {
  return `
    <div class="rounded border border-zinc-800 bg-zinc-900 p-3">
      <div class="flex items-center gap-1 text-xs uppercase text-zinc-500">
        <span>${escapeHtml(label)}</span>
        ${infoIcon(description)}
      </div>
      <div class="mt-1 truncate text-sm font-semibold" title="${escapeAttr(value)}">${escapeHtml(value)}</div>
      <div class="mt-1 truncate text-xs text-zinc-500" title="${escapeAttr(hint)}">${escapeHtml(hint)}</div>
    </div>
  `;
}

function infoIcon(description) {
  if (!description) return "";
  return `
    <span class="group relative inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-zinc-700 text-[10px] normal-case text-zinc-400" tabindex="0" aria-label="${escapeAttr(description)}">
      i
      <span class="pointer-events-none absolute left-1/2 top-5 z-20 hidden w-72 -translate-x-1/2 rounded border border-zinc-700 bg-zinc-950 p-2 text-left text-xs normal-case leading-5 text-zinc-200 shadow-xl group-hover:block group-focus:block">
        ${escapeHtml(description)}
      </span>
    </span>
  `;
}

function renderComparison() {
  document.getElementById("transcriptComparison").innerHTML = providerNames().map((provider) => `
    <div>
      <div class="mb-2 text-xs uppercase text-zinc-500">${escapeHtml(providerLabel(provider))}</div>
      <div class="min-h-32 rounded bg-zinc-950 p-3 text-sm leading-6">${escapeHtml(state.transcripts[provider] || "")}</div>
    </div>
  `).join("") || `<div class="text-zinc-500">Waiting for transcripts</div>`;
}

function lastFinalTranscript(provider) {
  const finals = state.events.filter((event) => event.provider === provider && event.is_final && event.transcript);
  return finals.length ? finals[finals.length - 1].transcript : "";
}

function renderTimeline() {
  const timeline = document.getElementById("timeline");
  timeline.innerHTML = "";
  const groups = timelineGroups(state.events)
    .sort((a, b) => (b.startedAt || 0) - (a.startedAt || 0))
    .slice(0, 120);
  groups.forEach((group) => {
    timeline.appendChild(timelineGroupCard(group));
  });
}

function timelineGroups(events) {
  const active = {};
  const groups = [];
  const ordered = [...events].sort(compareEvents);

  for (const event of ordered) {
    const provider = event.provider || "unknown";
    if (!active[provider]) {
      active[provider] = {
        provider,
        startedAt: timelineOrderValue(event),
        endedAt: timelineOrderValue(event),
        events: [],
        isFinal: false,
      };
    }

    active[provider].events.push(event);
    active[provider].endedAt = timelineOrderValue(event);

    if (event.is_final) {
      active[provider].isFinal = true;
      groups.push(active[provider]);
      active[provider] = null;
    }
  }

  Object.values(active)
    .filter(Boolean)
    .forEach((group) => groups.push(group));

  return groups;
}

function timelineGroupCard(group) {
  const card = document.createElement("div");
  const providerClass = providerMeta(group.provider).borderClass;
  const partials = group.events.filter((event) => !event.is_final);
  const finals = group.events.filter((event) => event.is_final);
  const eventIds = group.events.map((event) => event.id).filter((id) => id !== null && id !== undefined);
  const canDelete = eventIds.length === group.events.length && eventIds.length > 0;
  card.className = `rounded border ${providerClass} bg-zinc-950 p-3`;
  card.innerHTML = `
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-medium">${escapeHtml(group.provider)}</span>
        <span class="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">${group.events.length} events</span>
        <span class="rounded ${group.isFinal ? "bg-emerald-950 text-emerald-300" : "bg-amber-950 text-amber-300"} px-2 py-0.5 text-xs">${group.isFinal ? "finalized" : "in progress"}</span>
      </div>
      <div class="flex items-center gap-2">
        <div class="text-xs text-zinc-500">${escapeHtml(formatTimelineTime(group.events[0]))}</div>
        <button class="delete-turn inline-flex h-8 w-8 items-center justify-center rounded border border-red-900/70 text-red-300 hover:bg-red-950/50 disabled:cursor-not-allowed disabled:opacity-40" title="${canDelete ? "Delete this complete turn" : "Refresh the call before deleting"}" ${canDelete ? "" : "disabled"} data-event-ids="${escapeAttr(eventIds.join(","))}">
          ${trashIcon()}
        </button>
      </div>
    </div>
    <div class="space-y-3">
      ${partials.length ? `
        <div>
          <div class="mb-2 text-xs uppercase text-zinc-600">Partials</div>
          <div class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            ${partials.map((event, index) => timelinePartialBlock(event, index)).join("")}
          </div>
        </div>
      ` : ""}
      ${finals.length ? `
        <div>
          <div class="mb-2 text-xs uppercase text-zinc-600">Final</div>
          <div class="space-y-2">
            ${finals.map((event) => timelineFinalBlock(event)).join("")}
          </div>
        </div>
      ` : ""}
    </div>
  `;
  const deleteButton = card.querySelector(".delete-turn");
  if (deleteButton && canDelete) {
    deleteButton.addEventListener("click", () => deleteTimelineGroup(eventIds));
  }
  return card;
}

function trashIcon() {
  return `
    <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 6h18"></path>
      <path d="M8 6V4h8v2"></path>
      <path d="M19 6l-1 14H6L5 6"></path>
      <path d="M10 11v6"></path>
      <path d="M14 11v6"></path>
    </svg>
  `;
}

async function deleteTimelineGroup(eventIds) {
  if (!state.selectedCallId || !eventIds.length) return;
  const confirmed = window.confirm("Delete this complete turn, including partials and final transcript?");
  if (!confirmed) return;
  await fetchJson(`/api/benchmark/calls/${encodeURIComponent(state.selectedCallId)}/events`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_ids: eventIds }),
  });
  const ids = new Set(eventIds.map((id) => Number(id)));
  rebuildSelectedState(state.events.filter((event) => !ids.has(Number(event.id))));
  await loadReferenceTurns(state.selectedCallId);
  await loadAllCallsWer();
}

function timelinePartialBlock(event, index) {
  return `
    <div class="rounded bg-black/30 p-2">
      <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <span class="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300">partial ${index + 1}</span>
        <span>${formatMs(event.latency_ms)}</span>
        <span>#${event.sequence_id}</span>
      </div>
      <div class="mb-1 text-xs text-zinc-600">${escapeHtml(formatTimelineTime(event))}</div>
      <div class="text-zinc-300">${escapeHtml(event.transcript)}</div>
    </div>
  `;
}

function timelineFinalBlock(event) {
  return `
    <div class="rounded border border-emerald-900/60 bg-emerald-950/20 p-3">
      <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <span class="rounded bg-emerald-900/50 px-2 py-0.5 text-emerald-200">final</span>
        <span>${formatMs(event.latency_ms)}</span>
        <span>#${event.sequence_id}</span>
        <span>${escapeHtml(formatTimelineTime(event))}</span>
      </div>
      <div class="font-medium leading-6 text-zinc-100">${escapeHtml(event.transcript)}</div>
    </div>
  `;
}

function eventKey(event) {
  return [
    event.call_id || "",
    event.provider || "",
    event.sequence_id ?? "",
    event.is_final ? "final" : "partial",
    event.id ?? event.ingest_order ?? event.timestamp ?? "",
  ].join("|");
}

function compareEvents(a, b) {
  return timelineOrderValue(a) - timelineOrderValue(b);
}

function timelineOrderValue(event) {
  if (event.id !== null && event.id !== undefined) return Number(event.id);
  if (event.ingest_order !== null && event.ingest_order !== undefined) return Number(event.ingest_order);
  if (event.latency_ms !== null && event.latency_ms !== undefined) return Number(event.latency_ms);
  return Number(event.timestamp || 0);
}

function renderChart() {
  const providers = providerNames().filter((provider) => (state.latency[provider] || []).length);
  const maxPoints = Math.max(0, ...providers.map((provider) => state.latency[provider].length));
  latencyChart.data.labels = Array.from({ length: maxPoints }, (_, i) => i + 1);
  latencyChart.data.datasets = providers.map((provider) => ({
    label: providerLabel(provider),
    data: state.latency[provider] || [],
    borderColor: providerMeta(provider).color,
    tension: 0.25,
  }));
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

function providerNames() {
  return Array.from(new Set([
    ...Object.keys(state.providers || {}),
    ...Object.keys(state.transcripts || {}),
    ...Object.keys(state.latency || {}),
    ...Object.keys(state.callProviderSegments || {}),
    ...Object.keys(state.callProviderWer || {}),
    ...state.events.map((event) => event.provider).filter(Boolean),
  ])).sort((a, b) => providerLabel(a).localeCompare(providerLabel(b)));
}

function providerMeta(provider) {
  const normalized = String(provider || "").toLowerCase();
  return PROVIDER_META[normalized] || {
    label: titleCaseProvider(normalized || "unknown"),
    color: colorForProvider(normalized),
    borderClass: "border-violet-900/80",
  };
}

function providerLabel(provider) {
  return providerMeta(provider).label;
}

function providerOrValueLabel(value) {
  return PROVIDER_META[String(value || "").toLowerCase()] ? providerLabel(value) : titleCaseProvider(value);
}

function titleCaseProvider(provider) {
  return String(provider || "unknown").replace(/[-_]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function colorForProvider(provider) {
  let hash = 0;
  for (const char of String(provider || "provider")) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return `hsl(${hash} 78% 62%)`;
}

function providerWithBestValue(providers, valueForProvider, direction) {
  const values = providers
    .map((provider) => ({ provider, value: valueForProvider(provider) }))
    .filter((item) => item.value !== null && item.value !== undefined);
  if (!values.length) return { label: "n/a", hint: "No comparable provider values" };
  values.sort((a, b) => direction === "lower" ? a.value - b.value : b.value - a.value);
  const best = values[0];
  const tie = values.length > 1 && Number(values[0].value) === Number(values[1].value);
  return {
    label: tie ? "Tie" : providerLabel(best.provider),
    hint: values.map((item) => `${providerLabel(item.provider)} ${direction === "lower" ? formatMs(item.value) : formatPercent(item.value)}`).join(" vs "),
  };
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

function formatTimelineTime(event) {
  if (event.latency_ms !== null && event.latency_ms !== undefined) {
    return `t+${formatMs(event.latency_ms)}`;
  }
  return formatDateTime(event.timestamp);
}

function uniqueOptions(options) {
  return Array.from(new Set(options.filter((option) => option !== null && option !== undefined && String(option).trim()).map(String)));
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

document.getElementById("refreshWer").addEventListener("click", async () => {
  if (state.selectedCallId) {
    await loadReferenceTurns(state.selectedCallId);
  }
  await loadAllCallsWer();
});
document.getElementById("saveSettings").addEventListener("click", saveSettings);

loadSettings();
loadCalls();
loadAllCallsWer();
connect();
