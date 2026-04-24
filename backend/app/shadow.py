"""
Module Shadow — génère un fichier .bat qui lance mstsc.exe en mode shadow.

Méthode identique à Galinette cendrée originale :
  mstsc.exe /shadow:<ID> /v:<SERVER> [/control] [/noConsentPrompt]

Le fichier .rdp standard ne supporte pas le shadow de manière fiable
(limitation Microsoft). On passe donc par un petit .bat qui exécute la
commande directement, exactement comme l'app .NET originale.
"""

MODES = {
    "view":          {"control": False, "noconsent": False},  # /shadow:ID /v:SRV
    "control":       {"control": True,  "noconsent": False},  # + /control
    "force-view":    {"control": False, "noconsent": True},   # + /noConsentPrompt
    "force-control": {"control": True,  "noconsent": True},   # + /control /noConsentPrompt
}


def build_shadow_rdp(server: str, session_id: int, mode: str) -> str:
    """
    Génère un fichier .bat qui lance mstsc en mode shadow.
    Le nom de la fonction reste 'build_shadow_rdp' pour compat avec le reste du code,
    mais on renvoie désormais du contenu .bat.
    """
    cfg = MODES.get(mode, MODES["force-control"])
    flags = [f"/shadow:{session_id}", f"/v:{server}"]
    if cfg["control"]:
        flags.append("/control")
    if cfg["noconsent"]:
        flags.append("/noConsentPrompt")

    cmdline = "mstsc.exe " + " ".join(flags)

    # .bat auto-élévé : si pas admin, il se relance en tant qu'admin via PowerShell,
    # puis lance mstsc avec les droits nécessaires pour le shadow noConsentPrompt.
    lines = [
        "@echo off",
        f"REM Galinette Web — shadow {mode} sur {server} session #{session_id}",
        "",
        "REM Auto-élévation UAC si pas déjà admin",
        'net session >nul 2>&1',
        "if %errorLevel% neq 0 (",
        '    powershell -Command "Start-Process cmd -ArgumentList \'/c\',\'%~f0\' -Verb RunAs"',
        "    exit /b",
        ")",
        "",
        f"start \"\" {cmdline}",
    ]
    return "\r\n".join(lines) + "\r\n"

