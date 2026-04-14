#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_intelligence.py
==========================
Generates a summary report of unresolved terms from the hardware store bot.
Used for catalog and synonym maintenance.
"""

import os
import sys
from pathlib import Path

# Add project root to path so we can import bot_sales
sys.path.append(str(Path(__file__).resolve().parents[1]))

from bot_sales.ferreteria_unresolved_log import summarize_log

def main():
    print("=" * 60)
    print("FERRETERIA INTELLIGENCE SUMMARY")
    print("=" * 60)
    
    # Check for specific log file via env or default
    log_path = os.environ.get("FERRETERIA_UNRESOLVED_LOG")
    if log_path:
        print(f"Using log: {log_path}")
    
    summary = summarize_log()
    
    if summary["total"] == 0:
        print("\nNo unresolved terms found in log.")
        print("Everything is running smoothly! 🚀")
        return

    print(f"\nTotal unresolved items: {summary['total']}")
    
    print("\nDISTRIBUTION BY STATUS:")
    for status, count in summary["by_status"].items():
        percentage = (count / summary["total"]) * 100
        print(f"  - {status:25}: {count:4} ({percentage:5.1f}%)")
    
    print("\nTOP UNRESOLVED TERMS (Catalog growth candidates):")
    print("-" * 50)
    print(f"{'Term':35} | {'Count':5}")
    print("-" * 50)
    for entry in summary["top_terms"]:
        print(f"{entry['term']:35} | {entry['count']:5}")
    
    print("\n" + "=" * 60)
    print("END OF REPORT")
    print("=" * 60)

if __name__ == "__main__":
    main()
