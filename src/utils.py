#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions for the Kratos charm."""

from typing import Dict
from urllib.parse import urlparse


def dict_to_action_output(d: Dict) -> Dict:
    """Convert all keys in a dict to the format of a juju action output.

    All `_` in the keys are replaced with `-`. This is applied recursively
    to any nested dicts.

    For example:
        {"a_b_c": 123} -> {"a-b-c": 123}
        {"a_b": {"c_d": "aba"}} -> {"a-b": {"c-d": "aba"}}

    """
    ret = {}
    for k, v in d.items():
        k = k.replace("_", "-")
        if isinstance(v, dict):
            v = dict_to_action_output(v)
        ret[k] = v
    return ret


def normalise_url(url: str) -> str:
    """Convert a URL to a more user-friendly HTTPS URL.

    The user will be redirected to this URL, we need to use the https prefix
    in order to be able to set cookies (secure attribute is set). Also we remove
    the port from the URL to make it more user-friendly.

    For example:
        http://ingress:80 -> https://ingress
        http://ingress:80/ -> https://ingress/
        http://ingress:80/path/subpath -> https://ingress/path/subpath

    This conversion works under the following assumptions:
    1) The ingress will serve https under the 443 port, the user-agent will
       implicitly make the request on that port
    2) The provided URL is not a relative path
    3) No user/password is provided in the netloc

    This is a hack and should be removed once traefik provides a way for us to
    request the https URL.
    """
    parsed_url = urlparse(url)

    parsed_url = parsed_url._replace(scheme="https")
    parsed_url = parsed_url._replace(netloc=parsed_url.netloc.rsplit(":", 1)[0])

    return parsed_url.geturl()
