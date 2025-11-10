/**
 * # Terraform Module for Kratos Operator
 *
 * This is a Terraform module facilitating the deployment of the kratos charm
 * using the Juju Terraform provider.
 */

resource "juju_application" "application" {
  name        = var.app_name
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = "kratos"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
  model_uuid = var.model
}
