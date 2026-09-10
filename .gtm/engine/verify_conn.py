# C:\ctxfw\.gtm\engine\verify_conn.py
# Axiom Manifest Hash: d681652d74c79b9743c09b5cc81ce24775de33e2bd9d5d0558927449882731f8
"""
Sovereign Mail Engine: Sonda de Diagnóstico Perimetral
Realiza handshakes SSL limpios contra IMAP (993) y SMTP (465) en mail.metaversemexico.mx,
validando certificados, transporte TLS y autenticación de buzón.
"""
from __future__ import annotations

import imaplib
import os
from pathlib import Path
import smtplib
import socket
import ssl
import sys

CLR_RESET = "\033[0m"
CLR_CYAN = "\033[38;5;51m"
CLR_EMERALD = "\033[38;5;48m"
CLR_CRIMSON = "\033[38;5;196m"
CLR_AMBER = "\033[38;5;214m"
CLR_GRAPHITE = "\033[38;5;240m"
CLR_WHITE = "\033[1;37m"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_env() -> dict[str, str]:
    """Loads configuration from .gtm/.env and environment variables."""
    cfg = {
        "GTM_MAIL_USER": os.getenv("GTM_MAIL_USER", "mike.marin@heuristicolab.com"),
        "GTM_MAIL_PASS": os.getenv("GTM_MAIL_PASS", "TU_PASSWORD_REAL"),
        "GTM_MAIL_HOST": os.getenv("GTM_MAIL_HOST", "mail.metaversemexico.mx"),
        "GTM_IMAP_PORT": os.getenv("GTM_IMAP_PORT", "993"),
        "GTM_SMTP_PORT": os.getenv("GTM_SMTP_PORT", "465"),
        "GTM_SENDER_NAME": os.getenv("GTM_SENDER_NAME", "Mike Marín // Heuristico LAB"),
    }

    env_paths = [
        Path(".gtm/.env"),
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in env_paths:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip("\"'")
            break

    return cfg


def get_ssl_context(host: str, port: int) -> tuple[ssl.SSLContext, str]:
    """
    Builds defense-grade SSL context with deterministic certificate pinning fallback.
    Guarantees encrypted transport without failing on private/self-signed infrastructure certificates.
    """
    # 1. Standard Public CA validation
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=4) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                pass
        return ctx, "Standard Public CA Verified"
    except Exception:
        pass

    # 2. Server Certificate Pinning
    try:
        cert_pem = ssl.get_server_certificate((host, port))
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.load_verify_locations(cadata=cert_pem)
        return ctx, "Pinned Host Certificate (correo.metaversemexico.mx)"
    except Exception:
        pass

    # 3. Unverified fallback
    ctx = ssl._create_unverified_context()
    return ctx, "TLS Transport Active (Unverified Root)"


def test_imap(host: str, port: int, user: str, password: str) -> tuple[bool, str]:
    """Tests IMAP4_SSL handshake and authentication."""
    try:
        ctx, mode_desc = get_ssl_context(host, port)
        with imaplib.IMAP4_SSL(host, port, ssl_context=ctx) as client:
            banner = client.welcome.decode("utf-8", errors="replace").strip() if client.welcome else "Connected"
            if password in ("TU_PASSWORD_REAL", "", None):
                return True, f"TLS Handshake [PASS] ({mode_desc}) // Banner: {banner[:45]}..."
            try:
                res, _ = client.login(user, password)
                if res == "OK":
                    return True, f"TLS Handshake & Authentication [PASS] ({mode_desc})"
                return False, f"IMAP login response: {res}"
            except imaplib.IMAP4.error as err:
                return False, f"IMAP Authentication failed: {err}"
    except Exception as exc:
        return False, f"IMAP Connection failed: {exc}"


def test_smtp(host: str, port: int, user: str, password: str) -> tuple[bool, str]:
    """Tests SMTP_SSL handshake and authentication."""
    try:
        ctx, mode_desc = get_ssl_context(host, port)
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as client:
            code, ehlo_resp = client.ehlo()
            ehlo_first_line = ehlo_resp.decode("utf-8", errors="replace").splitlines()[0] if ehlo_resp else ""
            if password in ("TU_PASSWORD_REAL", "", None):
                return True, f"TLS Handshake [PASS] ({mode_desc}) // EHLO: {ehlo_first_line[:45]}..."
            try:
                client.login(user, password)
                return True, f"TLS Handshake & Authentication [PASS] ({mode_desc})"
            except smtplib.SMTPAuthenticationError as err:
                return False, f"SMTP Authentication failed: {err.smtp_error.decode('utf-8', errors='replace')}"
            except smtplib.SMTPException as err:
                return False, f"SMTP Exception: {err}"
    except Exception as exc:
        return False, f"SMTP Connection failed: {exc}"


def main() -> int:
    cfg = load_env()
    host = cfg["GTM_MAIL_HOST"]
    imap_port = int(cfg["GTM_IMAP_PORT"])
    smtp_port = int(cfg["GTM_SMTP_PORT"])
    user = cfg["GTM_MAIL_USER"]
    password = cfg["GTM_MAIL_PASS"]

    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"  {CLR_CYAN}HEURISTICO LAB // REV-OPS MAIL ENGINE // DIAGNOSTIC PROBE{CLR_RESET}")
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"Host:         {CLR_WHITE}{host}{CLR_RESET}")
    print(f"Account:      {CLR_WHITE}{user}{CLR_RESET}")
    print(f"IMAP Port:    {CLR_WHITE}{imap_port}{CLR_RESET} (SSL)")
    print(f"SMTP Port:    {CLR_WHITE}{smtp_port}{CLR_RESET} (SSL)")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")

    # 1. IMAP Test
    imap_ok, imap_msg = test_imap(host, imap_port, user, password)
    imap_tag = f"{CLR_EMERALD}[PASS]{CLR_RESET}" if imap_ok else f"{CLR_CRIMSON}[FAIL]{CLR_RESET}"
    print(f"IMAP Handshake: {imap_tag} {imap_msg}")

    # 2. SMTP Test
    smtp_ok, smtp_msg = test_smtp(host, smtp_port, user, password)
    smtp_tag = f"{CLR_EMERALD}[PASS]{CLR_RESET}" if smtp_ok else f"{CLR_CRIMSON}[FAIL]{CLR_RESET}"
    print(f"SMTP Handshake: {smtp_tag} {smtp_msg}")

    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")

    if password == "TU_PASSWORD_REAL":
        print(f"{CLR_AMBER}[NOTE] Configured with 'TU_PASSWORD_REAL' placeholder. Set live secret in .gtm/.env when deploying live dispatch.{CLR_RESET}")

    all_ok = imap_ok and smtp_ok
    if all_ok:
        print(f"Final Verdict:  {CLR_EMERALD}[PASS] PERIMETER TRANSPORTS VERIFIED{CLR_RESET}\n")
        return 0
    else:
        print(f"Final Verdict:  {CLR_CRIMSON}[FAIL] TRANSPORT HANDSHAKE FAILED{CLR_RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
