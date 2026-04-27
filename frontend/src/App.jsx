import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { api } from './api.js';
import {
  LayoutDashboard, MonitorSmartphone, Server, Shield, LogOut, RefreshCw,
  Search, Eye, MousePointer2, EyeOff, ShieldAlert, MessageSquare, Power,
  Camera, X, Send, AlertTriangle, CheckCircle2, Wifi, Plus, Trash2,
  Terminal, ChevronRight, Unlock, History, FileSpreadsheet, MoreHorizontal,
  Cpu, Activity, Clock, UserCircle2, Lock, FileBox,
} from 'lucide-react';

// ============================================================
// Design tokens
// ============================================================
const STATE = {
  active:       { dot: 'bg-emerald-400', text: 'text-emerald-300', bg: 'bg-emerald-400/10', label: 'active' },
  idle:         { dot: 'bg-amber-400',   text: 'text-amber-300',   bg: 'bg-amber-400/10',   label: 'inactive' },
  disconnected: { dot: 'bg-zinc-500',    text: 'text-zinc-400',    bg: 'bg-zinc-500/10',    label: 'déco.' },
  unknown:      { dot: 'bg-zinc-600',    text: 'text-zinc-500',    bg: 'bg-zinc-500/10',    label: '?' },
};

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'sessions',  label: 'Sessions',  icon: MonitorSmartphone },
  { id: 'servers',   label: 'Serveurs',  icon: Server },
  { id: 'audit',     label: 'Audit',     icon: Shield },
];

function useToasts() {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((msg, kind = 'ok') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);
  return { toasts, push };
}

// ============================================================
// Login
// ============================================================
function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.login(username, password);
      onLogin();
    } catch (err) {
      setError(err.message || 'Échec de connexion');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-900 p-4">
      <div className="w-[380px]">
        <div className="flex items-center gap-3 mb-8 justify-center">
          <div className="relative">
            <div className="w-8 h-8 bg-amber-400 rotate-45" />
          </div>
          <div>
            <div className="font-display text-2xl text-zinc-100 leading-none">Galinette</div>
            <div className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 mt-1">RDS console</div>
          </div>
        </div>

        <form onSubmit={submit} className="bg-zinc-950 border border-zinc-800 p-6 space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 mb-1 block">
              Identifiant administrateur
            </label>
            <input
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="adm-monprenom"
              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-400/60 focus:outline-none px-3 py-2 text-sm text-zinc-100 font-mono"
              disabled={loading}
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 mb-1 block">
              Mot de passe
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-400/60 focus:outline-none px-3 py-2 text-sm text-zinc-100 font-mono"
              disabled={loading}
            />
          </div>
          {error && (
            <div className="flex items-center gap-2 px-3 py-2 bg-rose-400/10 border border-rose-400/30 text-rose-300 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full py-2 bg-amber-400 text-zinc-950 font-medium text-sm hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Authentification…' : 'Se connecter'}
          </button>
          <div className="text-[10px] text-zinc-600 text-center font-mono">
            authentification Active Directory · groupe.avlo
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================
// Shell
// ============================================================
const AUTO_REFRESH_MS = 15 * 60 * 1000; // 15 minutes

function Shell({ user, onLogout }) {
  const [view, setView] = useState('sessions');
  const { toasts, push } = useToasts();

  // États globaux persistants (ne disparaissent pas au changement d'onglet)
  const [sessions, setSessions] = useState([]);
  const [sessionErrors, setSessionErrors] = useState([]);
  const [health, setHealth] = useState([]);
  const [serverList, setServerList] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const firstLoad = useRef(true);

  // Merge intelligent des sessions
  const mergeSessions = useCallback((fresh) => {
    setSessions((prev) => {
      const byKey = new Map(prev.map((s) => [`${s.server}:${s.session_id}`, s]));
      const result = [];
      for (const f of fresh) {
        const k = `${f.server}:${f.session_id}`;
        const old = byKey.get(k);
        if (old &&
            old.state === f.state &&
            old.idle_time === f.idle_time &&
            old.user === f.user) {
          result.push(old);
        } else {
          result.push(f);
        }
      }
      return result;
    });
  }, []);

  const refreshInFlight = useRef(false);

  const refreshAll = useCallback(async (manual = false) => {
    if (refreshInFlight.current) {
      if (manual) push('Rafraîchissement déjà en cours…', 'warn');
      return;
    }
    refreshInFlight.current = true;
    setRefreshing(true);
    try {
      // Toutes les requêtes en parallèle
      const [sess, h, srvs, aud] = await Promise.allSettled([
        api.listSessions(),
        api.serverHealth(),
        api.listServers(),
        api.audit(500),
      ]);
      if (sess.status === 'fulfilled') {
        mergeSessions(sess.value.sessions || []);
        setSessionErrors(sess.value.errors || []);
      }
      if (h.status === 'fulfilled')    setHealth(h.value.servers || []);
      if (srvs.status === 'fulfilled') setServerList(srvs.value.servers || []);
      if (aud.status === 'fulfilled')  setAuditEvents(aud.value.events || []);
      setLastRefresh(new Date());
      if (manual) push('Données rafraîchies');
    } catch (e) {
      push(e.message, 'err');
    } finally {
      setRefreshing(false);
      firstLoad.current = false;
      refreshInFlight.current = false;
    }
  }, [mergeSessions, push]);

  useEffect(() => {
    refreshAll();
    const id = setInterval(() => refreshAll(false), AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [refreshAll]);

  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-200">
      <header className="sticky top-0 z-30 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-xl">
        <div className="flex items-center h-12 px-4 gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-amber-400 rotate-45" />
            <div className="leading-none">
              <div className="font-display text-lg text-zinc-100 tracking-tight">Galinette</div>
              <div className="text-[9px] uppercase tracking-[0.25em] text-zinc-500 -mt-0.5">RDS console</div>
            </div>
          </div>
          <div className="h-5 w-px bg-zinc-800" />
          <nav className="flex items-center gap-0.5">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={() => setView(n.id)}
                className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium transition-colors ${
                  view === n.id
                    ? 'bg-amber-400/10 text-amber-300'
                    : 'text-zinc-400 hover:text-zinc-100'
                }`}
              >
                <n.icon className="w-3.5 h-3.5" />
                {n.label}
              </button>
            ))}
          </nav>
          <div className="flex-1" />
          <div className="flex items-center gap-3 text-xs">
            {lastRefresh && (
              <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 font-mono">
                <Wifi className={`w-3 h-3 ${refreshing ? 'text-amber-400 animate-pulse' : 'text-emerald-400'}`} />
                <span>MAJ {lastRefresh.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
            )}
            <button
              onClick={() => refreshAll(true)}
              disabled={refreshing}
              title="Rafraîchir maintenant (auto toutes les 15 min)"
              className="p-1.5 text-zinc-400 hover:text-amber-300 disabled:opacity-40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-zinc-800 flex items-center justify-center">
                <UserCircle2 className="w-4 h-4 text-zinc-400" />
              </div>
              <div className="leading-none">
                <div className="text-[11px] text-zinc-200 font-mono">{user.username}</div>
                <div className="text-[9px] text-zinc-500 uppercase tracking-wider">{user.domain}</div>
              </div>
            </div>
            <button
              onClick={onLogout}
              title="Se déconnecter"
              className="p-1.5 text-zinc-400 hover:text-rose-300 hover:bg-rose-400/10"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="p-4">
        {view === 'dashboard' && (
          <Dashboard health={health} sessions={sessions} refreshing={refreshing} onRefresh={() => refreshAll(true)} />
        )}
        {view === 'sessions' && (
          <Sessions
            push={push}
            sessions={sessions}
            errors={sessionErrors}
            loading={firstLoad.current && refreshing}
            refreshing={refreshing}
            onRefresh={() => refreshAll(true)}
            onActionDone={() => refreshAll(false)}
          />
        )}
        {view === 'servers' && (
          <Servers push={push} servers={serverList} onChanged={() => refreshAll(false)} />
        )}
        {view === 'audit' && <Audit events={auditEvents} />}
      </main>

      <div className="fixed bottom-4 right-4 space-y-2 z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-2 border text-sm font-mono shadow-xl flex items-center gap-2 ${
              t.kind === 'err'
                ? 'bg-rose-400/10 border-rose-400/40 text-rose-200'
                : t.kind === 'warn'
                ? 'bg-amber-400/10 border-amber-400/40 text-amber-200'
                : 'bg-emerald-400/10 border-emerald-400/40 text-emerald-200'
            }`}
          >
            {t.kind === 'err' ? (
              <AlertTriangle className="w-4 h-4" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Dashboard
// ============================================================
function Dashboard({ health, sessions, refreshing, onRefresh }) {
  const reachable = health.filter((s) => s.reachable).length;
  const active = sessions.filter((s) => s.state === 'active').length;
  const disc = sessions.filter((s) => s.state === 'disconnected').length;
  const avgCpu = health.length
    ? Math.round(
        health.filter((s) => s.reachable).reduce((a, s) => a + (s.cpu_pct || 0), 0) /
          Math.max(1, reachable)
      )
    : 0;
  const downServers = health.filter((s) => !s.reachable).map((s) => s.name);

  return (
    <div className="space-y-4">
      {downServers.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-rose-400/5 border border-rose-400/30 text-xs text-rose-300">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>
            <span className="font-medium">{downServers.length} serveur(s) hors-ligne :</span>{' '}
            <span className="font-mono">{downServers.join(', ')}</span>
          </span>
        </div>
      )}
      <div className="grid grid-cols-4 gap-px bg-zinc-800/50 border border-zinc-800">
        <Kpi label="Sessions totales" value={sessions.length} sub={`${active} actives · ${disc} déco.`} />
        <Kpi
          label="Hôtes joignables"
          value={`${reachable}/${health.length}`}
          sub={downServers.length ? `${downServers.length} hors-ligne` : 'ferme'}
        />
        <Kpi label="CPU moyen" value={`${avgCpu}%`} sub="hôtes joignables" />
        <Kpi label="Auto-refresh" value="15 min" sub="ou ↻ manuel" />
      </div>

      <div className="border border-zinc-800 bg-zinc-950">
        <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
          <h3 className="text-[11px] uppercase tracking-[0.15em] text-zinc-400 font-medium">
            État de la ferme
          </h3>
          <button onClick={onRefresh} className="text-xs text-zinc-400 hover:text-amber-300 flex items-center gap-1">
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} /> Rafraîchir
          </button>
        </div>
        {/* Header columns */}
        <div className="grid grid-cols-12 gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.15em] text-zinc-500 font-medium border-b border-zinc-800/60 bg-zinc-900/30">
          <div className="col-span-2">Serveur</div>
          <div className="col-span-1">Système</div>
          <div className="col-span-1">État</div>
          <div className="col-span-2">Sessions</div>
          <div className="col-span-2">CPU</div>
          <div className="col-span-2">RAM</div>
          <div className="col-span-1">Disque C:</div>
          <div className="col-span-1 text-right">Uptime</div>
        </div>
        <div className="divide-y divide-zinc-800/80">
          {health.map((s) => {
            const srvSessions = sessions.filter((x) => x.server?.toUpperCase() === s.name?.toUpperCase());
            const nbActive = srvSessions.filter((x) => x.state === 'active').length;
            const nbIdle   = srvSessions.filter((x) => x.state === 'idle').length;
            const nbDisc   = srvSessions.filter((x) => x.state === 'disconnected').length;
            const ramTip = s.ram_total_gb ? `${s.ram_used_gb} / ${s.ram_total_gb} Go utilisés` : '';
            const diskTip = s.disk_total_gb
              ? `${s.disk_used_gb} / ${s.disk_total_gb} Go utilisés (${s.disk_free_gb} Go libres)`
              : '';
            return (
              <div key={s.name} className="grid grid-cols-12 gap-3 py-2.5 px-3 items-center hover:bg-zinc-900/50">
                <div className="col-span-2 flex items-center gap-2">
                  <Server className="w-3.5 h-3.5 text-zinc-500" />
                  <span className="font-mono text-sm">{s.name}</span>
                </div>
                <div className="col-span-1 text-xs text-zinc-400">{s.os || '-'}</div>
                <div className="col-span-1 text-xs">
                  {s.reachable ? (
                    <span className="text-emerald-300">● en ligne</span>
                  ) : (
                    <span className="text-rose-300">● hors-ligne</span>
                  )}
                </div>
                <div className="col-span-2 flex items-center gap-1.5 text-xs font-mono tabular-nums" title="Actives · Inactives · Déconnectées">
                  <span className="text-emerald-300">{nbActive}<span className="text-zinc-500 ml-0.5">act.</span></span>
                  <span className="text-amber-300">{nbIdle}<span className="text-zinc-500 ml-0.5">inact.</span></span>
                  <span className="text-zinc-400">{nbDisc}<span className="text-zinc-500 ml-0.5">déc.</span></span>
                </div>
                <div className="col-span-2">
                  <Bar value={s.cpu_pct || 0} />
                </div>
                <div className="col-span-2" title={ramTip}>
                  <Bar value={s.ram_pct || 0} />
                </div>
                <div className="col-span-1" title={diskTip}>
                  <Bar value={s.disk_pct || 0} warn={80} crit={90} />
                </div>
                <div className="col-span-1 text-xs text-zinc-500 font-mono text-right">{s.uptime || '-'}</div>
              </div>
            );
          })}
          {!health.length && (
            <div className="p-8 text-center text-sm text-zinc-500">
              Aucun serveur configuré.{' '}
              <span className="text-amber-300">Ajoutez-en depuis l'onglet « Serveurs »</span>.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub }) {
  return (
    <div className="bg-zinc-950 p-4">
      <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 font-medium mb-1">{label}</div>
      <div className="text-3xl font-semibold tabular-nums text-zinc-100">{value}</div>
      <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>
    </div>
  );
}

function Bar({ value, warn = 70, crit = 85 }) {
  const color = value >= crit ? 'bg-rose-400' : value >= warn ? 'bg-amber-400' : 'bg-emerald-400';
  return (
    <div className="flex items-center gap-2">
      <div className="w-full h-1.5 bg-zinc-800 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="tabular-nums text-[11px] text-zinc-400 w-9 text-right">{value}%</span>
    </div>
  );
}

// ============================================================
// Sessions
// ============================================================
function Sessions({ push, sessions, errors, loading, refreshing, onRefresh, onActionDone }) {
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [ctxMenu, setCtxMenu] = useState(null);
  const [historyFor, setHistoryFor] = useState(null);
  const [messageFor, setMessageFor] = useState(null);
  const [sortKey, setSortKey] = useState('user');
  const [sortDir, setSortDir] = useState('asc');

  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [ctxMenu]);

  function toggleSort(key) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  }

  const filtered = useMemo(() => {
    const list = sessions.filter((s) => {
      if (filter !== 'all' && s.state !== filter) return false;
      if (query) {
        const hay = `${s.user} ${s.server} ${s.session_name}`.toLowerCase();
        if (!hay.includes(query.toLowerCase())) return false;
      }
      return true;
    });
    // Ordre d'états cohérent pour le tri état
    const stateOrder = { active: 0, idle: 1, disconnected: 2, unknown: 3 };
    const cmp = (a, b) => {
      let av, bv;
      switch (sortKey) {
        case 'state':       av = stateOrder[a.state] ?? 9; bv = stateOrder[b.state] ?? 9; break;
        case 'id':          av = a.session_id; bv = b.session_id; break;
        case 'user':        av = (a.user || '').toLowerCase(); bv = (b.user || '').toLowerCase(); break;
        case 'server':      av = (a.server || '').toLowerCase(); bv = (b.server || '').toLowerCase(); break;
        case 'session':     av = (a.session_name || '').toLowerCase(); bv = (b.session_name || '').toLowerCase(); break;
        case 'logon':       av = a.logon_time || ''; bv = b.logon_time || ''; break;
        case 'idle': {
          // parse "12 min" → 12 ; "-" → -1
          const p = (v) => { const m = /(\d+)/.exec(v || ''); return m ? parseInt(m[1]) : -1; };
          av = p(a.idle_time); bv = p(b.idle_time); break;
        }
        default: av = ''; bv = '';
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    };
    return [...list].sort(cmp);
  }, [sessions, filter, query, sortKey, sortDir]);

  function keyOf(s) { return `${s.server}:${s.session_id}`; }
  function toggle(s) {
    const k = keyOf(s);
    const n = new Set(selected);
    n.has(k) ? n.delete(k) : n.add(k);
    setSelected(n);
  }
  function toggleAll() {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map(keyOf)));
  }

  async function doAction(action, s, opt = {}) {
    try {
      if (action.startsWith('shadow-')) {
        const mode = action.replace('shadow-', '');
        // Téléchargement du .rdp
        window.location.href = api.shadowUrl(s.server, s.session_id, mode);
        push(`Shadow ${mode} — ${s.user}`);
        return;
      }
      if (action === 'disconnect') { await api.disconnect(s.server, s.session_id); push(`${s.user} déconnecté`); }
      else if (action === 'logoff') { await api.logoff(s.server, s.session_id); push(`Session fermée : ${s.user}`, 'warn'); }
      else if (action === 'message') { setMessageFor(s); return; }
      else if (action === 'unlock') { await api.unlock(s.user); push(`${s.user} déverrouillé`); }
      else if (action === 'history') { setHistoryFor(s); return; }
      else if (action === 'copy') {
        const info = [
          `Utilisateur : ${s.user}`,
          `Serveur     : ${s.server}`,
          `ID session  : ${s.session_id}`,
          `État        : ${s.state}`,
          `Nom session : ${s.session_name || '-'}`,
          `Ouverture   : ${s.logon_time || '-'}`,
          `Inactif     : ${s.idle_time || '-'}`,
        ].join('\n');
        let copied = false;
        // Méthode moderne (HTTPS ou localhost)
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(info);
            copied = true;
          } catch {}
        }
        // Fallback HTTP : textarea temporaire + execCommand
        if (!copied) {
          try {
            const ta = document.createElement('textarea');
            ta.value = info;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            copied = document.execCommand('copy');
            document.body.removeChild(ta);
          } catch {}
        }
        push(copied ? `Infos de ${s.user} copiées` : 'Copie impossible', copied ? 'ok' : 'err');
        return;
      }
      setTimeout(onActionDone, 800);
    } catch (e) {
      push(e.message, 'err');
    }
  }

  function onContext(e, s) {
    e.preventDefault();
    setCtxMenu({ x: Math.min(e.clientX, window.innerWidth - 300), y: Math.min(e.clientY, window.innerHeight - 380), session: s });
  }

  function exportCsv() {
    const headers = ['server', 'session_id', 'user', 'state', 'idle_time', 'logon_time'];
    const rows = filtered.map((s) => headers.map((h) => s[h] ?? '').join(';'));
    const blob = new Blob([headers.join(';') + '\n' + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sessions_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3">
      {/* toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[280px]">
          <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-zinc-500" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher utilisateur ou serveur…"
            className="w-full bg-zinc-950 border border-zinc-800 focus:border-amber-400/60 focus:outline-none pl-8 pr-3 py-1.5 text-sm text-zinc-100 font-mono"
          />
        </div>
        <div className="flex border border-zinc-800 divide-x divide-zinc-800">
          {['all', 'active', 'idle', 'disconnected'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs uppercase tracking-wider ${
                filter === f ? 'bg-zinc-800 text-amber-300' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
              }`}
            >
              {f === 'all' ? 'toutes' : f === 'active' ? 'actives' : f === 'idle' ? 'inactives' : 'déco.'}
            </button>
          ))}
        </div>
        <button onClick={exportCsv} className="flex items-center gap-1.5 px-3 py-1.5 border border-zinc-800 text-xs text-zinc-300 hover:text-amber-300 hover:bg-zinc-900">
          <FileSpreadsheet className="w-3.5 h-3.5" /> Exporter
        </button>
        <button onClick={onRefresh} title="Rafraîchir" className="p-1.5 border border-zinc-800 text-zinc-400 hover:text-zinc-200">
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* bulk */}
      {selected.size > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-400/5 border border-amber-400/30">
          <span className="text-xs text-amber-300 font-medium">
            {selected.size} sélectionnée(s)
          </span>
          <div className="flex-1" />
          <button
            onClick={async () => {
              for (const k of selected) {
                const [srv, id] = k.split(':');
                try { await api.disconnect(srv, parseInt(id)); } catch {}
              }
              push(`${selected.size} sessions déconnectées`);
              setSelected(new Set());
              onActionDone();
            }}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs border border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <LogOut className="w-3 h-3" /> Déconnecter
          </button>
          <button onClick={() => setSelected(new Set())} className="p-1 text-zinc-400">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* table */}
      <div className="border border-zinc-800 bg-zinc-950 overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 border-b border-zinc-800">
              <th className="w-8 p-2 text-left">
                <input
                  type="checkbox"
                  checked={filtered.length > 0 && selected.size === filtered.length}
                  onChange={toggleAll}
                  className="accent-amber-400"
                />
              </th>
              <SortTh label="État"        k="state"   sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="ID"          k="id"      sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="Utilisateur" k="user"    sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="Serveur"     k="server"  sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="Session"     k="session" sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="Ouverture"   k="logon"   sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <SortTh label="Inactif"     k="idle"    sortKey={sortKey} sortDir={sortDir} onClick={toggleSort} />
              <th className="p-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80">
            {filtered.map((s) => {
              const k = keyOf(s);
              const c = STATE[s.state] || STATE.unknown;
              return (
                <tr
                  key={k}
                  onContextMenu={(e) => onContext(e, s)}
                  className={`hover:bg-zinc-900/60 cursor-default ${selected.has(k) ? 'bg-amber-400/5' : ''}`}
                >
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={selected.has(k)}
                      onChange={() => toggle(s)}
                      className="accent-amber-400"
                    />
                  </td>
                  <td className="p-2">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                      <span className={`text-[11px] ${c.text}`}>{c.label}</span>
                    </span>
                  </td>
                  <td className="p-2 text-zinc-500 font-mono text-xs tabular-nums">{s.session_id}</td>
                  <td className="p-2 font-mono text-zinc-100">{s.user}</td>
                  <td className="p-2 font-mono text-xs text-zinc-300">{s.server}</td>
                  <td className="p-2 text-xs text-zinc-400">{s.session_name || '-'}</td>
                  <td className="p-2 text-xs text-zinc-400 tabular-nums">{s.logon_time}</td>
                  <td className="p-2 text-xs text-zinc-400 tabular-nums">{s.idle_time}</td>
                  <td className="p-2">
                    <div className="flex items-center justify-end gap-1">
                      <ShadowButton session={s} onAction={doAction} />
                      <RowBtn title="Message" icon={MessageSquare} onClick={() => doAction('message', s)} />
                      <RowBtn title="Plus…" icon={MoreHorizontal} onClick={(e) => onContext(e, s)} />
                    </div>
                  </td>
                </tr>
              );
            })}
            {!filtered.length && !loading && (
              <tr>
                <td colSpan={9} className="p-8 text-center text-zinc-500 text-sm">
                  Aucune session à afficher.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="px-3 py-2 border-t border-zinc-800 text-[11px] text-zinc-500 flex justify-between">
          <span>
            {filtered.length} session(s) · <span className="text-zinc-600">clic droit pour les actions</span>
          </span>
          <span className="flex items-center gap-1">
            <Wifi className="w-3 h-3 text-emerald-400" /> auto 15 min · ou ↻ manuel
          </span>
        </div>
      </div>

      {ctxMenu && (
        <CtxMenu
          x={ctxMenu.x}
          y={ctxMenu.y}
          session={ctxMenu.session}
          onAction={(a, s) => {
            doAction(a, s);
            setCtxMenu(null);
          }}
          onCloseMenu={() => setCtxMenu(null)}
        />
      )}

      {messageFor && (
        <MessageModal
          session={messageFor}
          onClose={() => setMessageFor(null)}
          onSent={(msg) => {
            push(`Message envoyé à ${messageFor.user}`);
            setMessageFor(null);
          }}
          push={push}
        />
      )}

      {historyFor && <HistoryModal user={historyFor.user} onClose={() => setHistoryFor(null)} push={push} />}
    </div>
  );
}

function RowBtn({ title, icon: Icon, onClick, danger }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick && onClick(e);
      }}
      title={title}
      className={`p-1.5 transition-colors ${
        danger ? 'text-zinc-500 hover:text-rose-300 hover:bg-rose-400/10' : 'text-zinc-500 hover:text-amber-300 hover:bg-zinc-800'
      }`}
    >
      <Icon className="w-3.5 h-3.5" />
    </button>
  );
}

function SortTh({ label, k, sortKey, sortDir, onClick }) {
  const active = sortKey === k;
  return (
    <th className="p-2 text-left font-medium select-none">
      <button
        onClick={() => onClick(k)}
        className={`flex items-center gap-1 uppercase tracking-[0.15em] text-[10px] hover:text-amber-300 ${
          active ? 'text-amber-300' : 'text-zinc-500'
        }`}
      >
        {label}
        <span className="text-[9px]">
          {active ? (sortDir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  );
}

function ShadowButton({ session, onAction }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const h = () => setOpen(false);
    window.addEventListener('click', h);
    return () => window.removeEventListener('click', h);
  }, [open]);
  return (
    <div className="relative">
      <button
        title="Cliché instantané sur la session"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="p-1.5 text-zinc-500 hover:text-amber-300 hover:bg-zinc-800"
      >
        <Eye className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-64 bg-zinc-950 border border-zinc-800 shadow-2xl z-50" onClick={(e) => e.stopPropagation()}>
          <div className="px-3 py-2 border-b border-zinc-800 text-[10px] uppercase tracking-[0.15em] text-zinc-500">
            Cliché instantané — #{session.session_id}
          </div>
          <ShadowItem icon={Eye} label="Visualiser" sub="avec consentement" onClick={() => { onAction('shadow-view', session); setOpen(false); }} />
          <ShadowItem icon={MousePointer2} label="Demander le contrôle" sub="avec consentement" onClick={() => { onAction('shadow-control', session); setOpen(false); }} />
          <div className="h-px bg-zinc-800 my-1" />
          <ShadowItem icon={EyeOff} label="Forcer la visualisation" sub="sans consentement" warn onClick={() => { onAction('shadow-force-view', session); setOpen(false); }} />
          <ShadowItem icon={ShieldAlert} label="Forcer le contrôle" sub="sans consentement · audité" warn onClick={() => { onAction('shadow-force-control', session); setOpen(false); }} />
        </div>
      )}
    </div>
  );
}

function ShadowItem({ icon: Icon, label, sub, onClick, warn }) {
  return (
    <button onClick={onClick} className="w-full text-left flex items-center gap-2.5 px-3 py-2 hover:bg-zinc-900">
      <Icon className={`w-3.5 h-3.5 shrink-0 ${warn ? 'text-amber-400' : 'text-zinc-500'}`} />
      <div className="min-w-0">
        <div className={`text-xs ${warn ? 'text-amber-200' : 'text-zinc-200'}`}>{label}</div>
        <div className="text-[10px] text-zinc-500 font-mono">{sub}</div>
      </div>
    </button>
  );
}

function CtxMenu({ x, y, session, onAction }) {
  const [shadowHover, setShadowHover] = useState(false);
  return (
    <div
      className="fixed z-50 w-72 bg-zinc-950 border border-zinc-800 shadow-2xl text-sm"
      style={{ left: x, top: y }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="px-3 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500">{session.user}</div>
        <div className="text-xs text-zinc-400 font-mono">{session.server} · #{session.session_id}</div>
      </div>
      <CtxItem icon={MessageSquare} label="Envoyer un message" onClick={() => onAction('message', session)} />
      <div className="relative" onMouseEnter={() => setShadowHover(true)} onMouseLeave={() => setShadowHover(false)}>
        <button className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-zinc-900 text-left">
          <Camera className="w-3.5 h-3.5 text-zinc-500" />
          <span className="text-zinc-200 flex-1">Cliché instantané</span>
          <ChevronRight className="w-3 h-3 text-zinc-500" />
        </button>
        {shadowHover && (
          <div className="absolute left-full top-0 w-64 bg-zinc-950 border border-zinc-800 shadow-2xl">
            <ShadowItem icon={Eye} label="Visualiser" sub="avec consentement" onClick={() => onAction('shadow-view', session)} />
            <ShadowItem icon={MousePointer2} label="Demander le contrôle" sub="avec consentement" onClick={() => onAction('shadow-control', session)} />
            <div className="h-px bg-zinc-800 my-1" />
            <ShadowItem icon={EyeOff} label="Forcer la visualisation" sub="sans consentement" warn onClick={() => onAction('shadow-force-view', session)} />
            <ShadowItem icon={ShieldAlert} label="Forcer le contrôle" sub="sans consentement" warn onClick={() => onAction('shadow-force-control', session)} />
          </div>
        )}
      </div>
      <CtxItem icon={Unlock} label="Déverrouiller le compte AD" onClick={() => onAction('unlock', session)} />
      <div className="h-px bg-zinc-800 my-1" />
      <CtxItem icon={History} label="Historique de connexion" onClick={() => onAction('history', session)} />
      <CtxItem icon={FileSpreadsheet} label="Copier infos session" onClick={() => onAction('copy', session)} />
      <div className="h-px bg-zinc-800 my-1" />
      <CtxItem icon={LogOut} label="Déconnecter l'utilisateur" onClick={() => onAction('disconnect', session)} />
      <CtxItem icon={Power} label="Fermer la session" onClick={() => onAction('logoff', session)} danger />
    </div>
  );
}

function CtxItem({ icon: Icon, label, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-left ${
        danger ? 'hover:bg-rose-400/10 text-rose-300' : 'hover:bg-zinc-900 text-zinc-200'
      }`}
    >
      <Icon className={`w-3.5 h-3.5 ${danger ? 'text-rose-400' : 'text-zinc-500'}`} />
      <span className="flex-1 text-xs">{label}</span>
    </button>
  );
}

function MessageModal({ session, onClose, onSent, push }) {
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);

  async function send() {
    setSending(true);
    try {
      await api.sendMessage(session.server, session.session_id, body);
      onSent(body);
    } catch (e) {
      push(e.message, 'err');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative w-[480px] bg-zinc-950 border border-zinc-800" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500">Message à</div>
            <div className="font-mono text-lg text-zinc-100">{session.user}</div>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-200"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-4">
          <textarea
            autoFocus
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={5}
            placeholder="Votre message pour l'utilisateur…"
            className="w-full bg-zinc-900 border border-zinc-800 focus:border-amber-400/60 focus:outline-none p-2 text-sm text-zinc-100 font-mono"
          />
          <button
            onClick={send}
            disabled={!body || sending}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-amber-400 text-zinc-950 disabled:opacity-40 hover:bg-amber-300"
          >
            <Send className="w-3 h-3" /> {sending ? 'Envoi…' : 'Envoyer'}
          </button>
        </div>
      </div>
    </div>
  );
}

function HistoryModal({ user, onClose, push }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.history(user)
      .then((r) => setRows(r.history || []))
      .catch((e) => push(e.message, 'err'))
      .finally(() => setLoading(false));
  }, [user, push]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative w-[720px] max-h-[80vh] bg-zinc-950 border border-zinc-800 flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500">Historique de connexion</div>
            <div className="font-mono text-lg text-zinc-100">{user}</div>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-200"><X className="w-4 h-4" /></button>
        </div>
        <div className="overflow-auto">
          {loading && <div className="p-8 text-center text-zinc-500 text-sm">Chargement…</div>}
          {!loading && !rows.length && <div className="p-8 text-center text-zinc-500 text-sm">Aucun événement sur les 30 derniers jours.</div>}
          {!loading && rows.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 border-b border-zinc-800 sticky top-0 bg-zinc-950">
                <tr>
                  <th className="p-2 text-left">Horodatage</th>
                  <th className="p-2 text-left">Serveur</th>
                  <th className="p-2 text-left">IP client</th>
                  <th className="p-2 text-left">Événement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/80 font-mono text-xs">
                {rows.map((r, i) => (
                  <tr key={i} className="hover:bg-zinc-900/60">
                    <td className="p-2 text-zinc-300 tabular-nums">{r.when}</td>
                    <td className="p-2 text-zinc-200">{r.server}</td>
                    <td className="p-2 text-zinc-400">{r.ip || '-'}</td>
                    <td className="p-2"><span className="text-emerald-300">{r.event}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Serveurs
// ============================================================
function Servers({ push, servers, onChanged }) {
  const [newServer, setNewServer] = useState('');

  async function add() {
    const name = newServer.trim();
    if (!name) return;
    try {
      await api.addServer(name);
      push(`${name} ajouté`);
      setNewServer('');
      onChanged();
    } catch (e) {
      push(e.message, 'err');
    }
  }

  async function remove(name) {
    if (!confirm(`Retirer ${name} de la liste ?`)) return;
    try {
      await api.removeServer(name);
      push(`${name} retiré`);
      onChanged();
    } catch (e) {
      push(e.message, 'err');
    }
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <div className="border border-zinc-800 bg-zinc-950">
        <div className="px-3 py-2 border-b border-zinc-800 text-[11px] uppercase tracking-[0.15em] text-zinc-400">
          Ajouter un serveur RDS
        </div>
        <div className="p-3 flex gap-2">
          <input
            value={newServer}
            onChange={(e) => setNewServer(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
            placeholder="Nom du serveur (ex: SRVORLNSRDS058)"
            className="flex-1 bg-zinc-900 border border-zinc-800 focus:border-amber-400/60 focus:outline-none px-3 py-1.5 text-sm font-mono"
          />
          <button onClick={add} disabled={!newServer.trim()} className="flex items-center gap-1.5 px-4 py-1.5 bg-amber-400 text-zinc-950 text-sm font-medium disabled:opacity-40 hover:bg-amber-300">
            <Plus className="w-3.5 h-3.5" /> Ajouter
          </button>
        </div>
      </div>

      <div className="border border-zinc-800 bg-zinc-950">
        <div className="px-3 py-2 border-b border-zinc-800 text-[11px] uppercase tracking-[0.15em] text-zinc-400 flex justify-between">
          <span>Serveurs configurés ({servers.length})</span>
        </div>
        <div className="divide-y divide-zinc-800/80">
          {servers.map((s) => (
            <div key={s} className="flex items-center gap-2 px-3 py-2 hover:bg-zinc-900/50">
              <Server className="w-4 h-4 text-zinc-500" />
              <span className="font-mono text-sm flex-1">{s}</span>
              <button onClick={() => remove(s)} title="Retirer" className="p-1.5 text-zinc-500 hover:text-rose-300 hover:bg-rose-400/10">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          {!servers.length && (
            <div className="p-8 text-center text-sm text-zinc-500">
              Aucun serveur configuré. Ajoutez-en avec le formulaire ci-dessus.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Audit
// ============================================================
function Audit({ events }) {
  const [q, setQ] = useState('');
  const filtered = useMemo(() => {
    if (!q) return events;
    const needle = q.toLowerCase();
    return events.filter((e) =>
      `${e.when} ${e.who} ${e.action} ${e.target} ${e.result}`.toLowerCase().includes(needle)
    );
  }, [q, events]);

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-zinc-500" />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Rechercher par admin, action, serveur, utilisateur…"
          className="w-full bg-zinc-950 border border-zinc-800 focus:border-amber-400/60 focus:outline-none pl-8 pr-3 py-1.5 text-sm text-zinc-100 font-mono"
        />
        {q && (
          <span className="absolute right-2 top-1.5 text-[10px] text-zinc-500 font-mono">
            {filtered.length}/{events.length}
          </span>
        )}
      </div>
      <div className="border border-zinc-800 bg-zinc-950">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 border-b border-zinc-800">
            <tr>
              <th className="p-2 text-left">Horodatage</th>
              <th className="p-2 text-left">Administrateur</th>
              <th className="p-2 text-left">Action</th>
              <th className="p-2 text-left">Cible</th>
              <th className="p-2 text-left">Résultat</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80 font-mono text-xs">
            {filtered.map((e, i) => (
              <tr key={i} className="hover:bg-zinc-900/60">
                <td className="p-2 text-zinc-400 tabular-nums">{e.when}</td>
                <td className="p-2 text-zinc-200">{e.who}</td>
                <td className="p-2"><span className="text-amber-300">{e.action}</span></td>
                <td className="p-2 text-zinc-300">{e.target}</td>
                <td className="p-2"><span className="text-emerald-300">{e.result}</span></td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-zinc-500">
                  {events.length ? 'Aucun résultat pour cette recherche.' : 'Aucun événement.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="px-3 py-2 border-t border-zinc-800 text-[11px] text-zinc-500 font-mono">
          Rétention : 30 jours · purge automatique
        </div>
      </div>
    </div>
  );
}

// ============================================================
// App root
// ============================================================
export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-900">
        <div className="text-zinc-500 text-sm font-mono">Chargement…</div>
      </div>
    );
  }

  if (!user) return <Login onLogin={() => api.me().then(setUser)} />;

  return <Shell user={user} onLogout={async () => { await api.logout(); setUser(null); }} />;
}
