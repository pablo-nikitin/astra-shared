def sentry_log_extra(**fields: object) -> dict[str, dict[str, str]]:
    return {
        "sentry_identifier_fields": {
            name: str(value) for name, value in fields.items() if value is not None
        }
    }
