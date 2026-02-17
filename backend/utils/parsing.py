"""
Pixel Agent - Email Parsing Utilities
Parse raw pasted email text into structured fields.
"""

import re
from typing import Dict, Optional


def parse_email_text(raw_text: str) -> Dict[str, str]:
    """
    Parse pasted email text into structured fields.

    Handles common formats:
    - Outlook-style headers (From: / To: / Subject: / Date:)
    - Gmail forwarded format
    - Plain body text (no headers)

    Returns dict with: sender_name, sender_email, to_list, cc_list,
                       subject, sent_at, body
    """
    result = {
        "sender_name": "",
        "sender_email": "",
        "to_list": "",
        "cc_list": "",
        "subject": "",
        "sent_at": "",
        "body": "",
    }

    if not raw_text or not raw_text.strip():
        return result

    lines = raw_text.strip().split("\n")

    # Try to detect if text has email headers
    header_patterns = {
        "from": re.compile(r"^(?:From|FROM)\s*:\s*(.+)$", re.IGNORECASE),
        "to": re.compile(r"^(?:To|TO)\s*:\s*(.+)$", re.IGNORECASE),
        "cc": re.compile(r"^(?:Cc|CC)\s*:\s*(.+)$", re.IGNORECASE),
        "subject": re.compile(r"^(?:Subject|SUBJECT)\s*:\s*(.+)$", re.IGNORECASE),
        "date": re.compile(r"^(?:Date|DATE|Sent|SENT)\s*:\s*(.+)$", re.IGNORECASE),
    }

    headers_found = {}
    body_start_idx = 0
    in_headers = True

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Empty line after headers = start of body
        if in_headers and stripped == "" and headers_found:
            body_start_idx = i + 1
            in_headers = False
            continue

        if in_headers:
            matched = False
            for key, pattern in header_patterns.items():
                match = pattern.match(stripped)
                if match:
                    headers_found[key] = match.group(1).strip()
                    matched = True
                    break

            # If we haven't found any headers yet and this line doesn't match,
            # treat everything as body
            if not matched and not headers_found:
                body_start_idx = 0
                in_headers = False

    # Extract body
    body_lines = lines[body_start_idx:]
    result["body"] = "\n".join(body_lines).strip()

    # If no body found but we have the full text, use it all
    if not result["body"] and not headers_found:
        result["body"] = raw_text.strip()

    # Parse From field
    if "from" in headers_found:
        from_val = headers_found["from"]
        result["sender_name"], result["sender_email"] = _parse_from_field(from_val)

    # Set other fields
    result["to_list"] = headers_found.get("to", "")
    result["cc_list"] = headers_found.get("cc", "")
    result["subject"] = headers_found.get("subject", "")
    result["sent_at"] = headers_found.get("date", "")

    return result


def _parse_from_field(from_str: str) -> tuple:
    """
    Parse a From field like 'John Smith <john@acme.com>' into (name, email).
    """
    # Pattern: Name <email>
    match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>', from_str)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern: just an email
    email_match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', from_str)
    if email_match:
        email = email_match.group(0)
        name = from_str.replace(email, "").strip(" <>\"'")
        return name or email.split("@")[0], email

    # Fallback: treat whole string as name
    return from_str.strip(), ""


def extract_emails_from_text(text_val: str) -> list:
    """Extract all email addresses from a text string."""
    if not text_val:
        return []
    return list(set(re.findall(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', text_val)))
