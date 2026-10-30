"""Evidence gate: mechanical provenance checks, never a truth oracle."""
import re
import html
import unicodedata
from urllib.parse import urlparse
from .models import Assessment, Verification


def normalize(text: str) -> str:
    text = html.unescape(unicodedata.normalize("NFKC", text))
    # Render formatting only. Words, negation, numbers and their order are retained.
    text = re.sub(r"!\[([^\]]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"</?(?:strong|b|em|i|span)(?:\s[^>]*)?>", "", text, flags=re.I)
    text = re.sub(r"(\*\*|__|`)([^\n]+?)\1", r"\2", text)
    text = text.translate(str.maketrans({"’":"'", "‘":"'", "“":'"', "”":'"', "–":"-", "—":"-"}))
    return " ".join(text.split()).casefold()


def validate_evidence(a: Assessment):
    sources = {s.id: s for s in a.sources}
    for f in a.findings:
        f.validation_notes = []
        f.evidence_valid = False
        linked = [sources[sid] for sid in f.source_ids if sid in sources]
        if not f.source_ids or len(linked) != len(f.source_ids):
            f.validation_notes.append("Missing or unknown retrieved source reference.")
        elif any(s.synthetic != (a.mode == "Demo") for s in linked):
            f.validation_notes.append("Source mode mismatch; synthetic and live evidence cannot mix.")
        elif any(urlparse(s.url).scheme not in (("demo",) if a.mode == "Demo" else ("http", "https")) for s in linked):
            f.validation_notes.append("Source URL is not valid for this mode.")
        elif not f.excerpt.strip() or not any(normalize(f.excerpt) in normalize(s.content) or (f.category == "profile" and f.field == "website" and f.excerpt == s.url) for s in linked):
            f.validation_notes.append("Evidence excerpt is absent from the retrieved source content.")
        elif f.extracted_value and normalize(f.extracted_value) not in normalize(f.excerpt):
            f.validation_notes.append("Extracted value is absent from the cited evidence excerpt.")
        elif normalize(f.claim) not in normalize(f.excerpt):
            f.validation_notes.append("Claim is not directly supported by the cited excerpt.")
        elif f.category == "profile" and f.field == "registration" and not re.search(r"\b(registration|incorporat\w*|registered\s+(?:in|as|with|under)|company\s+(?:number|no\.?|id)|entity\s+(?:number|no\.?|id)|CIK|ACN|ABN|CRN)\b", f.excerpt, re.I):
            f.validation_notes.append("The quote does not state registration information; a legal name or headquarters is not incorporation evidence.")
        elif f.category == "profile" and f.field == "ownership" and (not re.search(r"\b(own\w*|shareholder\w*|stockholder\w*|subsidiar\w*|parent company|equity|portfolio company|controlling interest)\b", f.excerpt, re.I) or (re.search(r"\b(merged?|merger|join(?:ed)? forces)\b", f.excerpt, re.I) and not re.search(r"\b(owned by|ownership of|shareholder\w*|stockholder\w*|subsidiary of|parent company|equity interest|controlling interest)\b", f.excerpt, re.I))):
            f.validation_notes.append("The quote does not establish ownership; a merger or partnership announcement alone is insufficient.")
        else:
            f.evidence_valid = True
        if not f.evidence_valid:
            f.verification = Verification.UNVERIFIED
            f.requires_review = True
            gap = f"Unsupported {f.category} finding quarantined: {f.id}."
            if gap not in a.gaps:
                a.gaps.append(gap)
        if f.relevance in ("Potential", "Unresolved"):
            f.requires_review = True
        if f.category == "sanctions" and f.match != "none":
            f.requires_review = True
            if f.match == "possible":
                f.verification = Verification.POTENTIAL
    # Multiple offices are normal. Only explicit registered-office records are comparable.
    # Website paths/WWW variants refer to the same domain, not separate entity identities.
    for field in ("registration", "location", "website"):
        facts = [f for f in a.findings if f.category == "profile" and f.field == field and f.evidence_valid and f.relevance != "Different entity"]
        if field == "location":
            facts = [f for f in facts if re.search(r"registered (?:office|address)", f.claim, re.I)]
        def value_key(f):
            value = f.extracted_value or f.claim
            if field == "website":
                return (urlparse(value).hostname or value).casefold().removeprefix("www.")
            return normalize(value).rstrip(".")
        values = {value_key(f) for f in facts}
        if len(values) > 1:
            gap = f"Potentially conflicting {field} evidence; compare sources before relying on it."
            if gap not in a.gaps:
                a.gaps.append(gap)
            for f in facts:
                f.requires_review = True
                f.verification = Verification.POTENTIAL
                f.validation_notes.append("Potential conflict across comparable retrieved values.")
