# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

variable "model_name" {
  description = "Name of Juju model to deploy application to."
  type        = string
  default     = ""
}

variable "channel" {
  description = "The channel to use when deploying a charm."
  type        = string
  default     = "1.5/edge"
}

variable "app_name" {
  description = "The name of the application providing the `database` endpoint."
  type        = string
  default     = "webui"
}
