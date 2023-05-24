#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G Webui service."""

import logging

from charms.data_platform_libs.v0.data_interfaces import (  # type: ignore[import]
    DatabaseCreatedEvent,
    DatabaseRequires,
)
from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]
    KubernetesServicePatch,
)
from jinja2 import Environment, FileSystemLoader
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/webui"
CONFIG_FILE_NAME = "webuicfg.conf"
DATABASE_RELATION_NAME = "database"
DATABASE_NAME = "free5gc"


def render_config_file(database_name: str, database_url: str) -> str:
    """Renders webui configuration file based on Jinja template.

    Args:
        database_name: Database Name
        database_url: Database URL.

    Returns:
        str: Content of the configuration file.
    """
    jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
    template = jinja2_environment.get_template("webuicfg.conf.j2")
    return template.render(
        database_name=database_name,
        database_url=database_url,
    )


class WebuiOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "webui"
        self._container = self.unit.get_container(self._container_name)
        self._database = DatabaseRequires(
            self,
            relation_name=DATABASE_RELATION_NAME,
            database_name=DATABASE_NAME,
            extra_user_roles="admin",
        )
        self.framework.observe(self.on.webui_pebble_ready, self._on_webui_pebble_ready)
        self.framework.observe(self.on.database_relation_joined, self._on_webui_pebble_ready)
        self.framework.observe(self._database.on.database_created, self._on_database_created)
        self.framework.observe(self._database.on.endpoints_changed, self._on_database_created)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            service_name="webui",
            ports=[
                ServicePort(name="urlport-http", port=5000),
                ServicePort(name="grpc", port=9876),
            ],
        )

    def _on_webui_pebble_ready(self, event: EventBase) -> None:
        """Handles pebble ready event."""
        if not self._database_relation_is_created():
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._config_file_is_written():
            self.unit.status = WaitingStatus("Waiting for config file to be written")
            return
        self._container.add_layer("webui", self._pebble_layer, combine=True)
        self._container.replan()
        self._container.restart(self._service_name)
        self.unit.status = ActiveStatus()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Handle database created event."""
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._container.exists(path=BASE_CONFIG_PATH):
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            event.defer()
            return
        config_file_content = render_config_file(
            database_name=DATABASE_NAME, database_url=event.uris.split(",")[0]
        )
        self._write_config_file(content=config_file_content)
        self._on_webui_pebble_ready(event=event)

    def _write_config_file(self, content: str) -> None:
        """Writes configuration file based on provided content.

        Args:
            content: Configuration file content
        """
        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info("Pushed %s config file", CONFIG_FILE_NAME)

    def _config_file_is_written(self) -> bool:
        """Returns whether the configuration file is written."""
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"))

    def _database_relation_is_created(self) -> bool:
        return self._relation_created(DATABASE_RELATION_NAME)

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            str: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": "webui layer",
                "description": "pebble config layer for webui",
                "services": {
                    "webui": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": f"./webconsole/webconsole -webuicfg {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}",  # noqa: E501
                        "environment": self._environment_variables,
                    },
                },
            }
        )

    @property
    def _environment_variables(self) -> dict:
        return {
            "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
            "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
            "GRPC_TRACE": "all",
            "GRPC_VERBOSITY": "debug",
            "CONFIGPOD_DEPLOYMENT": "5G",
        }


if __name__ == "__main__":  # pragma: nocover
    main(WebuiOperatorCharm)
