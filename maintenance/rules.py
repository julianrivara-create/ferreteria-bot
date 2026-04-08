def evaluate_status(check_results, log_findings, thresholds):
    """
    Evaluates OK/WARN/FAIL status based on check results and log findings.
    """
    overall_status = "OK"
    reasons = []

    # Legacy compatibility: accept old shape {"check": "...", "status": "...", "reason": "..."}
    for res in check_results:
        legacy_status = str(res.get("status", "")).upper()
        if legacy_status in {"FAIL", "WARN", "OK"}:
            if legacy_status == "FAIL":
                overall_status = "FAIL"
                reasons.append(res.get("reason") or f"Check failed: {res.get('check', 'unknown')}")
            elif legacy_status == "WARN" and overall_status != "FAIL":
                overall_status = "WARN"
                if res.get("reason"):
                    reasons.append(res["reason"])

    # 1. HTTP Checks (new shape)
    for res in check_results:
        if res.get("type") in ["http_base", "http_health"]:
            if not res.get("ok"):
                overall_status = "FAIL"
                reasons.append(f"HTTP {res['type']} failure: {res.get('error', 'Status ' + str(res.get('status_code')))}")
            elif res.get("latency_ms", 0) > thresholds.get("http_timeout_ms", 5000) * 0.8:
                if overall_status != "FAIL":
                    overall_status = "WARN"
                reasons.append(f"High HTTP latency: {res['latency_ms']}ms")

    # 2. DB Check
    db_res = next((r for r in check_results if r.get("type") == "db"), None)
    if db_res:
        if not db_res.get("ok"):
            overall_status = "FAIL"
            reasons.append(f"Database connection failed: {db_res.get('error')}")

    # 3. Log Findings
    for finding in log_findings:
        sev = finding.get("severity", "WARN")
        if sev == "FAIL":
            overall_status = "FAIL"
        elif sev == "WARN" and overall_status == "OK":
            overall_status = "WARN"
        reasons.append(f"Log anomaly: {finding['rule_name']} ({finding['count']} matches)")

    return overall_status, reasons
