# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


class CharmError(Exception):
    """Base class for custom charm errors."""


class MigrationError(CharmError):
    """Error for database migration."""


class PebbleServiceError(CharmError):
    """Error for pebble related operations."""


class ConfigMapError(CharmError):
    """Error for failed ConfigMap operations."""


class ActionError(CharmError):
    """Base class for charm action errors."""


class TooManyIdentitiesError(ActionError):
    """Error for when an email maps to more than one identity."""


class IdentityNotExistsError(ActionError):
    """Error for when an identity does not exist."""


class IdentityCredentialsNotExistError(ActionError):
    """Error for when the credentials of an identity do not exist."""


class IdentitySessionsNotExistError(ActionError):
    """Error for when the sessions of an identity do not exist."""


class ClientRequestError(ActionError):
    """Error when requesting Kratos fails."""
