# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_name" {
  description = "The Juju model name"
  type        = string
}

variable "app_name" {
  description = "The Juju application name"
  type        = string
}

variable "config" {
  description = "The charm config"
  type        = map(string)
  default = {
    enable_local_idp : "false",
    enable_oidc_webauthn_sequencing : "false",
  }
}

variable "constraints" {
  description = "The constraints to be applied"
  type        = string
  default     = ""
}

variable "units" {
  description = "The number of units"
  type        = number
  default     = 1
}

variable "base" {
  description = "The charm base"
  type        = string
  default     = "ubuntu@22.04"
}

variable "channel" {
  description = "The charm channel"
  type        = string
  default     = "latest/stable"
}

variable "revision" {
  description = "The charm revision"
  type        = number
  nullable    = true
  default     = null
}
