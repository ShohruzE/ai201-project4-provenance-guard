from datetime import datetime, timezone

_audit_log: list[dict] = []


def append_entry(entry: dict) -> dict:
    _audit_log.append(entry)
    return entry


def get_log(limit: int | None = None) -> list[dict]:
    if limit is None:
        return list(_audit_log)
    return list(_audit_log[-limit:])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
