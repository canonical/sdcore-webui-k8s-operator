#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G Webui service for K8s."""

import logging
from ipaddress import IPv4Address
from subprocess import CalledProcessError, check_output
from typing import Optional

from charms.data_platform_libs.v0.data_interfaces import (  # type: ignore[import]
    DatabaseRequires,
    DatabaseRequiresEvent,
)
from charms.sdcore_webui_k8s.v0.sdcore_management import (  # type: ignore[import]
    SdcoreManagementProvides,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/webui"
CONFIG_FILE_NAME = "webuicfg.conf"
DATABASE_RELATION_NAME = "database"
DATABASE_NAME = "free5gc"
SDCORE_MANAGEMENT_RELATION_NAME = "sdcore-management"
GRPC_PORT = 9876
WEBUI_URL_PORT = 5000


def _get_pod_ip() -> Optional[str]:
    """Returns the pod IP using juju client.

    Returns:
        str: The pod IP.
    """
    try:
        ip_address = check_output(["unit-get", "private-address"])
        return str(IPv4Address(ip_address.decode().strip())) if ip_address else None
    except (CalledProcessError, ValueError):
        return None


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
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to preform if we're removing the
            # charm.
            self.unit.status = BlockedStatus("Scaling is not implemented for this charm")
            return
        self._container_name = self._service_name = "webui"
        self._container = self.unit.get_container(self._container_name)
        self._database = DatabaseRequires(
            self,
            relation_name=DATABASE_RELATION_NAME,
            database_name=DATABASE_NAME,
            extra_user_roles="admin",
        )
        self._sdcore_management = SdcoreManagementProvides(self, SDCORE_MANAGEMENT_RELATION_NAME)
        self.unit.set_ports(GRPC_PORT, WEBUI_URL_PORT)

        self.framework.observe(self.on.update_status, self._configure)
        self.framework.observe(self.on.webui_pebble_ready, self._configure)
        self.framework.observe(self.on.database_relation_joined, self._configure)
        self.framework.observe(self.on.database_relation_broken, self._on_database_relation_broken)
        self.framework.observe(self._database.on.database_created, self._configure_db)
        self.framework.observe(self._database.on.endpoints_changed, self._configure_db)
        self.framework.observe(
            self.on.sdcore_management_relation_joined, self._publish_sdcore_management_url
        )
        # Handling config changed event to publish the new url if the unit reboots and gets new IP
        self.framework.observe(self.on.config_changed, self._publish_sdcore_management_url)

    def _configure(self, event: EventBase) -> None:
        """Juju event handler.

        Sets unit status, writes configuration file adds pebble layer.

        Args:
            event (EventBase): Juju event.
        """
        if not self._database_relation_is_created():
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            return
        if not self._container.exists(path=BASE_CONFIG_PATH):
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            return
        if not self._config_file_exists():
            self.unit.status = WaitingStatus("Waiting for config file to be written")
            return

        self._container.add_layer("webui", self._pebble_layer, combine=True)
        self._container.replan()
        self._container.restart(self._service_name)
        self.unit.status = ActiveStatus()

    def _configure_db(self, event: DatabaseRequiresEvent) -> None:
        """Handles database events (DatabaseCreatedEvent, DatabaseEndpointsChangedEvent).

        Args:
            event (DatabaseRequiresEvent): Juju event.
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._container.exists(path=BASE_CONFIG_PATH):
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            event.defer()
            return
        self._write_database_information_in_config_file(event.uris)
        self._configure(event)

    def _write_database_information_in_config_file(self, uris: str) -> None:
        """Extracts the MongoDb URL from uris and writes it in the config file.

        Args:
            uris (str): database connection URIs.
        """
        database_url = uris.split(",")[0]
        config_file_content = render_config_file(
            database_name=DATABASE_NAME, database_url=database_url
        )
        self._write_config_file(content=config_file_content)

    def _publish_sdcore_management_url(self, event: EventBase):
        """Sets the webui url in the sdcore management relation.

        Passes the url of webui to sdcore management relation.

        Args:
            event (EventBase): Juju event
        """
        if not self._relation_created(SDCORE_MANAGEMENT_RELATION_NAME):
            return
        if not self._get_webui_endpoint_url():
            event.defer()
            return
        self._sdcore_management.set_management_url(
            management_url=self._get_webui_endpoint_url(),
        )

    def _on_database_relation_broken(self, event: EventBase) -> None:
        """Event handler for database relation broken.

        Args:
            event: Juju event
        """
        self.unit.status = BlockedStatus("Waiting for database relation")

    def _write_config_file(self, content: str) -> None:
        """Writes configuration file based on provided content.

        Args:
            content: Configuration file content
        """
        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info("Pushed %s config file", CONFIG_FILE_NAME)

    def _config_file_exists(self) -> bool:
        """Returns whether the configuration file exists."""
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"))

    def _database_relation_is_created(self) -> bool:
        return self._relation_created(DATABASE_RELATION_NAME)

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    def _get_webui_endpoint_url(self) -> Optional[str]:
        """Returns the webui endpoint url.

        Returns:
            str: The webui endpoint url.
        """
        if not _get_pod_ip():
            return None
        return f"http://{_get_pod_ip()}:{WEBUI_URL_PORT}"

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
                        "command": f"/bin/webconsole --webuicfg {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}",  # noqa: E501
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
