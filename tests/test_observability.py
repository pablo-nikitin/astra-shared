from astra_shared.observability import sentry_log_extra


def test_fields_stringified_and_none_dropped():
    result = sentry_log_extra(user_uuid="abc", count=5, missing=None)
    assert result == {"sentry_identifier_fields": {"user_uuid": "abc", "count": "5"}}


def test_no_fields():
    assert sentry_log_extra() == {"sentry_identifier_fields": {}}
