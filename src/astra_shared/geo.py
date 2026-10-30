def city_display_name(name: str, region: str | None, country: str | None) -> str:
    """«Город, регион, страна» для показа; регион, совпадающий с городом («Москва»), не повторяется."""
    region = region if region != name else None
    return ", ".join(part for part in (name, region, country) if part)
