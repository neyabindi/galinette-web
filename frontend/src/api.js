/**
 * Client API Galinette — wrappers fetch avec cookies + erreurs typées.
 */

async function request(path, opts = {}) {
  const res = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
    ...opts,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {}
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.blob();
}

export const api = {
  // Auth
  login: (username, password) =>
    request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),

  // Serveurs
  listServers: () => request('/api/servers'),
  addServer: (name) =>
    request('/api/servers', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  removeServer: (name) =>
    request(`/api/servers/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  serverHealth: () => request('/api/servers/health'),

  // Sessions
  listSessions: () => request('/api/sessions'),
  disconnect: (server, sid) =>
    request(`/api/sessions/${server}/${sid}/disconnect`, { method: 'POST' }),
  logoff: (server, sid) =>
    request(`/api/sessions/${server}/${sid}/logoff`, { method: 'POST' }),
  sendMessage: (server, sid, body, title = 'Information administrateur') =>
    request(`/api/sessions/${server}/${sid}/message`, {
      method: 'POST',
      body: JSON.stringify({ title, body }),
    }),
  processes: (server, sid) =>
    request(`/api/sessions/${server}/${sid}/processes`),

  // Shadow : télécharge le .rdp
  shadowUrl: (server, sid, mode = 'force-control') =>
    `/api/sessions/${server}/${sid}/shadow?mode=${mode}`,

  // AD
  unlock: (sam) =>
    request(`/api/users/${encodeURIComponent(sam)}/unlock`, { method: 'POST' }),
  history: (sam) =>
    request(`/api/users/${encodeURIComponent(sam)}/history`),

  // Audit
  audit: (limit = 500, q = '') =>
    request(`/api/audit?limit=${limit}&q=${encodeURIComponent(q)}`),
};
