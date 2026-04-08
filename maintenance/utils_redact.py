import re

# Compiled regex for performance
PATTERNS = {
    "db_url": re.compile(r"(postgres(?:ql)?://)(?:[^:@\s]+):(?:[^:@\s]+)@"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "bearer_token": re.compile(r"(?i)bearer\s+[a-zA-Z0-9._-]+"),
    "api_key": re.compile(r"(?i)(?:api_key|token|secret|password|pass)(?:[\s:=\"]+)([a-zA-Z0-9]{8,})"),
}

def redact(text: str) -> str:
    """Redacts sensitive information from text using regex."""
    if not text or not isinstance(text, str):
        return text
    
    # Redact Database URLs (keep protocol, hide credentials)
    text = PATTERNS["db_url"].sub(r"\1[REDACTED]:[REDACTED]@", text)
    
    # Redact API Keys / Secrets in common formats
    text = PATTERNS["api_key"].sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED]"), text)
    
    # Redact Bearer tokens
    text = PATTERNS["bearer_token"].sub("Bearer [REDACTED]", text)
    
    # Redact Emails
    text = PATTERNS["email"].sub("[EMAIL]", text)
    
    # Redact IP addresses
    text = PATTERNS["ipv4"].sub("[IP_REDACTED]", text)
    
    return text


def redact_secrets(text: str) -> str:
    """Backward-compatible alias used by tests and older callers."""
    return redact(text)
