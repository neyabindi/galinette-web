# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-04-24

### First public release 🎉

Features:
- Active Directory login with LDAPS + LDAP fallback
- Group-based authorization (`Galinette-Admins` AD group)
- Multi-server session listing in parallel (async with per-server 20s timeout)
- 4 Shadow modes via auto-elevating `.bat` (view/control, with/without consent)
- Send message, disconnect, logoff actions
- Unlock AD account
- User connection history (last 30 days)
- Farm dashboard (CPU, RAM, uptime, sessions split)
- Column sort (state, ID, user, server, session, logon, idle)
- Live search and filters
- Bulk actions (disconnect multiple sessions)
- CSV export
- Copy session info to clipboard
- Dynamic server list editable from the UI
- Built-in audit log with 30-day retention and live search
- Credentials encrypted in RAM (Fernet), never persisted
- Docker Compose deployment

Known limitations:
- `noConsentPrompt` shadow mode depends on local group policy — fallback to consent prompt if blocked
- Event 4624 parsing for connection history may need tuning on some OS versions
- No built-in HTTPS — put a reverse proxy in front (Nginx, Caddy, NPM…)

Credits: Inspired by Galinette cendrée by Mehdy Bouchiba. Developed by Ney Abindi (neyabindi).
