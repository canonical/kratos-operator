# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.


class CharmError(Exception):
    """Base class for custom charm errors."""


class TooManyIdentitiesError(Exception):
    """Error for when an email maps to more than one identity."""
