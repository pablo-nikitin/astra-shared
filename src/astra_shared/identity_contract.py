from dataclasses import dataclass


@dataclass(frozen=True)
class AccessTokenPayload:
    user_uuid: str
    provider: str
    external_id: str
