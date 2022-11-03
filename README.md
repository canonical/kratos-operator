# Charmed Ory Kratos

## Description

This repository hosts the Kubernetes Python Operator for Ory Kratos.
For more details, visit https://www.ory.sh/docs/kratos/ory-kratos-intro

## Usage

TODO: Provide high-level usage, such as required config or relations
```bash
juju deploy postgresql-k8s --channel edge --trust
juju deploy kratos --trust
juju relate kratos postgresql-k8s
```

## Relations

TODO: Provide any relations which are provided or required by your charm

## OCI Images

TODO: Include a link to the default image your charm uses

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/kratos-operator/blob/main/CONTRIBUTING.md) for developer guidance.
### Security
Security issues in IAM stack can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.
