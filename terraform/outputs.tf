# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.kratos.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    pg-database         = "pg-database"
    public-ingress      = "public-ingress"
    admin-ingress       = "admin-ingress"
    internal-ingress    = "internal-ingress"
    kratos-external-idp = "kratos-external-idp"
    hydra-endpoint-info = "hydra-endpoint-info"
    ui-endpoint-info    = "ui-endpoint-info"
    receive-ca-cert     = "receive-ca-cert"
    smtp                = "smtp"
    logging             = "logging"
    tracing             = "tracing"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    kratos-info       = "kratos-info"
    metrics-endpoint  = "metrics-endpoint"
    grafana-dashboard = "grafana-dashboard"
  }
}
