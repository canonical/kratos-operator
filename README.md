# Charmed Ory Kratos

[![CharmHub Badge](https://charmhub.io/kratos/badge.svg)](https://charmhub.io/kratos)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/kratos-operator?label=License)](https://github.com/canonical/kratos-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/kratos-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/kratos-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

This repository hosts the Kubernetes Python Operator for Ory Kratos - an
API-first identity and user management system. For more details,
visit <https://www.ory.sh/docs/kratos/ory-kratos-intro>.

## Usage

The Kratos Operator may be deployed using the Juju command line as follows:

```shell
juju deploy postgresql-k8s --channel 14/stable --trust --config 'plugin_pg_trgm_enable=True' --config 'plugin_btree_gin_enable=True'
juju deploy kratos
juju integrate kratos postgresql-k8s
```

### Interacting with Kratos API

Below are two examples of the API.
Visit [Ory](https://www.ory.sh/docs/kratos/reference/api) to see full API
specification.

#### Create Identity

```shell
curl <kratos-service-ip>:4434/identities \
--request POST -sL \
--header "Content-Type: application/json" \
--data '{
  "schema_id": "default",
  "traits": {
    "email": "test@example.org"
  }
}'
```

#### Get Identities

```shell
curl <kratos-service-ip>:4434/admin/identities
```

You should be able to see the identity created earlier.

## Integrations

### PostgreSQL

This charm requires an integration
with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

### Ingress (via traefik-route)

The Kratos Operator offers integration with
the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator)
for ingress. Kratos has two APIs which can be exposed through ingress, the
public API and the admin API.

If you have a traefik deployed and configured in your kratos model, to provide
ingress to the admin API run:

```shell
juju integrate traefik-admin kratos:internal-route
```

To provide ingress to the public API run:

```shell
juju integrate traefik-public kratos:public-route
```

### SMTP Server Integration

In order to turn Kratos into a functional identity provider, an outgoing mail server must be integrated.
It can be done using the [`smtp`](https://github.com/canonical/charm-relation-interfaces/tree/main/interfaces/smtp/v0) interface.

If you have a self-hosted SMTP server independent of the juju ecosystem, deploy the [`smtp-integrator`](https://github.com/canonical/smtp-integrator-operator.git) charm, configure it with the required server details
and integrate with Kratos:

```shell
juju deploy smtp-integrator --channel latest/edge
juju config smtp-integrator user=<username> password=<pwd> host=<hostname> port=<port> transport_security=<none|tls|starttls> skip_ssl_verify=<True|False>
juju integrate smtp-integrator:smtp kratos
```

[Mailslurper](https://github.com/mailslurper/mailslurper) is recommended for local development.

### External Provider Integration

Kratos can be used as an identity broker. To connect Kratos with an external
identity provider you can use the external provider integration. All you need
to do is deploy
the [kratos-external-idp-integrator](https://charmhub.io/kratos-external-idp-integrator),
configure it and integrate it with Kratos:

```shell
juju deploy kratos-external-provider-integrator
juju config kratos-external-provider-integrator \
    client_id={client_id} \
    client_secret={client_secret} \
    provider={provider}
juju integrate kratos-external-provider-integrator kratos
```

Once kratos has registered the provider, you will be able to retrieve the
redirect_uri from the integrator by running:

```shell
juju run {external_provider_integrator_unit_name} get-redirect-uri --wait
```

### Hydra

This charm offers integration
with [hydra-operator](https://github.com/canonical/hydra-operator).

In order to integrate kratos with hydra, it needs to be able to access hydra's
admin API endpoint. To enable that, integrate the two charms:

```shell
juju integrate kratos hydra
```

For further guidance on integration on hydra side, visit
the [hydra-operator](https://github.com/canonical/hydra-operator#readme)
repository.

### Identity Platform Login UI

The following instructions assume that you have deployed `traefik-admin`
and `traefik-public` charms and integrated them with Kratos. Note that the UI
charm should run behind a proxy.

This charm offers integration
with [identity-platform-login-ui-operator](https://github.com/canonical/identity-platform-login-ui-operator).
In order to integrate them, run:

```shell
juju integrate kratos:ui-endpoint-info identity-platform-login-ui-operator:ui-endpoint-info
juju integrate identity-platform-login-ui-operator:kratos-info kratos:kratos-info
```

## Actions

The kratos charm offers the following actions:

### create-admin-account

This action can be used to create an admin account.
The password can be set to a specified value by passing `password-secret-id` as an action parameter.

To create a juju secret holding the password and grant it to kratos, run:

```shell
juju add-secret <secret-name> password=<new-password>
secret:cql684nmp25c75sflot0
juju grant-secret <secret-name> kratos
```

To create the admin account:

```shell
juju run kratos/0 create-admin-account username=admin123 password-secret-id=secret:12345678 email=admin@example.com
```

NOTE: The email registered for an admin account must not be used for any other
user (admin or not).

### get-identity

This action can be used to get information about an existing identity by email
or id:

By id:

```shell
juju run kratos/0 get-identity identity-id={identity_id}
```

By email:

```shell
juju run kratos/0 get-identity email={email}
```

### delete-identity

This action can be used to delete an existing identity. An identity_id can be
used to specify the identity:

```shell
juju run kratos/0 delete-identity identity-id={identity_id}
```

An email can be used to specify the identity as well:

```shell
juju run kratos/0 delete-identity email={email}
```

### reset-password

This action can be used to reset password of an identity by its email or id.
The password can be set to a specified value by passing `password-secret-id` as an action parameter.

To create a juju secret holding the password and grant it to kratos, run:

```shell
juju add-secret <secret-name> password=<new-password>
secret:cql684nmp25c75sflot0
juju grant-secret <secret-name> kratos
```

Then, run the action using identity id:

```shell
juju run kratos/0 reset-password identity-id={identity_id} password-secret-id=secret:cql684nmp25c75sflot0
```

Or email:

```shell
juju run kratos/0 reset-password email={email} password-secret-id=secret:cql684nmp25c75sflot0
```

If `password-secret-id` parameter is not provided, the action will return a self-service recovery code and link
to reset the password.

### invalidate-identity-sessions

This action can be used to invalidate all user sessions using either the identity id or email.

By id:

```shell
juju run kratos/0 invalidate-identity-sessions identity-id={identity_id}
```

By email:

```shell
juju run kratos/0 invalidate-identity-sessions email={email}
```

### reset-identity-mfa

This action can be used to reset identity's second authentication factor using either the identity id or email.
The type of credentials to be removed must be specified, supported values are `totp` and `lookup_secret`.

By id:

```shell
juju run kratos/0 reset-identity-mfa identity-id={identity_id} mfa-type={totp|lookup_secret}
```

By email:

```shell
juju run kratos/0 reset-identity-mfa email={email} mfa-type={totp|lookup_secret}
```

### list-oidc-accounts

This action can be used to list the OIDC accounts identifiers linked to an identity using either the identity id or email.

By id:

```shell
juju run kratos/0 list-oidc-accounts identity-id={identity_id}
```

By email:

```shell
juju run kratos/0 list-oidc-accounts email={email}
```

### unlink-oidc-account

This action can be used to unlink a user's external identity provider account from their identity
using either the identity id or email.
The credential id to be removed must be specified, you can find it with `list-oidc-accounts` action.

By id:

```shell
juju run kratos/0 unlink-oidc-account identity-id={identity_id} credential-id={oidc-identifier}
```

By email:

```shell
juju run kratos/0 unlink-oidc-account email={email} credential-id={oidc-identifier}
```

### run-migration

This action can be used to trigger a database migration:

```shell
juju run kratos/0 run-migration
```

## OCI Images

The image used by this charm is hosted
on [Docker Hub](https://hub.docker.com/r/oryd/kratos) and maintained by Ory.

## Security

Please see [SECURITY.md](https://github.com/canonical/kratos-operator/blob/main/SECURITY.md)
for guidelines on reporting security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/kratos-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The Charmed Kratos Operator is free software, distributed under the Apache
Software License, version 2.0.
See [LICENSE](https://github.com/canonical/kratos-operator/blob/main/LICENSE)
for more information.
