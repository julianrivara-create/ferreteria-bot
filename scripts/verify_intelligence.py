#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_intelligence.py
======================
Verification script to prove the new intelligence rules (synonyms, families, 
and clarifications) are working as expected after the April 14th upgrade.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from bot_sales.knowledge.loader import KnowledgeLoader
from bot_sales import ferreteria_quote as fq

def test_term(message, knowledge, expected_family=None, expected_normalized=None):
    print(f"\nTESTING: \"{message}\"")
    items = fq.parse_quote_items(message)
    
    if not items:
        print("  ❌ No items parsed.")
        return False

    item = items[0]
    # We simulate the scoring/family detection logic which usually happens in process_message
    # But for a basic check, let's see how the quote engine sees it.
    
    # Process normalization
    normalized = item.get("normalized", "")
    print(f"  - Normalized: {normalized}")
    
    # Process family detection
    family = fq.detect_product_family(item, knowledge)
    print(f"  - Family Detected: {family}")
    
    # Process clarification
    prompt = fq.build_clarification_prompt(item, knowledge)
    print(f"  - Clarification Prompt: {prompt}")

    success = True
    if expected_family and family != expected_family:
        print(f"  ❌ Expected family '{expected_family}', got '{family}'")
        success = False
    
    if expected_normalized and expected_normalized not in normalized:
        print(f"  ❌ Expected normalized to contain '{expected_normalized}'")
        success = False

    if success:
        print("  ✅ PASS")
    return success

def main():
    print("=" * 60)
    print("FERRETERIA INTELLIGENCE VERIFICATION TEST")
    print("=" * 60)
    
    # 1. Load the actual Ferretería knowledge
    loader = KnowledgeLoader(tenant_id="ferreteria")
    knowledge = loader.load_all()
    print(f"Successfully loaded knowledge for tenant: ferreteria")
    
    tests = [
        {
            "msg": "cano pvc de 20mm",
            "expected_normalized": "cano", # Synonym map should hit 'cano'
            "expected_family": "cano"
        },
        {
            "msg": "mecha para madera",
            "expected_family": "mecha"
        },
        {
            "msg": "electrovalvula industrial",
            "expected_family": "electrovalvula"
        },
        {
            "msg": "broca widia",
            "expected_family": "mecha" # We standardized widia to mecha family
        }
    ]
    
    results = []
    for t in tests:
        res = test_term(t["msg"], knowledge, t.get("expected_family"), t.get("expected_normalized"))
        results.append(res)
    
    print("\n" + "=" * 60)
    if all(results):
        print("RESULT: ALL TESTS PASSED! The new intelligence is active.")
    else:
        print("RESULT: SOME TESTS FAILED. Please check the logs.")
    print("=" * 60)

if __name__ == "__main__":
    main()
