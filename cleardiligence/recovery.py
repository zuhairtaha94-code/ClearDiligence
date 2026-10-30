"""Bounded Gemini route recovery. Credentials never appear in persisted attempts."""
import time
import os
import re
import httpx
from .models import ModelAttempt
from .research import ProviderError, safe_diagnostic

DEFAULT_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.7-flash")
TRANSIENT = {429, 500, 502, 503, 504}


def configured_fallbacks(primary):
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    legacy = os.getenv("GEMINI_FALLBACK_MODEL", "").strip().removeprefix("models/")
    values = raw.split(",") if raw is not None else [legacy] if legacy and legacy != primary else DEFAULT_FALLBACK_MODELS
    models = list(dict.fromkeys(value.strip().removeprefix("models/") for value in values if value.strip()))
    if len(models) > 3 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value) for value in models):
        raise ValueError("GEMINI_FALLBACK_MODELS must contain up to three model IDs")
    return models


class GeminiUnavailable(ProviderError):
    def __init__(self, reason):
        super().__init__("Gemini", "recovery", reason)


def recover(extractor, company, sources, task, on_attempt=None, on_recovery=None):
    started = time.monotonic()
    deadline = started + 90
    models = list(dict.fromkeys([extractor.active_model, extractor.model, *extractor.fallback_models]))
    key_label = extractor.active_credential
    attempts = 0
    last_reason = "No healthy configured route is available yet; wait for cooldown or update provider settings."
    auth_recovered = False
    for index, model in enumerate(models):
        if model in extractor.disabled_models:
            continue
        if extractor.cooldowns.get((key_label, model), 0) > time.monotonic():
            continue
        # Reserve one request per remaining model, then spend spare budget on a retry.
        remaining = sum(candidate not in extractor.disabled_models and extractor.cooldowns.get((key_label, candidate), 0) <= time.monotonic() for candidate in models[index+1:])
        repeats = 2 if attempts + remaining + 1 < 5 else 1
        for retry in range(repeats):
            if attempts >= 5 or time.monotonic() >= deadline - 1:
                raise GeminiUnavailable("Recovery budget reached. Retrieved sources are saved; model interpretation remains incomplete.")
            if key_label in extractor.disabled_credentials:
                raise GeminiUnavailable("Configured credentials were rejected. Save an authorized credential and retry; sources are retained.")
            extractor.active_model = model
            extractor.active_credential = key_label
            extractor.request_timeout = min(45, max(1, deadline - time.monotonic()))
            attempts += 1
            try:
                result = extractor.extract(company, sources, task)
            except Exception as error:
                code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                transient = code in TRANSIENT or isinstance(error, (httpx.TimeoutException, httpx.ConnectError))
                auth_failure = code in (401, 403) or getattr(error, "gemini_auth_failure", False)
                reason = "Gemini credential rejected" if auth_failure else safe_diagnostic(error)
                attempt = ModelAttempt(model=model, credential=key_label, status="Failed", http_status=code, message=reason)
                if on_attempt: on_attempt(attempt)
                # A backup credential is for rejected authentication, never quota rotation.
                if auth_failure:
                    extractor.disabled_credentials.add(key_label)
                    if key_label == "primary" and extractor.backup_api_key and not auth_recovered:
                        key_label = "backup"
                        auth_recovered = True
                        note = f"{reason}; switching to the configured backup credential for {model}."
                        if on_recovery: on_recovery(note)
                        # Retry same model with backup even if this was an alternate route.
                        return _backup(extractor, company, sources, task, deadline, attempts, on_attempt, on_recovery)
                    raise GeminiUnavailable("Gemini authentication failed and no usable backup credential is configured. Sources are retained; no conclusions were generated.") from None
                if code == 404:
                    extractor.disabled_models.add(model)
                elif transient:
                    extractor.cooldowns[(key_label, model)] = time.monotonic() + 120
                else:
                    # Safety blocks and malformed structured output are not routed around.
                    raise
                last_reason = reason
                retry_after = error.response.headers.get("Retry-After", "") if isinstance(error, httpx.HTTPStatusError) else ""
                try: delay = max(0, float(retry_after)) if retry_after else 1.0
                except ValueError: delay = 5.0  # HTTP-date or unrecognized hint: move to another route.
                if transient:
                    extractor.cooldowns[(key_label, model)] = time.monotonic() + max(120, delay)
                if transient and retry == 0 and repeats == 2 and delay <= 4:
                    note = f"{reason}; retrying {model} after {delay:g}s, then using the fallback model chain if needed."
                    if on_recovery: on_recovery(note)
                    time.sleep(delay)
                    continue
                note = f"{reason}; moving to the next configured fallback model."
                if on_recovery: on_recovery(note)
                break
            else:
                extractor.cooldowns.pop((key_label, model), None)
                if on_attempt: on_attempt(ModelAttempt(model=model, credential=key_label, status="Succeeded", message="Structured response received; evidence validation still applies."))
                return result
    raise GeminiUnavailable("All available model routes failed or are cooling down. " + last_reason + " Retrieved evidence is retained; assessment coverage remains incomplete.")


def _backup(extractor, company, sources, task, deadline, attempts, on_attempt, on_recovery):
    """One bounded backup-auth attempt; no fresh retry budget or recursion."""
    if attempts >= 5 or time.monotonic() >= deadline - 1:
        raise GeminiUnavailable("Recovery budget reached before backup authentication. Sources are retained.")
    extractor.active_credential = "backup"
    extractor.request_timeout = min(45, max(1, deadline - time.monotonic()))
    try:
        result = extractor.extract(company, sources, task)
    except Exception as error:
        code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        if on_attempt: on_attempt(ModelAttempt(model=extractor.active_model, credential="backup", status="Failed", http_status=code, message=safe_diagnostic(error)))
        if code in (401, 403) or getattr(error, "gemini_auth_failure", False): extractor.disabled_credentials.add("backup")
        elif code in TRANSIENT or isinstance(error, (httpx.TimeoutException, httpx.ConnectError)):
            extractor.cooldowns[("backup", extractor.active_model)] = time.monotonic() + 120
        raise GeminiUnavailable("Backup credential attempt failed. Sources are retained; update authorized provider access or retry later.") from None
    if on_attempt: on_attempt(ModelAttempt(model=extractor.active_model, credential="backup", status="Succeeded", message="Structured response received; evidence validation still applies."))
    return result
