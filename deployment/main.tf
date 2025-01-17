terraform {
  required_providers {
    juju = {
      version = ">= 0.15.0"
      source  = "juju/juju"
    }
  }
}

variable "client_id" {
  type      = string
  sensitive = true
}

variable "client_secret" {
  type      = string
  sensitive = true
}

variable "jimm_url" {
  type = string
}

variable "model" {
  type = string
}

variable "charm" {
  description = "The configurations of the application."
  type = object({
    name   = optional(string, "kratos")
    units  = optional(number, 1)
    base   = optional(string, "ubuntu@22.04")
    trust  = optional(string, true)
    config = optional(map(string), {})
  })
  default = {}
}

variable "application_name" {
  type = string
}

variable "revision" {
  type = number
}

variable "channel" {
  type = string
}

provider "juju" {
  controller_addresses = var.jimm_url

  client_id     = var.client_id
  client_secret = var.client_secret

}

data "juju_model" "model" {
  name = var.model
}


resource "juju_application" "application" {
  model = data.juju_model.model.name
  name  = var.application_name
  trust = var.charm.trust
  units = var.charm.units

  charm {
    name     = var.charm.name
    base     = var.charm.base
    revision = var.revision
    channel  = var.channel
  }

  config = var.charm.config

}
