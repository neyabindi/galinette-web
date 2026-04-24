"""
Module RDS — interactions avec les serveurs Windows via PowerShell Remoting.

Utilise pypsrp pour parler WinRM/Kerberos/NTLM. Les actions sont exécutées avec
les credentials de l'admin connecté (impersonation).
"""
import asyncio
import json
import logging
from typing import Any
from pypsrp.client import Client
from pypsrp.exceptions import WSManFaultError
from pypsrp.powershell import PowerShell, RunspacePool
from pypsrp.wsman import WSMan

log = logging.getLogger("galinette.rds")


def _run_ps(server: str, script: str, creds: tuple[str, str]) -> list[dict]:
    """
    Exécute un script PowerShell sur le serveur distant et retourne le résultat JSON.
    Le script DOIT se terminer par ConvertTo-Json -Compress pour être parsé.
    """
    username, password = creds
    try:
        with WSMan(
            server,
            username=username,
            password=password,
            ssl=False,            # WinRM HTTP chiffré par Kerberos/NTLM
            auth="negotiate",     # Kerberos + fallback NTLM
            cert_validation=False,
            connection_timeout=10,
            operation_timeout=30,
        ) as wsman:
            with RunspacePool(wsman) as pool:
                ps = PowerShell(pool)
                ps.add_script(script)
                output = ps.invoke()
                if ps.had_errors:
                    errors = [str(e) for e in ps.streams.error]
                    raise RuntimeError(f"Erreur PowerShell : {'; '.join(errors)}")
                if not output:
                    return []
                # Le résultat de ConvertTo-Json est rendu sous forme de string
                raw = "\n".join(str(o) for o in output).strip()
                if not raw:
                    return []
                data = json.loads(raw)
                # Normaliser : toujours une liste
                return data if isinstance(data, list) else [data]
    except WSManFaultError as e:
        raise RuntimeError(f"WSMan error sur {server} : {e}")


async def _run_async(server: str, script: str, creds: tuple[str, str]) -> list[dict]:
    return await asyncio.to_thread(_run_ps, server, script, creds)


# ---------------- Lecture des sessions ----------------
PS_LIST_SESSIONS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$OutputEncoding = [System.Text.Encoding]::UTF8
$raw = & quser.exe 2>&1
# quser.exe retourne un code d'erreur et un message "Aucun utilisateur..." quand
# il n'y a aucune session. On traite ce cas comme une liste vide, pas une erreur.
if (-not $raw -or ($raw -join '') -match 'No User exists|Aucun utilisateur') {
    '[]'
    return
}

$lines = @($raw | Where-Object { $_ -and $_.Trim() })
if ($lines.Count -lt 2) { '[]' ; return }

# Parser basé sur tokens : on prend toujours la 1ère ligne comme header et on skip.
# Pour chaque ligne suivante, on split sur 2+ espaces et on identifie les colonnes par leur TYPE :
#   - 1er token = user
#   - 1er token purement numérique = ID session
#   - Token entre user et ID (s'il y en a un non-numérique) = session_name (rdp-tcp#NN)
#   - Après l'ID : state, idle, logon
$sessions = @()
foreach ($line in $lines[1..($lines.Count-1)]) {
    try {
        $clean = ($line -replace '^\s*>', ' ').Trim()
        $tokens = @($clean -split '\s{2,}' | Where-Object { $_ -and $_.Trim() })
        if ($tokens.Count -lt 3) { continue }

        # Trouve l'index du premier token numérique (= ID session)
        $idIdx = -1
        for ($i = 0; $i -lt $tokens.Count; $i++) {
            if ($tokens[$i].Trim() -match '^\d+$') {
                $idIdx = $i
                break
            }
        }
        if ($idIdx -lt 1) { continue }  # il faut au moins user avant l'ID

        $user = $tokens[0].TrimStart('>',' ').Trim()
        $sid  = [int]$tokens[$idIdx].Trim()

        # Si l'ID est en position 2+, la position 1 est le session_name (rdp-tcp#NN ou "console")
        $sname = if ($idIdx -ge 2) { $tokens[1].Trim() } else { '' }

        # État = token juste après l'ID
        $state = if ($tokens.Count -gt ($idIdx + 1)) { $tokens[$idIdx + 1].Trim() } else { '' }

        # Idle = token suivant (chiffre ou ".")
        $idle = if ($tokens.Count -gt ($idIdx + 2)) { $tokens[$idIdx + 2].Trim() } else { '' }

        # Logon = tous les tokens restants joints (date + heure)
        $logon = if ($tokens.Count -gt ($idIdx + 3)) {
            ($tokens[($idIdx + 3)..($tokens.Count - 1)] -join ' ').Trim()
        } else { '' }

        $sessions += [pscustomobject]@{
            user         = $user
            session_name = $sname
            session_id   = $sid
            state        = $state
            idle_time    = $idle
            logon_time   = $logon
            server       = $env:COMPUTERNAME
        }
    } catch { continue }
}

if ($sessions.Count -eq 0) { '[]' ; return }
$sessions | ConvertTo-Json -Compress -Depth 3
"""


async def list_sessions_on_server(
    server: str, creds: tuple[str, str]
) -> list[dict[str, Any]]:
    """Liste les sessions RDP sur un serveur."""
    try:
        raw = await _run_async(server, PS_LIST_SESSIONS, creds)
        for s in raw:
            st = (s.get("state") or "").lower().strip()
            if st in ("active", "actif"):
                s["state"] = "active"
            elif "disc" in st or "déco" in st or "deco" in st:
                s["state"] = "disconnected"
            elif "idle" in st or "inact" in st:
                s["state"] = "idle"
            elif st == "" or st == "." or "listen" in st:
                s["state"] = "disconnected"
            else:
                s["state"] = "disconnected"
            # Normalise l'idle time
            idle = (s.get("idle_time") or "").strip()
            if idle in (".", "", "0"):
                s["idle_time"] = "-"
            elif idle.isdigit():
                s["idle_time"] = f"{idle} min"
        return raw
    except Exception as e:
        log.warning("list_sessions_on_server(%s) KO : %s", server, e)
        raise


# ---------------- Actions sur sessions ----------------
async def disconnect_session(server: str, sid: int, creds: tuple[str, str]) -> None:
    script = f"& tsdiscon.exe {sid} 2>&1 | Out-Null ; 'ok' | ConvertTo-Json -Compress"
    await _run_async(server, script, creds)


async def logoff_session(server: str, sid: int, creds: tuple[str, str]) -> None:
    script = f"& logoff.exe {sid} 2>&1 | Out-Null ; 'ok' | ConvertTo-Json -Compress"
    await _run_async(server, script, creds)


async def send_message(
    server: str, sid: int, title: str, body: str, creds: tuple[str, str]
) -> None:
    # Échappement simple des guillemets
    safe_title = title.replace('"', "'")
    safe_body = body.replace('"', "'")
    script = (
        f'& msg.exe {sid} /TIME:60 "{safe_title}`n`n{safe_body}" 2>&1 | Out-Null ; '
        f"'ok' | ConvertTo-Json -Compress"
    )
    await _run_async(server, script, creds)


# ---------------- Processus utilisateur ----------------
async def list_user_processes(
    server: str, sid: int, creds: tuple[str, str]
) -> list[dict[str, Any]]:
    script = f"""
    $ErrorActionPreference = 'Stop'
    Get-CimInstance Win32_Process -Filter "SessionId = {sid}" | ForEach-Object {{
        [pscustomobject]@{{
            pid      = [int]$_.ProcessId
            name     = $_.Name
            cpu_sec  = [int]($_.KernelModeTime + $_.UserModeTime) / 10000000
            ram_mb   = [math]::Round($_.WorkingSetSize / 1MB, 1)
        }}
    }} | Sort-Object ram_mb -Descending | Select-Object -First 50 | ConvertTo-Json -Compress -Depth 3
    """
    return await _run_async(server, script, creds)


# ---------------- Déverrouillage AD ----------------
async def unlock_ad_account(sam: str, creds: tuple[str, str]) -> None:
    """
    Déverrouille un compte AD. L'action est effectuée sur le DC via PowerShell Remoting
    sur n'importe quel serveur ayant le module ActiveDirectory (typiquement un RDS joint).
    """
    from .config import load_servers
    servers = load_servers()
    if not servers:
        raise RuntimeError("Aucun serveur configuré pour exécuter la commande AD")

    safe = sam.replace("'", "''")
    script = f"""
    $ErrorActionPreference = 'Stop'
    Import-Module ActiveDirectory
    Unlock-ADAccount -Identity '{safe}'
    'ok' | ConvertTo-Json -Compress
    """
    last_error = None
    for srv in servers:
        try:
            await _run_async(srv, script, creds)
            return
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Aucun serveur n'a pu déverrouiller {sam} : {last_error}")


# ---------------- Historique de connexion ----------------
async def get_connection_history(
    sam: str, creds: tuple[str, str], servers: list[str], days: int = 30
) -> list[dict[str, Any]]:
    """
    Parcourt les journaux Security de chaque RDS pour les events 4624 (logon) du user.
    Limité aux 30 derniers jours et 50 events max par serveur.
    """
    safe = sam.replace("'", "''")
    script = f"""
    $ErrorActionPreference = 'SilentlyContinue'
    $start = (Get-Date).AddDays(-{days})
    $events = Get-WinEvent -FilterHashtable @{{
        LogName = 'Security'
        Id = 4624
        StartTime = $start
    }} -MaxEvents 500 | Where-Object {{ $_.Properties[5].Value -eq '{safe}' }} |
    Select-Object -First 50 | ForEach-Object {{
        [pscustomobject]@{{
            when   = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
            server = $env:COMPUTERNAME
            ip     = $_.Properties[18].Value
            event  = 'logon'
        }}
    }}
    $events | ConvertTo-Json -Compress -Depth 3
    """
    all_events: list[dict] = []
    tasks = [_run_async(srv, script, creds) for srv in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            continue
        all_events.extend(result)
    all_events.sort(key=lambda e: e.get("when", ""), reverse=True)
    return all_events[:100]


# ---------------- Santé des serveurs ----------------
PS_HEALTH = r"""
$ErrorActionPreference = 'SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem

# CPU moyen (sur tous les processeurs logiques)
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average

# RAM : on utilise Win32_PerfFormattedData_PerfOS_Memory qui est fiable
# sur les VMs (contrairement à Win32_OperatingSystem.FreePhysicalMemory).
$ramTotBytes = [int64]$cs.TotalPhysicalMemory
$ramTotGB    = [math]::Round($ramTotBytes / 1GB, 1)

# AvailableMBytes = RAM libre + cache utilisable (la vraie "dispo")
$perf = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
if ($perf -and $perf.AvailableMBytes) {
    $ramFreeMB = [int64]$perf.AvailableMBytes
} else {
    # Fallback si la classe perf n'est pas dispo
    $ramFreeMB = [int64]($os.FreePhysicalMemory / 1024)
}
$ramFreeGB = [math]::Round($ramFreeMB / 1024, 1)
$ramUsedGB = [math]::Round($ramTotGB - $ramFreeGB, 1)

if ($ramTotGB -gt 0) {
    $ramPct = [int][math]::Round(($ramUsedGB / $ramTotGB) * 100, 0)
} else {
    $ramPct = 0
}

# Uptime lisible : "12j 04h" ou "4h 32m"
$up = (Get-Date) - $os.LastBootUpTime
if ($up.Days -ge 1) {
    $uptime = "{0}j {1:D2}h" -f $up.Days, $up.Hours
} elseif ($up.TotalHours -ge 1) {
    $uptime = "{0}h {1:D2}m" -f [int]$up.TotalHours, $up.Minutes
} else {
    $uptime = "{0}m" -f [int]$up.TotalMinutes
}

# Sessions : -2 car quser renvoie l'en-tête ET une ligne vide finale
$quserLines = & quser.exe 2>$null
if ($quserLines) {
    $sessions = @($quserLines | Where-Object { $_ -and $_.Trim() }).Count - 1
    if ($sessions -lt 0) { $sessions = 0 }
} else {
    $sessions = 0
}

[pscustomobject]@{
    name         = $env:COMPUTERNAME
    os           = ($os.Caption -replace 'Microsoft Windows ','')
    cpu_pct      = [int]$cpu
    ram_pct      = $ramPct
    ram_used_gb  = $ramUsedGB
    ram_total_gb = $ramTotGB
    uptime       = $uptime
    sessions     = $sessions
    reachable    = $true
} | ConvertTo-Json -Compress -Depth 3
"""


async def list_server_health(
    servers: list[str], creds: tuple[str, str]
) -> list[dict[str, Any]]:
    """Stats CPU/RAM/uptime pour chaque serveur (en parallèle)."""
    async def one(srv: str) -> dict:
        try:
            result = await _run_async(srv, PS_HEALTH, creds)
            return result[0] if result else {"name": srv, "reachable": False}
        except Exception as e:
            return {"name": srv, "reachable": False, "error": str(e)}

    return await asyncio.gather(*[one(s) for s in servers])
