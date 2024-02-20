# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.sdcore-webui-k8s.name
}

# Required integration endpoints

output "common_database_endpoint" {
  description = "Name of the endpoint to integrate with MongoDB for common database using mongodb_client interface."
  value       = "common_database"
}

output "auth_database_endpoint" {
  description = "Name of the endpoint to integrate with MongoDB for authentication database using mongodb_client interface."
  value       = "auth_database"
}

# Provided integration endpoints

output "sdcore_management_endpoint" {
  description = "Name of the endpoint to provide `sdcore_management` interface."
  value       = "sdcore-management"
}
