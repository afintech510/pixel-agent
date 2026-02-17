"""
PST Parser - Ported from Future_Agent_1
Reads Outlook PST files using pypff and stores emails in PostgreSQL.
"""

try:
    import pypff
    PYPFF_AVAILABLE = True
except ImportError:
    PYPFF_AVAILABLE = False

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session


def clean_text(text_val: str) -> str:
    if not text_val:
        return ""
    return text_val.replace("\x00", "").strip()


def extract_header_field(headers: str, key: str) -> Optional[str]:
    if not headers:
        return None
    pattern = rf"^{key}:\s*(.+)$"
    match = re.search(pattern, headers, re.MULTILINE | re.IGNORECASE)
    if match:
        return clean_text(match.group(1))
    return None


def extract_emails(text_val: str) -> List[str]:
    if not text_val:
        return []
    raw_emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", text_val)
    return list(set(e.lower() for e in raw_emails))


def generate_dedupe_hash(sender, recipients_str, subject, sent_time_iso, body_text):
    body_snippet = body_text[:200] if body_text else ""
    raw = f"{sender}|{recipients_str}|{subject}|{sent_time_iso}|{body_snippet}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_domain(email: str) -> Optional[str]:
    if not email or "@" not in email:
        return None
    return email.split("@")[-1].lower()


def html_to_text(html: str) -> str:
    """Convert HTML to readable plain text using regex (no external deps)."""
    if not html:
        return ""

    text = html

    # Remove script and style blocks entirely
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert block-level elements to newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:p|div|li|tr|h[1-6])\b[^>]*>', '\n', text, flags=re.IGNORECASE)

    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode common HTML entities
    entity_map = {
        '&nbsp;': ' ', '&lt;': '<', '&gt;': '>', '&amp;': '&',
        '&quot;': '"', '&#39;': "'", '&apos;': "'",
    }
    for entity, char in entity_map.items():
        text = text.replace(entity, char)

    # Handle numeric entities (e.g. &#160;)
    text = re.sub(
        r'&#(\d+);',
        lambda m: chr(int(m.group(1))) if int(m.group(1)) < 65536 else '',
        text,
    )

    # Collapse whitespace: multiple spaces -> single, 3+ newlines -> 2
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(line.strip() for line in text.split('\n'))

    return text.strip()


def generate_thread_id(subject: str) -> str:
    if not subject:
        return "unknown"
    clean = re.sub(
        r"^(re|fwd|fw|\[.*?\]):\s*", "", subject, flags=re.IGNORECASE
    ).strip().lower()
    return hashlib.sha1(clean.encode("utf-8")).hexdigest()


class PSTParser:
    """
    Parse Outlook PST files and store emails in PostgreSQL.

    Usage:
        parser = PSTParser(file_path, db_session, import_id)
        parser.open()
        stats = parser.parse()
        parser.close()
    """

    def __init__(
        self,
        file_path: str,
        db: Session,
        import_id: Optional[str] = None,
        batch_size: int = 50,
        internal_domain: str = "futureelectronics.com",
    ):
        if not PYPFF_AVAILABLE:
            raise ImportError(
                "pypff is not installed. PST import requires the pypff library. "
                "Install it from source: https://github.com/libyal/libpff"
            )
        self.file_path = file_path
        self.db = db
        self.import_id = import_id
        self.batch_size = batch_size
        self.internal_domain = internal_domain
        self.pst = pypff.file()
        self.stats = {"processed": 0, "errors": 0, "skipped": 0}
        self.batch: List[Dict] = []
        self.emails_for_return: List[Dict] = []  # For training mode

    def open(self):
        self.pst.open(self.file_path)

    def close(self):
        self.pst.close()

    def parse(self, return_emails: bool = False) -> Dict:
        """
        Parse all emails from the PST file.

        Args:
            return_emails: If True, collect and return parsed emails
                          (for training mode labeling). If False, insert
                          directly into database.
        """
        self.emails_for_return = []
        root = self.pst.get_root_folder()
        if root:
            self._parse_folder(root, "Root", return_emails)
        if not return_emails:
            self._flush_batch()
        return self.stats

    def get_parsed_emails(self) -> List[Dict]:
        """Return emails collected during parse(return_emails=True)."""
        return self.emails_for_return

    def _parse_folder(self, folder, path_str: str, return_emails: bool):
        for message in folder.sub_messages:
            try:
                self._process_message(message, path_str, return_emails)
            except Exception as e:
                print(f"Error in {path_str}: {e}")
                self.stats["errors"] += 1

        for sub_folder in folder.sub_folders:
            new_path = f"{path_str}/{sub_folder.name}"
            self._parse_folder(sub_folder, new_path, return_emails)

    def _process_message(self, message, folder_path: str, return_emails: bool):
        # 1. Basic extraction
        subject = clean_text(message.subject)
        headers = clean_text(message.transport_headers)
        body_text = clean_text(message.plain_text_body)
        if not body_text:
            try:
                raw_html = message.html_body.decode("utf-8", errors="ignore")
                body_text = html_to_text(raw_html)
            except Exception:
                body_text = ""

        # 2. Identity & headers
        msg_id = extract_header_field(headers, "Message-ID")
        references = extract_header_field(headers, "References")

        header_from = extract_header_field(headers, "From")
        sender_emails = extract_emails(header_from)
        sender_email = sender_emails[0] if sender_emails else None
        sender_name = clean_text(message.sender_name)

        header_to = extract_header_field(headers, "To")
        header_cc = extract_header_field(headers, "Cc")
        to_emails = extract_emails(header_to)
        cc_emails = extract_emails(header_cc)

        # 3. Timestamps
        delivery_time = message.get_delivery_time()
        timestamp_missing = False
        if delivery_time:
            try:
                sent_at = delivery_time.astimezone(timezone.utc).isoformat()
            except Exception:
                sent_at = delivery_time.isoformat()
        else:
            sent_at = None
            timestamp_missing = True

        # 4. Dedupe & threading
        content_hash = generate_dedupe_hash(
            sender_email or "unknown",
            ",".join(sorted(to_emails)),
            subject,
            sent_at or "missing",
            body_text,
        )
        thread_id = generate_thread_id(subject)

        # 5. Entity linking (company + contact + thread)
        related_company_id = None
        all_participants = list(set(
            ([sender_email] if sender_email else []) + to_emails + cc_emails
        ))
        external_emails = [
            e for e in all_participants
            if e and not e.endswith(f"@{self.internal_domain}")
        ]

        if external_emails:
            primary_external = external_emails[0]
            domain = extract_domain(primary_external)

            if domain:
                try:
                    # Ensure company exists
                    result = self.db.execute(
                        text("SELECT id FROM companies WHERE domain = :domain"),
                        {"domain": domain},
                    ).fetchone()

                    if result:
                        related_company_id = str(result[0])
                    else:
                        comp_name = domain.split(".")[0].capitalize()
                        new_id = str(uuid.uuid4())
                        self.db.execute(
                            text("""
                                INSERT INTO companies (id, name, domain, type)
                                VALUES (:id, :name, :domain, 'Unclassified')
                                ON CONFLICT (domain) DO NOTHING
                            """),
                            {"id": new_id, "name": comp_name, "domain": domain},
                        )
                        self.db.commit()
                        # Re-fetch in case of conflict
                        result = self.db.execute(
                            text("SELECT id FROM companies WHERE domain = :domain"),
                            {"domain": domain},
                        ).fetchone()
                        related_company_id = str(result[0]) if result else None

                    # Ensure contact exists
                    if related_company_id and sender_email and sender_email in external_emails:
                        self.db.execute(
                            text("""
                                INSERT INTO contacts (email, company_id, full_name)
                                VALUES (:email, :company_id, :full_name)
                                ON CONFLICT (email) DO NOTHING
                            """),
                            {
                                "email": sender_email,
                                "company_id": related_company_id,
                                "full_name": sender_name,
                            },
                        )

                    # Ensure thread exists
                    self.db.execute(
                        text("""
                            INSERT INTO email_threads (id, subject, related_company_id, last_message_at)
                            VALUES (:id, :subject, :company_id, :last_msg)
                            ON CONFLICT (id) DO UPDATE SET
                                last_message_at = GREATEST(email_threads.last_message_at, EXCLUDED.last_message_at)
                        """),
                        {
                            "id": thread_id,
                            "subject": subject,
                            "company_id": related_company_id,
                            "last_msg": sent_at,
                        },
                    )
                    self.db.commit()
                except Exception as e:
                    self.db.rollback()
                    print(f"Entity linking error: {e}")

        # 6. Attachments
        attachments_meta = []
        for i in range(message.number_of_attachments):
            try:
                att = message.get_attachment(i)
                name = ""
                if hasattr(att, "get_name"):
                    name = att.get_name()
                elif hasattr(att, "name"):
                    name = att.name

                attachments_meta.append({
                    "filename": clean_text(name) or f"attachment_{i}",
                    "size": att.get_size() if hasattr(att, "get_size") else 0,
                    "index": i,
                })
            except Exception as att_e:
                print(f"Error extracting attachment {i}: {att_e}")

        # 7. Record construction
        email_record = {
            "import_id": self.import_id,
            "message_id": msg_id,
            "dedupe_hash": content_hash,
            "thread_id": thread_id,
            "references_header": references,
            "subject": subject,
            "body": body_text[:50000],
            "from_name": sender_name,
            "sender_email": sender_email,
            "recipient_emails": to_emails,
            "cc_emails": cc_emails,
            "sent_at": sent_at,
            "timestamp_missing": timestamp_missing,
            "folder_path": folder_path,
            "attachments": attachments_meta,
            "transport_headers": headers,
            "processed_by_ai": False,
            "related_company_id": related_company_id,
        }

        if return_emails:
            self.emails_for_return.append(email_record)
        else:
            self.batch.append(email_record)

        self.stats["processed"] += 1

        if not return_emails and len(self.batch) >= self.batch_size:
            self._flush_batch()

    def _flush_batch(self):
        if not self.batch:
            return
        try:
            for record in self.batch:
                email_id = str(uuid.uuid4())
                self.db.execute(
                    text("""
                        INSERT INTO emails (
                            id, import_id, message_id, dedupe_hash, thread_id,
                            references_header, subject, body, from_name,
                            sender_email, recipient_emails, cc_emails, sent_at,
                            timestamp_missing, folder_path, attachments,
                            transport_headers, processed_by_ai, related_company_id
                        ) VALUES (
                            :id, :import_id, :message_id, :dedupe_hash, :thread_id,
                            :references_header, :subject, :body, :from_name,
                            :sender_email, :recipient_emails, :cc_emails, :sent_at,
                            :timestamp_missing, :folder_path, :attachments::jsonb,
                            :transport_headers::jsonb, :processed_by_ai, :related_company_id
                        ) ON CONFLICT (dedupe_hash) DO NOTHING
                    """),
                    {
                        "id": email_id,
                        "import_id": record["import_id"],
                        "message_id": record["message_id"],
                        "dedupe_hash": record["dedupe_hash"],
                        "thread_id": record["thread_id"],
                        "references_header": record["references_header"],
                        "subject": record["subject"],
                        "body": record["body"],
                        "from_name": record["from_name"],
                        "sender_email": record["sender_email"],
                        "recipient_emails": record["recipient_emails"],
                        "cc_emails": record["cc_emails"],
                        "sent_at": record["sent_at"],
                        "timestamp_missing": record["timestamp_missing"],
                        "folder_path": record["folder_path"],
                        "attachments": str(record["attachments"]).replace("'", '"') if record["attachments"] else "[]",
                        "transport_headers": f'"{record["transport_headers"]}"' if record["transport_headers"] else "null",
                        "processed_by_ai": record["processed_by_ai"],
                        "related_company_id": record["related_company_id"],
                    },
                )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            print(f"Batch insert error: {e}")

        self.batch.clear()
