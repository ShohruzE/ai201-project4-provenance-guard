_submissions: dict[str, dict] = {}


def save_submission(content_id: str, record: dict) -> dict:
    _submissions[content_id] = record
    return record


def get_submission(content_id: str) -> dict | None:
    return _submissions.get(content_id)


def update_submission(content_id: str, updates: dict) -> dict | None:
    record = _submissions.get(content_id)
    if record is None:
        return None
    record.update(updates)
    _submissions[content_id] = record
    return record
