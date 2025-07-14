<!-- BEGIN_TF_DOCS -->
# Terraform Module for Kratos Operator

This is a Terraform module facilitating the deployment of the kratos charm
using the Juju Terraform provider.
---
## Providers

| Name | Version |
|------|---------|
| <a name="provider_juju"></a> [juju](#provider\_juju) | >= 0.20.0 |
---
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.5.0 |
| <a name="requirement_juju"></a> [juju](#requirement\_juju) | >= 0.20.0 |
---
## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_model_name"></a> [model\_name](#input\_model\_name) | The Juju model name | `string` | n/a | yes |
| <a name="input_app_name"></a> [app\_name](#input\_app\_name) | The Juju application name | `string` | n/a | yes |
| <a name="input_config"></a> [config](#input\_config) | The charm config | `map(string)` | <pre>{<br/>  "enable_local_idp": "false",<br/>  "enable_oidc_webauthn_sequencing": "false"<br/>}</pre> | no |
| <a name="input_constraints"></a> [constraints](#input\_constraints) | The constraints to be applied | `string` | `""` | no |
| <a name="input_units"></a> [units](#input\_units) | The number of units | `number` | `1` | no |
| <a name="input_base"></a> [base](#input\_base) | The charm base | `string` | `"ubuntu@22.04"` | no |
| <a name="input_channel"></a> [channel](#input\_channel) | The charm channel | `string` | `"latest/stable"` | no |
| <a name="input_revision"></a> [revision](#input\_revision) | The charm revision | `number` | `null` | no |
---
## Outputs

| Name | Description |
|------|-------------|
| <a name="output_app_name"></a> [app\_name](#output\_app\_name) | The Juju application name |
| <a name="output_requires"></a> [requires](#output\_requires) | The Juju integrations that the charm requires |
| <a name="output_provides"></a> [provides](#output\_provides) | The Juju integrations that the charm provides |
<!-- END_TF_DOCS -->