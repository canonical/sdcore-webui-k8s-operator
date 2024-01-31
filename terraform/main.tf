resource "juju_application" "webui" {
  name  = "webui"
  model = var.model_name

  charm {
    name    = "sdcore-webui-k8s"
    channel = var.channel
  }

  units = 1
  trust = true
}

resource "juju_integration" "webui-db" {
  model = var.model_name

  application {
    name     = juju_application.webui.name
    endpoint = "database"
  }

  application {
    name     = var.db_application_name
    endpoint = "database"
  }
}


