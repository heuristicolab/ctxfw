# C:\ctxfw\.gtm\agents\01_scout.py
# Axiom Manifest Hash: 0dc85b41b49d17ac338d5f9d44257daeef83cbae0b0ac41021d24747f854d300
import sqlite3
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

CLR_RESET = "\033[0m"
CLR_CYAN = "\033[38;5;51m"
CLR_EMERALD = "\033[38;5;48m"
CLR_CRIMSON = "\033[38;5;196m"
CLR_GRAPHITE = "\033[38;5;240m"
CLR_WHITE = "\033[1;37m"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DB_PATH = Path(".gtm/state/pipeline.db")
RULES_PATH = Path(".gtm/state/icp_rules.json")

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT UNIQUE NOT NULL,
                domain TEXT NOT NULL,
                vertical TEXT NOT NULL,
                dev_count INTEGER NOT NULL,
                tech_lead_name TEXT,
                tech_lead_title TEXT,
                ai_tools_detected BOOLEAN NOT NULL,
                compliance_scope TEXT,
                icp_score INTEGER NOT NULL,
                status TEXT DEFAULT 'DISCOVERED',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

def calculate_icp(vertical: str, devs: int, ai_tools: bool, compliance: str) -> int:
    score = 0
    if not RULES_PATH.exists():
        return 50
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        rules = json.load(f)

    if vertical.lower() in [v.lower() for v in rules["target_verticals"]]:
        score += rules["scoring_weights"]["regulated_vertical"]
    
    bounds = rules["headcount_dev_sweet_spot"]
    if bounds["min"] <= devs <= bounds["max"]:
        score += rules["scoring_weights"]["headcount_match"]
    elif devs > bounds["max"]:
        score += rules["scoring_weights"]["headcount_match"] // 2
        
    if ai_tools:
        score += rules["scoring_weights"]["ai_tooling_active"]
        
    if compliance and compliance.strip():
        score += rules["scoring_weights"]["compliance_exposure"]
        
    return min(100, score)

def ingest_target(name: str, domain: str, vertical: str, devs: int, lead: str, title: str, ai: bool, comp: str):
    init_db()
    score = calculate_icp(vertical, devs, ai, comp)
    now = datetime.now(timezone.utc).isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO targets (company_name, domain, vertical, dev_count, tech_lead_name, tech_lead_title, ai_tools_detected, compliance_scope, icp_score, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED', ?)
            ON CONFLICT(company_name) DO UPDATE SET
                dev_count=excluded.dev_count,
                icp_score=excluded.icp_score,
                compliance_scope=excluded.compliance_scope
        """, (name, domain, vertical, devs, lead, title, ai, comp, score, now))
        conn.commit()

    verdict_tag = f"{CLR_EMERALD}[QUALIFIED]{CLR_RESET}" if score >= 70 else f"{CLR_CRIMSON}[REJECTED]{CLR_RESET}"
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"  {CLR_CYAN}GTM RECON SCOUT // INGEST REPORT{CLR_RESET}")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")
    print(f"Company:      {CLR_WHITE}{name}{CLR_RESET} ({domain})")
    print(f"Profile:      Vertical: {vertical.upper()} | Squad: {devs} devs")
    print(f"ICP Score:    {CLR_WHITE}{score}/100{CLR_RESET} -> {verdict_tag}")
    print(f"Primary Lead: {lead} [{title}]")
    print(f"{CLR_GRAPHITE}------------------------------------------------------------------------{CLR_RESET}")

def list_pipeline():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT company_name, vertical, dev_count, icp_score, status, tech_lead_name FROM targets ORDER BY icp_score DESC").fetchall()
    
    if not rows:
        print(f"{CLR_CRIMSON}[!] No targets recorded in pipeline.db{CLR_RESET}")
        return

    print(f"\n{CLR_CYAN}========================================================================{CLR_RESET}")
    print(f"  {CLR_WHITE}HEURISTICO LAB // GTM RADAR PIPELINE (ACTIVE TARGETS){CLR_RESET}")
    print(f"{CLR_CYAN}========================================================================{CLR_RESET}")
    print(f"{CLR_GRAPHITE}{'COMPANY':<20} {'VERTICAL':<14} {'DEVS':<6} {'ICP':<6} {'STATUS':<14} {'CONTACT'}{CLR_RESET}")
    print(f"{CLR_GRAPHITE}{'-'*72}{CLR_RESET}")
    for r in rows:
        color = CLR_EMERALD if r[3] >= 70 else CLR_CRIMSON
        print(f"{r[0]:<20} {r[1]:<14} {r[2]:<6} {color}{r[3]:<6}{CLR_RESET} {r[4]:<14} {r[5]}")
    print(f"{CLR_CYAN}========================================================================{CLR_RESET}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GTM Target Scout Agent")
    sub = parser.add_subparsers(dest="subcommand")

    add_p = sub.add_parser("add")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--domain", required=True)
    add_p.add_argument("--vertical", required=True)
    add_p.add_argument("--devs", type=int, required=True)
    add_p.add_argument("--lead", required=True)
    add_p.add_argument("--title", default="Head of Engineering", nargs="?", const="Head of Engineering")
    add_p.add_argument("--ai", action="store_true", default=True)
    add_p.add_argument("--compliance", default="", nargs="?", const="")

    sub.add_parser("list")

    args = parser.parse_args()
    if args.subcommand == "add":
        ingest_target(args.name, args.domain, args.vertical, args.devs, args.lead, args.title, args.ai, args.compliance)
    elif args.subcommand == "list":
        list_pipeline()
    else:
        parser.print_help()
