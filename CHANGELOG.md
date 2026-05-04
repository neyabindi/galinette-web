# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2026-04-30

### Major stability and feature update 🎉

#### Added
- **Background scanner**: a task running in the backend scans the RDS farm every minute,
  using credentials of any logged-in admin. The cache is shared across all admins → instant
  page loads after first scan completes.
- **Auto-search**: typing a username in the search box that returns no result triggers a
  fresh scan automatically (mimics original Galinette cendrée behavior).
- **AD SID column**: each session is enriched with its `objectSid` resolved via a single
  LDAP query to the DC (cached 6h). One-click copy for FSLogix VHDX troubleshooting.
- **Disk C: monitoring** in the farm dashboard, with warning (80%) and critical (90%) thresholds.
- **Per-server session stats** in dashboard (active / idle / disconnected).
- **Offline servers alert** on the dashboard.
- **Connection history with logon types** (RDP, console, unlock, network, cached).
- **MariaDB/MySQL audit backend** via `DATABASE_URL` config (SQLite remains the default).
- **Configurable audit retention** via `AUDIT_RETENTION_DAYS` (default 90 days).
- **Auto-deduplication** of server names (case-insensitive normalization).

#### Changed
- WinRM concurrency: separate semaphores for admin actions (5 slots) and background
  scans (2 slots) → admin actions are never blocked by the background scanner.
- Timeouts now applied AFTER semaphore acquisition (no more bulk false-positive timeouts).
- The cache always returns the latest valid data, even if the latest scan failed.
- History queries are parallelized with timeouts and case-insensitive matching.
- Improved error messages (replaces low-level pypsrp jargon with human messages).

#### Fixed
- "Server offline" false positives when WinRM was saturated.
- Dashboard / Sessions tab going blank when switching tabs (state lifted to Shell).
- Connection history returning empty due to MaxEvents being applied before the user filter.
- Duplicate server entries with different cases (VMP036 / vmp036).
- Manual refresh occasionally overwriting a good cache with empty results.

## [1.0.0] - 2026-04-24

### First public release

- Active Directory login with LDAPS + LDAP fallback
- Group-based authorization (`Galinette-Admins` AD group)
- Multi-server session listing in parallel
- 4 Shadow modes via auto-elevating `.bat`
- Send message, disconnect, logoff
- Unlock AD account
- User connection history
- Farm dashboard (CPU, RAM, uptime)
- Live search and column sort
- Bulk actions, CSV export, copy session info
- Dynamic server list editable from the UI
- Built-in audit log (SQLite, 30-day retention)
- Credentials encrypted in RAM (Fernet), never persisted

Credits: Inspired by Galinette cendrée by Mehdy Bouchiba.
