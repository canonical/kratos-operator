# Charmed Ory Kratos

## Description

This repository hosts the Kubernetes Python Operator for Ory Kratos -  an API-first identity and user management system.
For more details, visit https://www.ory.sh/docs/kratos/ory-kratos-intro

## Usage

The Kratos Operator may be deployed using the Juju command line as follows:

```bash
juju deploy postgresql-k8s --channel edge --trust
juju deploy kratos
juju relate kratos postgresql-k8s
```

### Ingress

The Kratos Operator offers integration with the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator) for ingress. Kratos has two APIs which can be exposed through ingress, the public API and the admin API.

If you have a traefik deployed and configured in your kratos model, to provide ingress to the admin API run:
```console
juju relate traefik-admin kratos:admin-ingress
```

To provide ingress to the public API run:
```console
juju relate traefik-public kratos:public-ingress
```

### Interacting with Kratos API

Below are two examples of the API. Visit [Ory](https://www.ory.sh/docs/kratos/reference/api) to see full API specification.

#### Create Identity
```bash
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
```bash
curl <kratos-service-ip>:4434/admin/identities
```
You should be able to see the identity created earlier.

## Relations

This charm requires a relation with [postgresql-k8s-operator](https://github.com/canonical/postgresql-k8s-operator).

## OCI Images

The image used by this charm is hosted on [Docker Hub](https://hub.docker.com/r/oryd/kratos) and maintained by Ory.

### Security
Security issues in IAM stack can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/kratos-operator/blob/main/CONTRIBUTING.md) for developer guidance.


## License

The Charmed Kratos Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/kratos-operator/blob/main/LICENSE) for more information.
