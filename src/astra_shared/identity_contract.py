import uuid as uuid_lib
from dataclasses import dataclass


@dataclass(frozen=True)
class AccessTokenPayload:
    user_uuid: str
    provider: str
    external_id: str


def generate_referral_code() -> str:
    return str(uuid_lib.uuid4())[:8]
