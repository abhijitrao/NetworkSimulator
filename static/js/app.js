const $ = (id) => document.getElementById(id);
let state = [];
let toastTimer;
let networkInterfaces = [];
let selectedNetworkIp = '';

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || ('Request failed: ' + response.status));
  return data;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function runtimeOf(profile) { return profile.runtime || {running:false,active_connections:0,connections:[]}; }

function activeFaultPreset(fault = {}) {
  const latency = Number(fault.latency_ms) || 0;
  const jitter = Number(fault.jitter_ms) || 0;
  const bandwidth = Number(fault.bandwidth_bytes_per_second) || 0;
  const pauseClient = !!fault.pause_client_to_upstream;
  const pauseServer = !!fault.pause_upstream_to_client;
  if (latency === 0 && jitter === 0 && bandwidth === 0 && !pauseClient && !pauseServer) return 'normal';
  if (latency === 30000 && jitter === 0 && bandwidth === 0 && !pauseClient && !pauseServer) return 'slow';
  if (latency === 55000 && jitter === 0 && bandwidth === 0 && !pauseClient && !pauseServer) return 'very-slow';
  if (latency === 300 && jitter === 250 && bandwidth === 0 && !pauseClient && !pauseServer) return 'unstable';
  if (latency === 0 && jitter === 0 && bandwidth === 0 && (pauseClient || pauseServer)) return 'no-response';
  return 'custom';
}

function profileCard(p) {
  const rt = runtimeOf(p), running = !!rt.running, fault = p.fault_profile || {}, activeFault = activeFaultPreset(fault);
  let html = '<article class="profile-card" data-id="' + esc(p.id) + '">';
  html += '<div class="card-top"><div><h3 class="profile-name">' + esc(p.name) + '</h3><p class="endpoint">' + esc(p.upstream_host) + ':' + p.upstream_port + '</p></div>';
  html += '<span class="status ' + (running ? 'running' : '') + '">' + (running ? '● Running' : '○ Stopped') + '</span></div>';
  html += '<div class="card-meta"><span class="chip">' + (p.transport_label === 'tls_passthrough' ? 'TLS passthrough' : 'Plain TCP') + '</span>';
  html += '<span class="chip">Listen ' + esc(p.bind_host) + ':' + p.listen_port + '</span><span class="chip">' + (rt.active_connections || 0) + ' active</span><span class="chip">' + (p.enabled ? 'Enabled' : 'Disabled') + '</span></div>';
  html += '<div class="card-actions"><button class="small-btn ' + (running ? '' : 'go') + '" data-action="' + (running ? 'stop' : 'start') + '" data-id="' + esc(p.id) + '">' + (running ? 'Stop proxy' : 'Start proxy') + '</button>';
  html += '<button class="small-btn" data-action="edit" data-id="' + esc(p.id) + '"' + (running ? ' disabled title="Stop before editing endpoint"' : '') + '>Edit</button>';
  html += '<button class="small-btn" data-action="duplicate" data-id="' + esc(p.id) + '">Duplicate</button>';
  html += '<button class="small-btn danger" data-action="delete" data-id="' + esc(p.id) + '"' + (running ? ' disabled' : '') + '>Delete</button>';
  if (running) html += '<button class="small-btn danger" data-action="abort" data-id="' + esc(p.id) + '">Abort connections</button>';
  html += '</div>';
  const sequence = p.request_sequence_fault || {enabled:p.request_sequence_enabled,orders:p.request_sequence_orders || [],counter:0,next_request:1};
  const processingEnabled = p.processing_rules_enabled !== false;
  html += '<div class="profile-feature-pair">';
  html += '<section class="profile-feature"><div class="feature-heading"><strong>PROCESSING CODE RULES (DE 3)</strong><span class="feature-status ' + (p.transport_label === 'tcp' && processingEnabled ? 'on' : '') + '">' + (p.transport_label === 'tcp' ? (processingEnabled ? 'Enabled' : 'Disabled') : 'Unavailable · TLS') + '</span></div>';
  html += '<div class="feature-detail">' + (p.transport_label === 'tcp' ? esc((p.processing_codes || []).join(', ') || 'No processing codes configured') : 'Encrypted traffic cannot be inspected') + '</div>';
  if (p.transport_label === 'tcp') html += '<div class="feature-actions"><button class="small-btn" data-action="edit-processing" data-id="' + esc(p.id) + '">Edit</button></div>';
  html += '</section>';
  html += '<section class="profile-feature sequence-profile-panel"><div class="feature-heading"><strong>REQUEST SEQUENCE BLOCKING</strong><span class="feature-status ' + (sequence.enabled ? 'on' : '') + '">' + (sequence.enabled ? 'Enabled' : 'Disabled') + '</span></div>';
  html += '<div class="feature-detail sequence-summary"><span>Blocking Sequences: ' + esc((sequence.orders || []).join(', ') || 'None') + '</span><span>Counter: ' + esc(sequence.counter ?? 0) + ', Next Counter: ' + esc(sequence.next_request ?? ((Number(sequence.counter) || 0) + 1)) + '</span></div>';
  html += '<div class="feature-actions"><button class="small-btn" data-action="reset-sequence" data-id="' + esc(p.id) + '">Reset Counter</button><button class="small-btn" data-action="edit-sequence" data-id="' + esc(p.id) + '">Edit</button></div></section>';
  html += '</div>';
  html += '<div class="fault-panel"><div class="fault-title">LIVE FAULT INJECTION</div><div class="fault-direction"><span>Apply faults to</span><label><input type="radio" name="direction-' + esc(p.id) + '" data-direction="request"' + ((fault.apply_to || 'request') === 'request' ? ' checked' : '') + '> Request (POS → Server)</label><label><input type="radio" name="direction-' + esc(p.id) + '" data-direction="response"' + (fault.apply_to === 'response' ? ' checked' : '') + '> Response (Server → POS)</label><label><input type="radio" name="direction-' + esc(p.id) + '" data-direction="both"' + (fault.apply_to === 'both' ? ' checked' : '') + '> Both</label></div><div class="fault-grid">';
  html += faultInput('Latency (ms)', 'latency_ms', fault.latency_ms || 0);
  html += faultInput('Jitter (ms)', 'jitter_ms', fault.jitter_ms || 0);
  html += faultInput('Bandwidth (B/s)', 'bandwidth_bytes_per_second', fault.bandwidth_bytes_per_second || 0);
  html += '</div><div class="fault-checks">';
  const pauseEnabled = fault.apply_to === 'response' ? fault.pause_upstream_to_client : fault.apply_to === 'both' ? (fault.pause_client_to_upstream || fault.pause_upstream_to_client) : fault.pause_client_to_upstream;
  html += faultCheck('Pause traffic', 'pause_enabled', pauseEnabled);
  html += '</div><div class="apply-row"><button class="small-btn ' + (activeFault === 'normal' ? 'active' : '') + '" data-action="normal" data-id="' + esc(p.id) + '">Normal</button>';
  html += '<button class="small-btn ' + (activeFault === 'slow' ? 'active' : '') + '" data-action="preset" data-preset="slow" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Slow 30s</button>';
  html += '<button class="small-btn ' + (activeFault === 'very-slow' ? 'active' : '') + '" data-action="preset" data-preset="very-slow" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Very slow 55s</button>';
  html += '<button class="small-btn ' + (activeFault === 'unstable' ? 'active' : '') + '" data-action="preset" data-preset="unstable" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Unstable</button>';
  html += '<button class="small-btn ' + (activeFault === 'no-response' ? 'active' : '') + '" data-action="preset" data-preset="no-response" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>No response</button>';
  html += '<button class="small-btn custom-apply ' + (activeFault === 'custom' ? 'active' : '') + '" data-action="apply-fault" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled title="Start proxy first"') + '>Apply custom</button></div></div>';
  if (rt.connections && rt.connections.length) {
    html += '<div class="fault-panel"><div class="fault-title">ACTIVE CONNECTIONS</div>';
    rt.connections.forEach(c => { html += '<div class="endpoint">' + esc(c.client) + ' · POS → Server ' + c.bytes_from_client + ' B · Server → POS ' + c.bytes_from_upstream + ' B</div>'; });
    html += '</div>';
  }
  return html + '</article>';
}
function selectedDirection(card) { return card.querySelector('[data-direction]:checked')?.dataset.direction || 'request'; }
function faultInput(label, key, value) {
  return '<label>' + label + '<input type="number" min="0" max="100000000" data-fault="' + key + '" value="' + value + '"></label>';
}
function faultCheck(label, key, checked) {
  return '<label><input type="checkbox" data-fault="' + key + '"' + (checked ? ' checked' : '') + '> ' + label + '</label>';
}


async function refreshNetworkInterfaces() {
  const button = $('refreshNetworkBtn');
  if (button) { button.disabled = true; button.textContent = 'Scanning…'; }
  try {
    const data = await api('/api/network/interfaces');
    networkInterfaces = data.interfaces || [];
    const select = $('networkInterface');
    const previous = select.value || selectedNetworkIp;
    select.innerHTML = '';
    if (!networkInterfaces.length) {
      select.innerHTML = '<option value="">No usable IPv4 address found</option>';
      selectedNetworkIp = '';
    } else {
      networkInterfaces.forEach(item => {
        const option = document.createElement('option');
        option.value = item.ipv4;
        option.textContent = item.name + ' · ' + item.ipv4 + (item.recommended ? ' (Recommended)' : '');
        select.appendChild(option);
      });
      const chosen = networkInterfaces.find(item => item.ipv4 === previous) ||
        networkInterfaces.find(item => item.recommended) || networkInterfaces[0];
      select.value = chosen.ipv4;
      selectedNetworkIp = chosen.ipv4;
    }
    $('networkScanStatus').textContent = 'Updated ' + new Date().toLocaleTimeString();
    renderPosConnections();
  } catch (e) {
    $('networkScanStatus').textContent = 'IP detection failed';
    toast('Could not detect network interfaces: ' + e.message);
  } finally {
    if (button) { button.disabled = false; button.textContent = '↻ Refresh IP addresses'; }
  }
}

function renderPosConnections() {
  const host = selectedNetworkIp;
  const target = $('posConnectionList');
  if (!host) {
    target.innerHTML = '<div class="empty">No usable IPv4 address found. Connect Wi-Fi or Ethernet, then refresh.</div>';
    return;
  }
  const enabledProfiles = state.filter(p => p.enabled);
  if (!enabledProfiles.length) {
    target.innerHTML = '<div class="empty">Enable a profile to display its POS connection details.</div>';
    return;
  }
  target.innerHTML = enabledProfiles.map(p => {
    const endpoint = host + ':' + p.listen_port;
    const running = !!runtimeOf(p).running;
    return '<article class="pos-connection-card"><div class="pos-connection-top"><strong>' + esc(p.name) + '</strong><span class="status ' + (running ? 'running' : '') + '">' + (running ? '● Running' : '○ Stopped') + '</span></div>' +
      '<p class="pos-instruction">Enter these details in POS Device → Server Configuration</p>' +
      '<div class="pos-endpoint">' + esc(endpoint) + '</div>' +
      '<div class="pos-fields"><span>POS Server IP <b>' + esc(host) + '</b></span><span>POS Server Port <b>' + p.listen_port + '</b></span></div>' +
      '<button class="small-btn copy-endpoint" type="button" data-copy="' + esc(endpoint) + '">Copy IP:Port</button></article>';
  }).join('');
}

function formatEventTimestamp(timestamp) {
  const date = new Date(timestamp * 1000);
  const pad = (value, size = 2) => String(value).padStart(size, '0');
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
    ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds()) +
    '.' + pad(date.getMilliseconds(), 3);
}
async function refreshEvents() {
  const filter = $('eventFilter').value;
  const data = await api('/api/events');
  const allEvents = data.events || [];
  const metadataEvents = allEvents.filter(item => !['RAW_REQUEST', 'RAW_RESPONSE'].includes(item.type));
  const rawEvents = allEvents.filter(item => ['RAW_REQUEST', 'RAW_RESPONSE'].includes(item.type));

  // Attach each raw packet chunk to the nearest matching metadata event
  // from the same connection and direction instead of rendering another row.
  const rawByEvent = new Map();
  for (const raw of rawEvents) {
    const metadataType = raw.type === 'RAW_REQUEST' ? 'REQUEST' : 'RESPONSE';
    const candidates = metadataEvents.filter(item =>
      item.type === metadataType && item.connection_id === raw.connection_id
    );
    if (!candidates.length) continue;
    const nearest = candidates.reduce((best, item) =>
      Math.abs(item.timestamp - raw.timestamp) < Math.abs(best.timestamp - raw.timestamp) ? item : best
    );
    const key = nearest;
    if (!rawByEvent.has(key)) rawByEvent.set(key, []);
    rawByEvent.get(key).push(raw.detail);
  }

  const events = metadataEvents.filter(item =>
    filter === 'all' || (filter === 'REQUEST' ? item.type === 'REQUEST' : item.type === filter)
  );
  const target = $('eventLog');
  target.innerHTML = events.length ? events.slice(-200).sort((a, b) => a.timestamp - b.timestamp).map(item => {
    const attachedRaw = rawByEvent.get(item) || [];
    const rawHtml = attachedRaw.length
      ? '<div class="inline-raw-hex">' + attachedRaw.map(detail => '<div>' + esc(detail) + '</div>').join('') + '</div>'
      : '';
    return '<div class="event-row"><time>' + esc(formatEventTimestamp(item.timestamp)) + '</time><b class="event-type ' + esc(item.type.toLowerCase()) + '">' + esc(item.type) + '</b><span>' + esc(item.profile) + '</span><code>' + esc(item.mti || '-') + '</code><code>' + esc(item.processing_code || '-') + '</code><span>' + esc(item.detail) + rawHtml + '</span></div>';
  }).join('') : '<div class="empty">No matching events yet.</div>';
}
$('eventFilter').addEventListener('change', () => refreshEvents().catch(() => {}));
$('exportEventsBtn').addEventListener('click', () => { window.location.href = '/api/events/export'; });
function setEventsFullscreen(expanded) {
  const panel = document.querySelector('.event-panel');
  panel.classList.toggle('event-panel-fullscreen', expanded);
  document.body.classList.toggle('event-fullscreen-open', expanded);
  $('expandEventsBtn').textContent = expanded ? 'Exit full screen' : 'Full screen';
  $('expandEventsBtn').setAttribute('aria-pressed', String(expanded));
  $('expandEventsBtn').setAttribute('aria-label', expanded ? 'Exit full screen traffic log' : 'Expand traffic log to full screen');
}
$('expandEventsBtn').addEventListener('click', () => {
  const expanded = !$('expandEventsBtn').getAttribute('aria-pressed') || $('expandEventsBtn').getAttribute('aria-pressed') !== 'true';
  setEventsFullscreen(expanded);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.querySelector('.event-panel-fullscreen')) setEventsFullscreen(false);
});
$('clearEventsBtn').addEventListener('click', async () => { await api('/api/events/clear',{method:'POST',body:'{}'}); await refreshEvents(); });

async function refresh() {
  const data = await api('/api/state');
  state = data.profiles || [];
  $('profileList').innerHTML = state.length ? state.map(profileCard).join('') : '<div class="empty">No profiles yet. Add your first UAT endpoint to get started.</div>';
  $('profileCount').textContent = state.length;
  $('runningCount').textContent = state.filter(p => runtimeOf(p).running).length;
  $('connectionCount').textContent = state.reduce((n,p) => n + (runtimeOf(p).active_connections || 0), 0);
  renderPosConnections();
  refreshEvents().catch(() => {});
}

function openDialog(profile = null) {
  $('profileForm').dataset.mode = profile ? 'edit' : 'create';
  $('dialogTitle').textContent = profile ? 'Edit profile' : 'Add profile';
  $('profileId').value = profile?.id || '';
  $('profileName').value = profile?.name || '';
  $('transport').value = profile?.transport_label || 'tcp';
  $('upstreamHost').value = profile?.upstream_host || '';
  $('upstreamPort').value = profile?.upstream_port || 9000;
  $('listenPort').value = profile?.listen_port || 8666;
  $('bindHost').value = profile?.bind_host || '127.0.0.1';
  $('connectTimeout').value = profile?.connect_timeout_ms || 10000;
  $('notes').value = profile?.notes || '';
  $('enabled').checked = profile?.enabled ?? true;
  $('rawHexLogging').checked = profile?.raw_hex_logging ?? false;
  $('profileDialog').showModal();
}

function formPayload(id) {
  const existing = state.find(profile => profile.id === id);
  return {id: id || undefined, name:$('profileName').value.trim(), transport_label:$('transport').value,
    request_sequence_enabled:existing?.request_sequence_enabled ?? false,
    request_sequence_orders:existing?.request_sequence_orders || [],
    processing_rules_enabled:existing?.processing_rules_enabled ?? true,
    processing_codes:existing?.processing_codes || [],
    upstream_host:$('upstreamHost').value.trim(), upstream_port:Number($('upstreamPort').value),
    listen_port:Number($('listenPort').value), bind_host:$('bindHost').value,
    connect_timeout_ms:Number($('connectTimeout').value), notes:$('notes').value.trim(), enabled:$('enabled').checked,
    raw_hex_logging:$('rawHexLogging').checked,
    fault_profile:{apply_to:'request',latency_ms:0,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false}};
}

$('profileForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const id = $('profileId').value, payload = formPayload(id);
    await api(id ? '/api/profiles/' + encodeURIComponent(id) : '/api/profiles',
      {method:id ? 'PUT' : 'POST',body:JSON.stringify(payload)});
    $('profileDialog').close(); await refresh(); toast('Profile saved');
  } catch(e) { toast(e.message); }
});

$('profileList').addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const id = button.dataset.id, action = button.dataset.action, profile = state.find(p => p.id === id);
  try {
    if (action === 'edit') openDialog(profile);
    else if (action === 'edit-processing') openFeatureDialog('processing', profile);
    else if (action === 'edit-sequence') openFeatureDialog('sequence', profile);
    else if (action === 'reset-sequence') {
      if (confirm('Reset the request counter for profile "' + profile.name + '" to 0?')) {
        await api('/api/profiles/' + encodeURIComponent(id) + '/request-sequence-fault/reset', {method:'POST',body:'{}'});
        await refresh(); toast('Request counter reset for ' + profile.name);
      }
    }
    else if (action === 'preset') {
      const presets = {
        slow: {latency_ms:30000,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        'very-slow': {latency_ms:55000,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        unstable: {latency_ms:300,jitter_ms:250,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        'no-response': {latency_ms:0,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:true}
      };
      const preset = presets[button.dataset.preset];
      preset.apply_to = selectedDirection(button.closest('.profile-card'));
      preset.pause_client_to_upstream = button.dataset.preset === 'no-response' && (preset.apply_to === 'request' || preset.apply_to === 'both');
      preset.pause_upstream_to_client = button.dataset.preset === 'no-response' && (preset.apply_to === 'response' || preset.apply_to === 'both');
      await api('/api/profiles/' + encodeURIComponent(id) + '/fault',{method:'POST',body:JSON.stringify(preset)});
      await refresh(); toast('Scenario applied: ' + button.textContent);
    }
    else if (action === 'duplicate') {
      const copy = {...profile,id:undefined,name:profile.name + ' Copy',listen_port:profile.listen_port + 1,enabled:false};
      delete copy.runtime;
      await api('/api/profiles',{method:'POST',body:JSON.stringify(copy)});
      await refresh(); toast('Profile duplicated; review its listener port');
    } else if (action === 'delete') {
      if (confirm('Delete profile "' + profile.name + '"?')) {
        await api('/api/profiles/' + encodeURIComponent(id),{method:'DELETE'}); await refresh(); toast('Profile deleted');
      }
    } else if (action === 'start') {
      await api('/api/profiles/' + encodeURIComponent(id) + '/start',{method:'POST',body:'{}'}); await refresh(); toast('Proxy started');
    } else if (action === 'stop') {
      await api('/api/profiles/' + encodeURIComponent(id) + '/stop',{method:'POST',body:'{}'}); await refresh(); toast('Proxy stopped');
    } else if (action === 'abort') {
      const result = await api('/api/profiles/' + encodeURIComponent(id) + '/abort',{method:'POST',body:'{}'});
      await refresh(); toast('Closed ' + result.sockets_closed + ' sockets');
    } else if (action === 'normal') {
      await api('/api/profiles/' + encodeURIComponent(id) + '/fault',{method:'POST',body:JSON.stringify({
        latency_ms:0,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false
      })});
      await refresh(); toast('Normal forwarding restored');
    } else if (action === 'apply-fault') {
      const card = button.closest('.profile-card'), payload = {};
      payload.apply_to = selectedDirection(card);
      card.querySelectorAll('[data-fault]').forEach(input => {
        if (input.dataset.fault === 'pause_enabled') return;
        payload[input.dataset.fault] = input.type === 'checkbox' ? input.checked : Number(input.value);
      });
      const pause = card.querySelector('[data-fault="pause_enabled"]').checked;
      payload.pause_client_to_upstream = pause && (payload.apply_to === 'request' || payload.apply_to === 'both');
      payload.pause_upstream_to_client = pause && (payload.apply_to === 'response' || payload.apply_to === 'both');
      await api('/api/profiles/' + encodeURIComponent(id) + '/fault',{method:'POST',body:JSON.stringify(payload)});
      await refresh(); toast('Fault settings applied live');
    }
  } catch(e) { toast(e.message); }
});

function openFeatureDialog(type, profile) {
  const sequence = profile.request_sequence_fault || {enabled:profile.request_sequence_enabled,orders:profile.request_sequence_orders || []};
  $('featureDialogTitle').textContent = type === 'processing' ? 'Processing Code Rules (DE 3)' : 'Request Sequence Blocking';
  $('featureDialogType').value = type;
  $('featureDialogProfileId').value = profile.id;
  $('featureEnabled').checked = type === 'processing' ? profile.processing_rules_enabled !== false : !!sequence.enabled;
  $('featureValuesLabel').textContent = type === 'processing' ? 'Processing Codes (6 digits, comma-separated)' : 'Block request numbers (comma-separated)';
  $('featureValues').value = type === 'processing' ? (profile.processing_codes || []).join(', ') : (sequence.orders || []).join(', ');
  $('featureValues').placeholder = type === 'processing' ? '000000, 003000' : '2, 3, 5';
  $('featureDialog').showModal();
}
$('featureForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('featureDialogProfileId').value, type = $('featureDialogType').value, raw = $('featureValues').value.trim();
  try {
    if (type === 'processing') {
      const codes = raw ? raw.split(/[ ,;\n]+/).map(value => value.trim()).filter(Boolean) : [];
      if (codes.some(value => !/^\d{6}$/.test(value))) throw new Error('Each Processing Code must contain exactly 6 digits');
      await api('/api/profiles/' + encodeURIComponent(id) + '/processing-codes', {method:'POST',body:JSON.stringify({processing_codes:codes,enabled:$('featureEnabled').checked})});
    } else {
      const orders = raw ? raw.split(',').map(value => value.trim()).filter(Boolean) : [];
      if (orders.some(value => !/^\d+$/.test(value) || Number(value) < 1)) throw new Error('Enter positive request numbers separated by commas, for example: 2, 3, 5');
      await api('/api/profiles/' + encodeURIComponent(id) + '/request-sequence-fault', {method:'POST',body:JSON.stringify({enabled:$('featureEnabled').checked,orders})});
    }
    $('featureDialog').close(); await refresh(); toast('Settings saved');
  } catch(e) { toast(e.message); }
});
$('closeFeatureDialog').addEventListener('click', () => $('featureDialog').close());
$('cancelFeatureDialog').addEventListener('click', () => $('featureDialog').close());

$('addProfileBtn').addEventListener('click', () => openDialog());
$('closeDialog').addEventListener('click', () => $('profileDialog').close());
$('cancelDialog').addEventListener('click', () => $('profileDialog').close());
$('refreshBtn').addEventListener('click', () => refresh().catch(e => toast(e.message)));
$('refreshNetworkBtn').addEventListener('click', refreshNetworkInterfaces);
$('networkInterface').addEventListener('change', event => {
  selectedNetworkIp = event.target.value;
  renderPosConnections();
});
$('posConnectionList').addEventListener('click', event => {
  const button = event.target.closest('[data-copy]');
  if (!button) return;
  const value = button.dataset.copy;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(value).then(() => toast('Copied ' + value)).catch(() => toast('Could not copy IP:Port'));
  } else {
    const field = document.createElement('textarea');
    field.value = value; document.body.appendChild(field); field.select();
    try { document.execCommand('copy'); toast('Copied ' + value); } catch (_) { toast('Could not copy IP:Port'); }
    field.remove();
  }
});
$('startAllBtn').addEventListener('click', async () => {
  try {
    const result = await api('/api/profiles/start-all',{method:'POST',body:'{}'});
    await refresh();
    const failed = result.results.filter(item => !item.ok);
    toast(failed.length ? (failed.length + ' profile(s) could not start') : 'All enabled profiles started');
  } catch(e) { toast(e.message); }
});
$('stopAllBtn').addEventListener('click', async () => {
  try { await api('/api/profiles/stop-all',{method:'POST',body:'{}'}); await refresh(); toast('All proxies stopped'); }
  catch(e) { toast(e.message); }
});
$('exportBtn').addEventListener('click', () => { window.location.href = '/api/profiles/export'; });
$('importFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const content = JSON.parse(await file.text());
    const merge = confirm('OK = merge profiles (keep existing). Cancel = replace all profiles.');
    await api('/api/profiles/import' + (merge ? '' : '?mode=replace'),{method:'POST',body:JSON.stringify(content)});
    await refresh(); toast('Profiles imported');
  } catch(e) { toast(e.message); }
  finally { event.target.value = ''; }
});
refresh().catch(e => toast(e.message));
refreshNetworkInterfaces();
setInterval(() => { refreshEvents().catch(() => {}); }, 1500);
setInterval(() => {
  const list = $('profileList');
  if (!list.contains(document.activeElement) && !$('profileDialog').open) refresh().catch(() => {});
}, 4000);
