<div align="center">

# Galinette Web V2.0

**Modern web-based RDS administration console**
*Console moderne d'administration RDS en web*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb?logo=react)](https://react.dev/)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](CHANGELOG.md)

[English](#english) · [Français](#français)

</div>

---

## English

A modern, lightweight, web-based replacement for the legendary **Galinette cendrée** (.NET Windows app by Mehdy Bouchiba) used by countless French sysadmins to manage Remote Desktop Services.

Galinette Web lets a team of Active Directory administrators list, monitor and manage user sessions across a farm of Windows RDS hosts — without installing any agent, GPO, or service account.

### Features

-  **Active Directory login** with LDAPS + group-based authorization
-  **Background refresh** — instant page loads, server load mutualized between admins
-  **Real-time multi-server session listing** with smart merge (no UI flicker)
-  **Auto-search** — type a username, if not found a fresh scan is triggered automatically
-  **Sort & filter** every column (state, user, SID, server, logon, idle)
-  **4 Shadow modes** (view/control, with/without consent) — auto-UAC elevation
-  **AD SID column** — one-click copy (perfect for FSLogix VHDX troubleshooting)
-  **Send message** to any user
-  **Unlock AD account** from the UI
-  **Connection history** with logon types (RDP, console, unlock, cached)
-  **Farm dashboard** — CPU, RAM, **disk C:** with thresholds, uptime, sessions split per server
-  **Offline servers alert** on the dashboard
-  **Built-in audit log** — SQLite or **MariaDB**, configurable retention (default 90 days), live search
-  **Dynamic server list** — add/remove from the UI, auto-deduplication
-  **CSV export** with SID
-  **Copy session info** to clipboard

### Why?

Galinette cendrée is wonderful but:
- Windows desktop app — must be installed on each admin's workstation
- Aging WinForms UI
- No multi-admin audit trail
- Limited search and filtering
- Bugs on recent OS versions

Galinette Web keeps the **same philosophy** (just enter your admin credentials, see sessions, act), but:
- Deploy once on a Docker host, access from any browser
- Multi-admin with per-action audit
- Modern dense UI built for pros who stare at it 8h/day
- Same `mstsc.exe /shadow` mechanism — no GPO, no agent

### Architecture

```
Browser (admins)
   ↓ HTTPS (via your reverse proxy)
┌──────────────────────────────┐
│  Docker host                 │
│   ┌──────────┐  ┌─────────┐  │
│   │ frontend │→ │ backend │  │
│   └──────────┘  └────┬────┘  │
│                      │       │
│   Background scanner: every minute
└──────────────────────┼───────┘
                       │ WinRM 5985 + Kerberos
                       ↓
                RDS Session Hosts
```

A **background task** scans your RDS farm every minute using credentials of any logged-in admin. The cache is shared across all admins, so subsequent connections are instant.

**Stack:** FastAPI (Python) + React (Tailwind) + ldap3 + pypsrp + SQLAlchemy + Docker.

### Quick start

**Prerequisites:**
- Docker + Docker Compose
- Active Directory domain with working DNS
- RDS hosts with **WinRM enabled** (port 5985), reachable from the Docker host
- Port **445/SMB** open from admin workstations to RDS hosts (for Shadow)
- Your admin account must be **local admin** of the RDS hosts
- An AD group (e.g. `Galinette-Admins`) whose members can access Galinette
- *(Optional)* a MariaDB/MySQL server if you want the audit log there

**Deployment:**

```bash
git clone https://github.com/YOUR_USERNAME/galinette-web.git
cd galinette-web
cp .env.example .env
# Edit .env with your AD settings
docker compose up -d --build
```

Access at `http://your-docker-host:8082`, or put a reverse proxy (Nginx, Caddy, Traefik, NPM…) in front for HTTPS.

> ⚠️ If using a reverse proxy, increase `proxy_*_timeout` to **120s** to allow the first farm scan to complete.

### Configuration

| Variable | Description | Example |
|---|---|---|
| `AD_DOMAIN` | AD DNS domain | `contoso.local` |
| `AD_NETBIOS` | NetBIOS name | `CONTOSO` |
| `AD_DC` | DC hostname (empty = auto) | `dc01.contoso.local` |
| `AD_ADMIN_GROUP` | AD group allowed to log in | `Galinette-Admins` |
| `AUDIT_RETENTION_DAYS` | Audit log retention | `90` |
| `DATABASE_URL` | Empty for SQLite, or MariaDB URL | `mysql+pymysql://user:pwd@host:3306/galinette` |
| `FRONTEND_PORT` | Host port | `8082` |
| `COOKIE_SECURE` | `true` in HTTPS | `true` |
| `CORS_ORIGINS` | Public URL (JSON array) | `["https://galinette.contoso.com"]` |

### Shadow mechanism

When you click **Shadow** on a session, Galinette generates a small auto-elevating `.bat` file that runs:

```
mstsc.exe /shadow:<ID> /v:<SERVER> [/control] [/noConsentPrompt]
```

Same mechanism as the original Galinette cendrée. No GPO needed.

### Security

<<<<<<< HEAD
- Credentials **encrypted in RAM** (Fernet) — never written to disk
- Session cookie is opaque `HttpOnly` token, not the password
- Cleared on logout / after 8h inactivity / on container restart
- Audit log records every action (who, when, what, target)
- LDAP queries use the connected admin's credentials (no service account)
=======
- Credentials are **encrypted in RAM** (Fernet) during your session — never written to disk
- Session cookie is opaque `HttpOnly` token, not your password
- Cleared on logout / after 8h of inactivity / on container restart
- Audit log records all actions (who, when, what, target) with 30-day retention
- Passwords appear nowhere in logs or the database

### Screenshots

![Login](docs/screenshots/login.png)


*Active Directory login with group-based authorization*

![Dashboard](docs/screenshots/dashboard.png)
*Farm health: per-server CPU/RAM/uptime and session stats*

![Sessions](docs/screenshots/sessions.png)
*Multi-server sessions with sortable columns, filters, and live search*

![Shadow menu](docs/screenshots/shadow-menu.png)
*Four shadow modes — same as the original Galinette cendrée*

![Audit](docs/screenshots/audit.png)
*Built-in audit log with 30-day retention and live search*
>>>>>>> 01697c181cf2266bd11d2ce98514360272e8d315

### Roadmap

- [ ] FSLogix/UPD profile size tab
- [ ] WebSocket live updates (currently 1-min auto-refresh)
- [ ] Custom `galinette://` URL protocol handler (one-click shadow without download)

### Credits

<<<<<<< HEAD
- Inspired by **Galinette cendrée** by [Mehdy Bouchiba](https://sourceforge.net/projects/galinettecendree/) — the OG RDS admin tool for French sysadmins.
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [Tailwind CSS](https://tailwindcss.com/), [pypsrp](https://github.com/jborean93/pypsrp), [ldap3](https://github.com/cannatag/ldap3), [SQLAlchemy](https://www.sqlalchemy.org/).
=======
- Inspired by **Galinette cendrée** by [Mehdy Bouchiba](https://sourceforge.net/projects/galinettecendree/) — the OG RDS admin tool for sysadmin.
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [Tailwind CSS](https://tailwindcss.com/), [pypsrp](https://github.com/jborean93/pypsrp), [ldap3](https://github.com/cannatag/ldap3).
>>>>>>> 01697c181cf2266bd11d2ce98514360272e8d315

### License

[MIT](LICENSE)

---

## Français

Un remplacement moderne, léger et web de la légendaire **Galinette cendrée** (app .NET de Mehdy Bouchiba) utilisée par d'innombrables sysadmins français pour gérer les Services Bureau à distance.

Galinette Web permet à une équipe d'administrateurs Active Directory de lister, surveiller et gérer les sessions utilisateurs sur une ferme de serveurs RDS — sans agent, sans GPO, sans compte de service.

### Fonctionnalités

-  **Connexion Active Directory** LDAPS avec contrôle par groupe
-  **Refresh en arrière-plan** — chargement instantané, charge mutualisée entre admins
-  **Liste temps réel multi-serveurs** avec merge intelligent (pas de flash)
-  **Recherche-actualisation** — tape un nom, si introuvable un scan frais est lancé automatiquement
-  **Tri et filtres** sur toutes les colonnes (état, user, SID, serveur, ouverture, inactif)
-  **4 modes Shadow** (visualisation/contrôle, avec/sans consentement) — auto-élévation UAC
-  **Colonne SID** AD — clic pour copier (parfait pour debugger FSLogix)
-  **Envoi de message** à tout utilisateur
-  **Déverrouillage compte AD** depuis l'interface
-  **Historique de connexion** avec types (RDP, console, déverrouillage, cached)
-  **Dashboard de ferme** — CPU, RAM, **disque C:** avec seuils, uptime, sessions par serveur
-  **Alerte serveurs hors-ligne** sur le dashboard
-  **Journal d'audit intégré** — SQLite ou **MariaDB**, rétention configurable (90j par défaut), recherche live
-  **Liste de serveurs dynamique** — ajout/retrait depuis l'UI, dédoublonnage auto
-  **Export CSV** avec SID
-  **Copier les infos de session** dans le presse-papier

### Pourquoi ?

Galinette cendrée est géniale mais :
- App Windows desktop — à installer sur chaque poste d'admin
- Interface WinForms vieillissante
- Pas de traçabilité multi-admins
- Recherche et filtres limités
- Bugs sur OS récents

Galinette Web garde la **même philosophie**, mais en mieux :
- Déploiement unique, accessible depuis tout navigateur
- Multi-admins avec audit par action
- UI moderne dense pour les pros 8h/jour
- Même mécanisme `mstsc.exe /shadow` — pas de GPO, pas d'agent

### Démarrage rapide

**Prérequis :**
- Docker + Docker Compose
- Domaine AD avec DNS fonctionnel
- Serveurs RDS avec **WinRM activé** (port 5985), accessibles depuis l'hôte Docker
- Port **445/SMB** ouvert depuis postes admins vers RDS (pour Shadow)
- Compte admin **admin local** des serveurs RDS
- Un groupe AD (ex: `Galinette-Admins`) pour l'accès à Galinette
- *(Optionnel)* un serveur MariaDB/MySQL pour le journal d'audit

**Déploiement :**

```bash
git clone https://github.com/VOTRE_USER/galinette-web.git
cd galinette-web
cp .env.example .env
# Modifier .env
docker compose up -d --build
```

> ⚠️ Si reverse proxy, augmenter `proxy_*_timeout` à **120s** pour le 1er scan.

### Sécurité

- Identifiants **chiffrés en RAM** (Fernet) — jamais sur disque
- Cookie `HttpOnly` opaque, pas le mot de passe
- Effacés au logout / après 8h / au redémarrage du conteneur
- Audit complet (qui, quand, quoi, cible)
- Requêtes LDAP avec les credentials de l'admin connecté (pas de compte de service)

### Crédits

### Crédits

- Inspiré par **Galinette cendrée** de [Mehdy Bouchiba](https://sourceforge.net/projects/galinettecendree/)
- Construit avec [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [Tailwind CSS](https://tailwindcss.com/), [pypsrp](https://github.com/jborean93/pypsrp), [ldap3](https://github.com/cannatag/ldap3).

### Licence

[MIT](LICENSE)
