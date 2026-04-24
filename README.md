<div align="center">

#  Galinette Web

**Modern web-based RDS administration console**
*Console moderne d'administration RDS en web*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb?logo=react)](https://react.dev/)

[English](#english) · [Français](#français)

</div>

---

## English

A modern, lightweight, web-based replacement for the legendary **Galinette cendrée** (a .NET Windows app by Mehdy Bouchiba) that every sysadmin managing Remote Desktop Services has used at some point.

Galinette Web lets a team of Active Directory administrators list, monitor and manage user sessions across a farm of Windows RDS hosts — without installing any agent, without any GPO, and without any service account.

### Features

-  **Active Directory login** with group-based authorization (LDAPS with LDAP fallback)
-  **Real-time multi-server session listing** with smart merge (no UI flicker on refresh)
-  **Instant search, filters and column sorting** (state, user, server, logon, idle)
-  **4 Shadow modes** (view/control, with/without consent) — auto-UAC elevation
-  **Send message** to any user
-  **Unlock AD accounts** from the UI
-  **Connection history** (last 30 days)
-  **Farm dashboard** (CPU, RAM, uptime, per-server session stats)
-  **Built-in audit log** (SQLite, 30-day retention, live search)
-  **Dynamic server list** (add/remove without restart)
-  **CSV export**
-  **Copy session info** to clipboard

### Why?

Galinette cendrée is wonderful but:
- Windows desktop app — needs to be installed on every admin's machine
- Aging WinForms UI
- No multi-admin audit trail
- No search, limited filters
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
┌─────────────────────────┐
│  Docker host            │
│   ┌──────────┐ ┌──────┐ │
│   │ frontend │→│ API  │ │
│   └──────────┘ └──┬───┘ │
└──────────────────┼──────┘
                   │ WinRM 5985 + Kerberos
                   ↓
           RDS Session Hosts
```

**Stack:** FastAPI (Python) backend + React (Tailwind) frontend + SQLite audit + Docker.

### Quick start

**Prerequisites:**
- Docker + Docker Compose
- Active Directory domain with working DNS
- RDS hosts with **WinRM enabled** (port 5985) and the Docker host allowed to reach them
- Port **445/SMB** open from admin workstations to RDS hosts (for Shadow)
- Your admin account must be **local admin** of the RDS hosts
- An AD group (e.g. `Galinette-Admins`) whose members can access Galinette

**Deployment:**

```bash
git clone https://github.com/YOUR_USERNAME/galinette-web.git
cd galinette-web
cp .env.example .env
# Edit .env with your AD settings
docker compose up -d --build
```

Access at `http://your-docker-host:8082`, or put a reverse proxy (Nginx, Caddy, Traefik, Nginx Proxy Manager…) in front for HTTPS.

### Configuration

Edit `.env`:

| Variable | Description | Example |
|---|---|---|
| `AD_DOMAIN` | AD DNS domain | `contoso.local` |
| `AD_NETBIOS` | NetBIOS name | `CONTOSO` |
| `AD_DC` | DC hostname (empty = auto) | `dc01.contoso.local` |
| `AD_ADMIN_GROUP` | AD group allowed to log in | `Galinette-Admins` |
| `FRONTEND_PORT` | Host port | `8082` |
| `COOKIE_SECURE` | `true` in HTTPS | `true` |
| `CORS_ORIGINS` | Public URL (JSON array) | `["https://galinette.contoso.com"]` |

**Server list:** added through the UI (stored in `servers.json` inside the Docker volume). No restart needed when adding/removing hosts.

### Shadow mechanism

When you click **Shadow** on a session, Galinette generates a small auto-elevating `.bat` file that runs:

```
mstsc.exe /shadow:<ID> /v:<SERVER> [/control] [/noConsentPrompt]
```

This is the **exact same mechanism** as the original Galinette cendrée — just triggered from the web instead of a .NET app. No GPO changes required.

The `.bat` requests UAC elevation so that `/noConsentPrompt` works reliably (Windows refuses elevated actions from medium-integrity contexts).

### Security

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

### Roadmap

- [ ] FSLogix/UPD profile size tab
- [ ] WebSocket live updates (currently 15-min auto-refresh + manual)
- [ ] Custom `galinette://` URL protocol handler (one-click shadow without download)
- [ ] Kerberos-based impersonation (no password storage at all)
- [ ] Multi-domain support

### Contributing

Issues and PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

### Credits

- Inspired by **Galinette cendrée** by [Mehdy Bouchiba](https://sourceforge.net/projects/galinettecendree/) — the OG RDS admin tool for sysadmin.
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [Tailwind CSS](https://tailwindcss.com/), [pypsrp](https://github.com/jborean93/pypsrp), [ldap3](https://github.com/cannatag/ldap3).

### License

[MIT](LICENSE)

---

## Français

Un remplacement moderne, léger et web de la légendaire **Galinette cendrée** (app .NET Windows de Mehdy Bouchiba) que tout sysadmin gérant des Services Bureau à distance a utilisée au moins une fois.

Galinette Web permet à une équipe d'administrateurs Active Directory de lister, surveiller et gérer les sessions utilisateurs sur une ferme de serveurs RDS — sans installer d'agent, sans GPO, sans compte de service.

### Fonctionnalités

-  **Connexion Active Directory** avec contrôle par groupe (LDAPS avec fallback LDAP)
-  **Liste temps réel multi-serveurs** avec merge intelligent (pas de flash au rafraîchissement)
-  **Recherche instantanée, filtres, tri par colonnes** (état, utilisateur, serveur, ouverture, inactif)
-  **4 modes Shadow** (visualisation/contrôle, avec/sans consentement) — auto-élévation UAC
-  **Envoi de message** à tout utilisateur
-  **Déverrouillage compte AD** depuis l'interface
-  **Historique de connexion** (30 derniers jours)
-  **Dashboard de ferme** (CPU, RAM, uptime, stats sessions par serveur)
-  **Journal d'audit intégré** (SQLite, rétention 30 jours, recherche live)
-  **Liste de serveurs dynamique** (ajout/retrait sans redémarrage)
-  **Export CSV**
-  **Copier les infos de session** dans le presse-papier

### Pourquoi ?

Galinette cendrée est géniale mais :
- Application Windows desktop — à installer sur chaque poste d'admin
- Interface WinForms vieillissante
- Pas de traçabilité multi-admins
- Pas de recherche, filtres limités
- Bugs sur les OS récents

Galinette Web garde la **même philosophie** (tu entres tes identifiants admin, tu vois les sessions, tu agis), mais :
- Déploiement unique sur un hôte Docker, accessible depuis tout navigateur
- Multi-admins avec audit par action
- UI moderne dense pensée pour des pros qui regardent ça 8h/jour
- Même mécanisme `mstsc.exe /shadow` — pas de GPO, pas d'agent

### Architecture

```
Navigateur (admins)
   ↓ HTTPS (via ton reverse proxy)
┌─────────────────────────┐
│  Hôte Docker            │
│   ┌──────────┐ ┌──────┐ │
│   │ frontend │→│ API  │ │
│   └──────────┘ └──┬───┘ │
└──────────────────┼──────┘
                   │ WinRM 5985 + Kerberos
                   ↓
         Serveurs RDS (Session Hosts)
```

**Stack :** backend FastAPI (Python) + frontend React (Tailwind) + audit SQLite + Docker.

### Démarrage rapide

**Prérequis :**
- Docker + Docker Compose
- Domaine Active Directory avec DNS fonctionnel
- Serveurs RDS avec **WinRM activé** (port 5985) et l'hôte Docker autorisé à y accéder
- Port **445/SMB** ouvert depuis les postes admins vers les RDS (pour le Shadow)
- Ton compte admin doit être **admin local** des serveurs RDS
- Un groupe AD (ex: `Galinette-Admins`) dont les membres peuvent accéder à Galinette

**Déploiement :**

```bash
git clone https://github.com/VOTRE_USER/galinette-web.git
cd galinette-web
cp .env.example .env
# Modifier .env avec tes paramètres AD
docker compose up -d --build
```

Accès sur `http://ton-hote-docker:8082`, ou mets un reverse proxy (Nginx, Caddy, Traefik, Nginx Proxy Manager…) devant pour le HTTPS.

### Configuration

Modifier `.env` :

| Variable | Description | Exemple |
|---|---|---|
| `AD_DOMAIN` | Domaine DNS AD | `monentreprise.local` |
| `AD_NETBIOS` | Nom NetBIOS | `MONENT` |
| `AD_DC` | Nom du DC (vide = auto) | `dc01.monentreprise.local` |
| `AD_ADMIN_GROUP` | Groupe AD autorisé | `Galinette-Admins` |
| `FRONTEND_PORT` | Port sur l'hôte | `8082` |
| `COOKIE_SECURE` | `true` en HTTPS | `true` |
| `CORS_ORIGINS` | URL publique (tableau JSON) | `["https://galinette.exemple.com"]` |

**Liste de serveurs :** ajoutée via l'interface web (stockée dans `servers.json` du volume Docker). Pas de redémarrage nécessaire pour ajouter/retirer un hôte.

### Mécanisme Shadow

Quand tu cliques **Shadow** sur une session, Galinette génère un petit `.bat` auto-élevé qui exécute :

```
mstsc.exe /shadow:<ID> /v:<SERVEUR> [/control] [/noConsentPrompt]
```

C'est le **mécanisme exact** de Galinette cendrée originale — juste déclenché depuis le web au lieu d'une app .NET. Aucune GPO à modifier.

Le `.bat` demande une élévation UAC pour que `/noConsentPrompt` fonctionne (Windows refuse les actions élevées depuis un contexte d'intégrité moyenne).

### Sécurité

- Les identifiants sont **chiffrés en RAM** (Fernet) pendant ta session — jamais écrits sur disque
- Le cookie de session est un token `HttpOnly` opaque, pas le mot de passe
- Effacés au logout / après 8h d'inactivité / au redémarrage du conteneur
- Le journal d'audit enregistre toutes les actions (qui, quand, quoi, cible) avec rétention 30 jours
- Les mots de passe n'apparaissent nulle part dans les logs ou la base

### Contribution

Issues et PRs bienvenues ! Voir [CONTRIBUTING.md](CONTRIBUTING.md).

### Crédits

- Inspiré par **Galinette cendrée** de [Mehdy Bouchiba](https://sourceforge.net/projects/galinettecendree/) — l'outil RDS de référence pour les sysadmins. 
- Construit avec [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [Tailwind CSS](https://tailwindcss.com/), [pypsrp](https://github.com/jborean93/pypsrp), [ldap3](https://github.com/cannatag/ldap3).

### Licence

[MIT](LICENSE)
