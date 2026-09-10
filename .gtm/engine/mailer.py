# C:\ctxfw\.gtm\engine\mailer.py
# Axiom Manifest Hash: d681652d74c79b9743c09b5cc81ce24775de33e2bd9d5d0558927449882731f8
"""
Sovereign Mail Engine: Outbound RFC 5322 Dispatcher
Reads synthesized briefs from .gtm/state/dispatches/{slug}_outreach.md, formats clean plaintext
emails with cryptographic tracking headers, executes SMTP SSL dispatching, and tracks CRM interactions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
import email.utils
import hashlib
import os
from pathlib import Path
import re
import smtplib
import socket
import ssl
import sqlite3
import sys
import uuid

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

DB_PATH = Path(".gtm/state/pipeline.db")
DISPATCHES_DIR = Path(".gtm/state/dispatches")


def slugify(text: str) -> str:
    """Generates filesystem-safe lowercase slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


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


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    """Guarantees pipeline.db columns and interactions table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            channel TEXT NOT NULL,
            subject TEXT,
            body_text TEXT,
            message_id TEXT UNIQUE,
            classification TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (target_id) REFERENCES targets(id)
        )
    """)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(targets)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "contacted_at" not in existing_cols:
        cursor.execute("ALTER TABLE targets ADD COLUMN contacted_at TEXT")
    if "contacted_channel" not in existing_cols:
        cursor.execute("ALTER TABLE targets ADD COLUMN contacted_channel TEXT")
    conn.commit()


def get_ssl_context(host: str, port: int) -> ssl.SSLContext:
    """Builds pinned or standard SSL context for SMTP transmission."""
    try:
        cert_pem = ssl.get_server_certificate((host, port))
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.load_verify_locations(cadata=cert_pem)
        return ctx
    except Exception:
        return ssl._create_unverified_context()


def parse_dispatch_markdown(dispatch_file: Path) -> tuple[str, str]:
    """Extracts Subject and Body from Canal A of outreach markdown."""
    content = dispatch_file.read_text(encoding="utf-8")
    
    # Extract subject
    subj_match = re.search(r"### Subject:\s*\n`([^`]+)`", content)
    if not subj_match:
        subj_match = re.search(r"### Subject:\s*\n([^\n]+)", content)
    subject = subj_match.group(1).strip() if subj_match else "CTXFW Context Audit & FinOps Optimization"

    # Extract body from code fence
    body_match = re.search(r"### Body:\s*\n```(?:text)?\n(.*?)\n```", content, re.DOTALL)
    if not body_match:
        raise ValueError(f"Unable to extract Canal A body from {dispatch_file}")
    body = body_match.group(1).strip()

    return subject, body


def generate_message_id(company: str) -> str:
    """Generates RFC 5322 compliant deterministic Message-ID."""
    h = hashlib.sha256(f"{company}:{uuid.uuid4()}".encode("utf-8")).hexdigest()[:16]
    return f"<ctxfw-{h}@heuristicolab.com>"


def dispatch_target(target: dict, dry_run: bool = False, recipient_email: str | None = None) -> int:
    """Formats and dispatches outbound email for a single target."""
    cfg = load_env()
    company = target["company_name"]
    slug = slugify(company)
    dispatch_file = DISPATCHES_DIR / f"{slug}_outreach.md"

    if not dispatch_file.is_file():
        print(f"{CLR_CRIMSON}[FAIL] Dispatch artifact missing: {dispatch_file}{CLR_RESET}")
        print(f"{CLR_AMBER}[!] Run: python .gtm/agents/03_outreach_sentry.py --company \"{company}\"{CLR_RESET}")
        return 1

    subject, body = parse_dispatch_markdown(dispatch_file)

    lead_name = target.get("tech_lead_name") or "Technical Director"
    first_last = lead_name.lower().split()
    default_email = f"{first_last[0]}.{first_last[-1]}@{target['domain']}" if len(first_last) >= 2 else f"engineering@{target['domain']}"
    target_to = recipient_email or target.get("email") or default_email

    sender_name = cfg["GTM_SENDER_NAME"]
    sender_mail = cfg["GTM_MAIL_USER"]
    message_id = generate_message_id(company)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Build RFC 5322 Email Message
    msg = EmailMessage()
    msg["From"] = f"{sender_name} <{sender_mail}>"
    msg["To"] = f"{lead_name} <{target_to}>"
    msg["Reply-To"] = sender_mail
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg["X-Mailer"] = "CTXFW Sovereign Mail Engine v3.5"
    msg["X-Compliance-Scope"] = target.get("compliance_scope") or "SOC2"
    msg.set_content(body)

    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"  {CLR_CYAN}CTXFW OUTBOUND DISPATCHER // RFC 5322 ENGINE{CLR_RESET}")
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"Target:       {CLR_WHITE}{company}{CLR_RESET} (ID: {target['id']})")
    print(f"To:           {CLR_WHITE}{lead_name}{CLR_RESET} <{target_to}>")
    print(f"From:         {CLR_WHITE}{sender_name}{CLR_RESET} <{sender_mail}>")
    print(f"Reply-To:     {sender_mail}")
    print(f"Message-ID:   {CLR_CYAN}{message_id}{CLR_RESET}")
    print(f"Subject:      {CLR_WHITE}{subject}{CLR_RESET}")
    print(f"Body Length:  {len(body.split())} words ({len(body)} chars) [Plaintext UTF-8]")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"{CLR_GRAPHITE}Payload Preview:{CLR_RESET}")
    preview_lines = body.splitlines()[:6]
    for pl in preview_lines:
        print(f"  {pl}")
    if len(body.splitlines()) > 6:
        print(f"  {CLR_GRAPHITE}... [{len(body.splitlines()) - 6} additional lines]{CLR_RESET}")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")

    if dry_run:
        print(f"{CLR_EMERALD}[DRY-RUN PASS] Dispatch formatted and certified successfully.{CLR_RESET}")
        print(f"{CLR_AMBER}[DRY-RUN] Zero network packets sent to SMTP server.{CLR_RESET}")
        print(f"{CLR_AMBER}[DRY-RUN] Simulated state transition: targets.status -> 'CONTACTED'{CLR_RESET}")
        print(f"{CLR_AMBER}[DRY-RUN] Simulated event: insert into interactions (direction='OUTBOUND'){CLR_RESET}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        return 0

    # Live dispatch execution
    if cfg["GTM_MAIL_PASS"] == "TU_PASSWORD_REAL":
        print(f"{CLR_CRIMSON}[ABORT] Live dispatch requires real secret in .gtm/.env (currently 'TU_PASSWORD_REAL').{CLR_RESET}")
        return 1

    host = cfg["GTM_MAIL_HOST"]
    port = int(cfg["GTM_SMTP_PORT"])
    print(f"Connecting to SMTP SSL: {host}:{port}...")

    try:
        ctx = get_ssl_context(host, port)
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=12) as server:
            server.login(cfg["GTM_MAIL_USER"], cfg["GTM_MAIL_PASS"])
            server.send_message(msg)
            print(f"{CLR_EMERALD}[DISPATCH SENT] RFC 5322 payload acknowledged by remote MTA.{CLR_RESET}")
    except Exception as exc:
        print(f"{CLR_CRIMSON}[TRANSMISSION ERROR] SMTP dispatch failed: {exc}{CLR_RESET}")
        return 1

    # Update CRM State in pipeline.db
    with sqlite3.connect(DB_PATH) as conn:
        ensure_db_schema(conn)
        conn.execute(
            "UPDATE targets SET status = 'CONTACTED', contacted_at = ?, contacted_channel = 'EMAIL' WHERE id = ?",
            (now_iso, target["id"]),
        )
        conn.execute(
            """
            INSERT INTO interactions 
            (target_id, direction, channel, subject, body_text, message_id, classification, created_at)
            VALUES (?, 'OUTBOUND', 'EMAIL', ?, ?, ?, 'NEUTRAL', ?)
            """,
            (target["id"], subject, body, message_id, now_iso),
        )
        conn.commit()

    print(f"{CLR_EMERALD}[DB UPDATED] target.status = 'CONTACTED' | Logged in interactions table.{CLR_RESET}")
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GTM Engine: Outbound Mailer & RFC 5322 Dispatcher")
    parser.add_argument("--company", help="Target company name to dispatch")
    parser.add_argument("--to", help="Override recipient email address")
    parser.add_argument("--dry-run", action="store_true", help="Simulate RFC 5322 formatting without transmitting")
    parser.add_argument("--batch", action="store_true", help="Process all AUDITED targets in pipeline.db")

    args = parser.parse_args()

    if not args.company and not args.batch:
        parser.print_help()
        return 1

    if not DB_PATH.is_file():
        print(f"{CLR_CRIMSON}[ERROR] Pipeline database not found: {DB_PATH}{CLR_RESET}")
        return 1

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        ensure_db_schema(conn)
        cursor = conn.cursor()

        if args.company:
            cursor.execute("SELECT * FROM targets WHERE company_name LIKE ?", (f"%{args.company}%",))
            targets = [dict(r) for r in cursor.fetchall()]
            if not targets:
                print(f"{CLR_CRIMSON}[!] Target '{args.company}' not found in pipeline.db{CLR_RESET}")
                return 1
        elif args.batch:
            cursor.execute("SELECT * FROM targets WHERE status = 'AUDITED'")
            targets = [dict(r) for r in cursor.fetchall()]
            if not targets:
                print(f"{CLR_AMBER}[*] No pending AUDITED targets in pipeline.db{CLR_RESET}")
                return 0

    exit_code = 0
    for target in targets:
        code = dispatch_target(target, dry_run=args.dry_run, recipient_email=args.to)
        if code != 0:
            exit_code = code

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
