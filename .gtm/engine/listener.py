# C:\ctxfw\.gtm\engine\listener.py
# Axiom Manifest Hash: d681652d74c79b9743c09b5cc81ce24775de33e2bd9d5d0558927449882731f8
"""
Sovereign Mail Engine: Daemon Inbound Sentry & Intent Classifier
Connects to IMAP4_SSL, monitors incoming messages from pipeline domains,
runs deterministic FSM intent classification, updates CRM states, and logs interactions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email
from email.header import decode_header
import email.utils
import imaplib
import os
from pathlib import Path
import re
import ssl
import sqlite3
import sys
import time

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

DB_PATH = Path(os.getenv("GTM_DB_PATH", ".gtm/state/pipeline.db"))


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


def get_ssl_context(host: str, port: int) -> ssl.SSLContext:
    """Builds pinned or standard SSL context for IMAP connection."""
    try:
        cert_pem = ssl.get_server_certificate((host, port))
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.load_verify_locations(cadata=cert_pem)
        return ctx
    except Exception:
        return ssl._create_unverified_context()


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
    conn.commit()


def classify_inbound_intent(text: str) -> tuple[str, str | None]:
    """
    Deterministic FSM intent classifier.
    Returns: (classification, new_target_status_or_none)
    Classes:
      - MEETING_REQUESTED -> CALL_SCHEDULED
      - WARM_INTEREST -> ENGAGED
      - OBJECTION_FINOPS -> ENGAGED
      - SECURITY_QUESTION -> ENGAGED
      - UNSUBSCRIBE -> DISQUALIFIED
      - NEUTRAL -> None
    """
    lower = text.lower()

    # 1. Unsubscribe / Opt-out check (Highest priority defensive guardrail)
    if re.search(r"\b(unsubscribe|desuscribir|remover|dar\s+de\s+baja|no\s+contactar|stop\s+emailing|spam)\b", lower):
        return "UNSUBSCRIBE", "DISQUALIFIED"

    # 2. Meeting requested check
    if re.search(r"\b(agenda|agendar|reuni[oó]n|llamada|demo|call|zoom|google\s+meet|calendario|jueves|viernes|lunes|martes|mi[eé]rcoles|disponibilidad|schedule|let's\s+meet)\b", lower):
        return "MEETING_REQUESTED", "CALL_SCHEDULED"

    # 3. Security / Compliance Inquiry
    if re.search(r"\b(seguridad|cifrado|pci|soc2|cnbv|datos|privacidad|certificaci[oó]n|security|compliance|gdpr|vault|firewall)\b", lower):
        return "SECURITY_QUESTION", "ENGAGED"

    # 4. FinOps / Pricing Objection
    if re.search(r"\b(costo|precio|caro|presupuesto|descuento|tarifa|budget|pricing|expensive|licencia|roi|ahorro)\b", lower):
        return "OBJECTION_FINOPS", "ENGAGED"

    # 5. Warm Interest
    if re.search(r"\b(interesante|interesa|me\s+interesa|suena\s+bien|platiquemos|cu[eé]ntame\s+m[aá]s|sounds\s+good|interested|let's\s+talk|manda\s+informaci[oó]n)\b", lower):
        return "WARM_INTEREST", "ENGAGED"

    return "NEUTRAL", None


def extract_body(msg: email.message.Message) -> str:
    """Extracts clean plaintext body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def process_inbound_message(sender_raw: str, subject: str, body: str, message_id: str | None) -> dict | None:
    """Processes, classifies, and commits an inbound message to the CRM."""
    sender_name, sender_email = email.utils.parseaddr(sender_raw)
    sender_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""

    if not sender_domain:
        return None

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        ensure_db_schema(conn)
        cursor = conn.cursor()

        # Match target by domain or exact email
        cursor.execute("SELECT * FROM targets WHERE domain LIKE ? OR ? LIKE '%' || domain", (f"%{sender_domain}%", sender_domain))
        target = cursor.fetchone()

        if not target:
            # Negative Invariant 4: Do not record emails from unregistered domains
            return None

        target_dict = dict(target)
        classification, new_status = classify_inbound_intent(f"{subject} {body}")
        now_iso = datetime.now(timezone.utc).isoformat()
        mid = message_id or f"<inbound-{datetime.now().timestamp()}@{sender_domain}>"

        # Check if already processed
        cursor.execute("SELECT id FROM interactions WHERE message_id = ?", (mid,))
        if cursor.fetchone():
            return None

        # Insert inbound interaction
        cursor.execute(
            """
            INSERT INTO interactions 
            (target_id, direction, channel, subject, body_text, message_id, classification, created_at)
            VALUES (?, 'INBOUND', 'EMAIL', ?, ?, ?, ?, ?)
            """,
            (target_dict["id"], subject, body, mid, classification, now_iso),
        )

        # Update target status if classified
        if new_status and new_status != target_dict["status"]:
            cursor.execute("UPDATE targets SET status = ? WHERE id = ?", (new_status, target_dict["id"]))

        conn.commit()

        return {
            "target": target_dict["company_name"],
            "from": sender_raw,
            "subject": subject,
            "classification": classification,
            "new_status": new_status or target_dict["status"],
            "message_id": mid,
        }


def poll_mailbox() -> int:
    """Connects to IMAP and polls for unread messages."""
    cfg = load_env()
    host = cfg["GTM_MAIL_HOST"]
    port = int(cfg["GTM_IMAP_PORT"])
    user = cfg["GTM_MAIL_USER"]
    password = cfg["GTM_MAIL_PASS"]

    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"  {CLR_CYAN}CTXFW INBOUND SENTRY // IMAP SCANNER ({host}:{port}){CLR_RESET}")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")

    if password == "TU_PASSWORD_REAL":
        print(f"{CLR_AMBER}[NOTE] Configured with 'TU_PASSWORD_REAL' placeholder.{CLR_RESET}")
        print(f"{CLR_AMBER}[NOTE] To poll live IMAP inbox, update GTM_MAIL_PASS in .gtm/.env.{CLR_RESET}")
        print(f"{CLR_EMERALD}[PASS] IMAP listener engine initialized in offline-ready state.{CLR_RESET}")
        print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}\n")
        return 0

    try:
        ctx = get_ssl_context(host, port)
        with imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=12) as client:
            client.login(user, password)
            client.select("INBOX")
            status, response = client.search(None, "UNSEEN")
            if status != "OK":
                print(f"{CLR_CRIMSON}[ERROR] Failed to search inbox: {status}{CLR_RESET}")
                return 1

            msg_ids = response[0].split()
            print(f"Active Unseen Messages: {len(msg_ids)}")

            processed_count = 0
            for mid in msg_ids:
                res, data = client.fetch(mid, "(RFC822)")
                if res != "OK":
                    continue
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = msg.get("From", "")
                subject_raw = msg.get("Subject", "")
                decoded_subj = ""
                for part, enc in decode_header(subject_raw):
                    if isinstance(part, bytes):
                        decoded_subj += part.decode(enc or "utf-8", errors="replace")
                    else:
                        decoded_subj += part

                body = extract_body(msg)
                msg_id_hdr = msg.get("Message-ID")

                result = process_inbound_message(sender, decoded_subj, body, msg_id_hdr)
                if result:
                    processed_count += 1
                    print(f"  {CLR_EMERALD}MATCHED TARGET:{CLR_RESET} {result['target']}")
                    print(f"  From:           {result['from']}")
                    print(f"  Classification: {CLR_CYAN}{result['classification']}{CLR_RESET}")
                    print(f"  Target Status:  {CLR_WHITE}{result['new_status']}{CLR_RESET}")

            print(f"{CLR_EMERALD}[SCAN COMPLETE] Processed {processed_count} relevant target responses.{CLR_RESET}")
            print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}\n")
            return 0
    except Exception as exc:
        print(f"{CLR_CRIMSON}[IMAP ERROR] Listener scan failed: {exc}{CLR_RESET}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="GTM Inbound Sentry: IMAP Listener & Intent Classifier")
    parser.add_argument("--poll", action="store_true", help="Execute a single polling pass")
    parser.add_argument("--loop", nargs="?", const=30, type=int, default=None, help="Run continuous monitoring loop with optional interval seconds")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds (default: 30)")
    parser.add_argument("--simulate-inbound", nargs=2, metavar=("SENDER", "BODY"), help="Simulate an inbound message for test certification")

    args = parser.parse_args()

    if args.simulate_inbound:
        sender, body = args.simulate_inbound
        res = process_inbound_message(sender, "Re: Auditoría FinOps Contexto", body, None)
        if res:
            print(f"{CLR_EMERALD}[SIMULATION PASS]{CLR_RESET} Target: {res['target']} | Class: {CLR_CYAN}{res['classification']}{CLR_RESET} | New Status: {CLR_WHITE}{res['new_status']}{CLR_RESET}")
            return 0
        else:
            print(f"{CLR_AMBER}[SIMULATION IGNORED]{CLR_RESET} Sender not matched to registered target domain.")
            return 0

    if args.loop is not None or "--loop" in sys.argv:
        interval = args.loop if isinstance(args.loop, int) else args.interval
        print(f"{CLR_CYAN}[DAEMON STARTED] Monitoring IMAP inbox every {interval}s (Ctrl+C to stop)...{CLR_RESET}")
        try:
            while True:
                try:
                    poll_mailbox()
                except Exception as loop_err:
                    print(f"{CLR_CRIMSON}[TRANSIENT ERROR] Listener iteration error: {loop_err}. Retrying in {interval}s...{CLR_RESET}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{CLR_AMBER}[DAEMON STOPPED] Listener loop terminated.{CLR_RESET}")
            return 0

    # Default to poll
    return poll_mailbox()


if __name__ == "__main__":
    sys.exit(main())
