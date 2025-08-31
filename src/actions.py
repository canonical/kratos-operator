# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from exceptions import IdentityNotExistsError, TooManyIdentitiesError


class IdentityParams(BaseModel):
    identity_id: Optional[str] = Field(default=None, alias="identity-id")
    email: Optional[EmailStr] = Field(default=None)

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        extra="ignore",
    )

    @field_validator("identity_id", mode="before")
    @classmethod
    def validate_identity_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        try:
            UUID(v)
        except Exception:
            raise ValueError("The identity-id must be a valid UUID")

        return v

    @model_validator(mode="after")
    def populate_identity_id(self, info: ValidationInfo) -> Self:
        http_client = info.context.get("http_client")
        identity_id, email = self.identity_id, self.email

        if identity_id and email:
            raise ValueError("Provide only one of 'identity-id' or 'email', not both")

        if not identity_id and not email:
            raise ValueError("You must provide either 'identity-id' or 'email'")

        if not identity_id and email:
            try:
                identity = http_client.get_identity_by_email(email)
            except IdentityNotExistsError:
                raise ValueError(f"Identity not found for email '{email}'")
            except TooManyIdentitiesError:
                raise ValueError(
                    f"Multiple identities found for email '{email}'. Please provide an identity-id "
                    f"instead"
                )
            except Exception:
                raise ValueError("Couldn't retrieve the identity id from email")

            self.identity_id = identity["id"]

        return self
