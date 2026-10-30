const $ = (id) => document.getElementById(id);
let state = [];
let toastTimer;

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

function profileCard(p) {
  const rt = runtimeOf(p), running = !!rt.running, fault = p.fault_profile || {};
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
  html += '</div><div class="fault-panel"><div class="fault-title">LIVE FAULT INJECTION</div><div class="fault-grid">';
  html += faultInput('Latency (ms)', 'latency_ms', fault.latency_ms || 0);
  html += faultInput('Jitter (ms)', 'jitter_ms', fault.jitter_ms || 0);
  html += faultInput('Bandwidth (B/s)', 'bandwidth_bytes_per_second', fault.bandwidth_bytes_per_second || 0);
  html += '</div><div class="fault-checks">';
  html += faultCheck('Pause POS → Server', 'pause_client_to_upstream', fault.pause_client_to_upstream);
  html += faultCheck('Pause Server → POS', 'pause_upstream_to_client', fault.pause_upstream_to_client);
  html += '</div><div class="apply-row"><button class="small-btn" data-action="normal" data-id="' + esc(p.id) + '">Normal</button>';
  html += '<button class="small-btn" data-action="preset" data-preset="slow" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Slow 500ms</button>';
  html += '<button class="small-btn" data-action="preset" data-preset="very-slow" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Very slow 2s</button>';
  html += '<button class="small-btn" data-action="preset" data-preset="unstable" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>Unstable</button>';
  html += '<button class="small-btn" data-action="preset" data-preset="no-response" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled') + '>No response</button>';
  html += '<button class="small-btn go" data-action="apply-fault" data-id="' + esc(p.id) + '"' + (running ? '' : ' disabled title="Start proxy first"') + '>Apply custom</button></div></div>';
  if (rt.connections && rt.connections.length) {
    html += '<div class="fault-panel"><div class="fault-title">ACTIVE CONNECTIONS</div>';
    rt.connections.forEach(c => { html += '<div class="endpoint">' + esc(c.client) + ' · POS → Server ' + c.bytes_from_client + ' B · Server → POS ' + c.bytes_from_upstream + ' B</div>'; });
    html += '</div>';
  }
  return html + '</article>';
}
function faultInput(label, key, value) {
  return '<label>' + label + '<input type="number" min="0" max="100000000" data-fault="' + key + '" value="' + value + '"></label>';
}
function faultCheck(label, key, checked) {
  return '<label><input type="checkbox" data-fault="' + key + '"' + (checked ? ' checked' : '') + '> ' + label + '</label>';
}

async function refresh() {
  const data = await api('/api/state');
  state = data.profiles || [];
  $('profileList').innerHTML = state.length ? state.map(profileCard).join('') : '<div class="empty">No profiles yet. Add your first UAT endpoint to get started.</div>';
  $('profileCount').textContent = state.length;
  $('runningCount').textContent = state.filter(p => runtimeOf(p).running).length;
  $('connectionCount').textContent = state.reduce((n,p) => n + (runtimeOf(p).active_connections || 0), 0);
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
  $('profileDialog').showModal();
}

function formPayload(id) {
  return {id: id || undefined, name:$('profileName').value.trim(), transport_label:$('transport').value,
    upstream_host:$('upstreamHost').value.trim(), upstream_port:Number($('upstreamPort').value),
    listen_port:Number($('listenPort').value), bind_host:$('bindHost').value,
    connect_timeout_ms:Number($('connectTimeout').value), notes:$('notes').value.trim(), enabled:$('enabled').checked,
    fault_profile:{latency_ms:0,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false}};
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
    else if (action === 'preset') {
      const presets = {
        slow: {latency_ms:500,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        'very-slow': {latency_ms:2000,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        unstable: {latency_ms:300,jitter_ms:250,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:false},
        'no-response': {latency_ms:0,jitter_ms:0,bandwidth_bytes_per_second:0,pause_client_to_upstream:false,pause_upstream_to_client:true}
      };
      await api('/api/profiles/' + encodeURIComponent(id) + '/fault',{method:'POST',body:JSON.stringify(presets[button.dataset.preset])});
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
      card.querySelectorAll('[data-fault]').forEach(input => {
        payload[input.dataset.fault] = input.type === 'checkbox' ? input.checked : Number(input.value);
      });
      await api('/api/profiles/' + encodeURIComponent(id) + '/fault',{method:'POST',body:JSON.stringify(payload)});
      await refresh(); toast('Fault settings applied live');
    }
  } catch(e) { toast(e.message); }
});

$('addProfileBtn').addEventListener('click', () => openDialog());
$('closeDialog').addEventListener('click', () => $('profileDialog').close());
$('cancelDialog').addEventListener('click', () => $('profileDialog').close());
$('refreshBtn').addEventListener('click', () => refresh().catch(e => toast(e.message)));
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
setInterval(() => {
  const list = $('profileList');
  if (!list.contains(document.activeElement) && !$('profileDialog').open) refresh().catch(() => {});
}, 4000);
