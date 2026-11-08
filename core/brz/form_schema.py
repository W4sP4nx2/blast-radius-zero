"""Shared trusted form semantics; change the revision when disclosures/fields change."""
import hashlib
import json

DISCLOSURE = "This creates a demo receipt only. It sends no email and makes no purchase."
SCHEMA = {"title": "Demo Request", "fields": {"title": 120, "message": 2000},
          "method": "POST", "path": "/submit", "disclosure": DISCLOSURE}
FORM_REVISION = hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()


def payload_hash(title: str, message: str, revision: str) -> str:
    return hashlib.sha256(json.dumps({"title": title, "message": message, "revision": revision},
                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest()
