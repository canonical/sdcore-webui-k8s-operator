#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G Webui service for K8s."""

import logging
from ipaddress import IPv4Address
from subprocess import CalledProcessError, check_output
from typing import Optional

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires  # type: ignore[import]
from charms.loki_k8s.v1.loki_push_api import LogForwarder  # type: ignore[import]
from charms.sdcore_webui_k8s.v0.sdcore_management import (  # type: ignore[import]
    SdcoreManagementProvides,
)
from jinja2 import Environment, FileSystemLoader
from ops import ActiveStatus, BlockedStatus, RelationBrokenEvent, WaitingStatus
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/webui"
CONFIG_FILE_NAME = "webuicfg.conf"
COMMON_DATABASE_RELATION_NAME = "common_database"
AUTH_DATABASE_RELATION_NAME = "auth_database"
AUTH_DATABASE_NAME = "authentication"
COMMON_DATABASE_NAME = "free5gc"
SDCORE_MANAGEMENT_RELATION_NAME = "sdcore-management"
GRPC_PORT = 9876
WEBUI_URL_PORT = 5000
LOGGING_RELATION_NAME = "logging"


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


def render_config_file(
    common_database_name: str,
    common_database_url: str,
    auth_database_name: str,
    auth_database_url: str,
) -> str:
    """Renders webui configuration file based on Jinja template.

    Args:
        common_database_name: Common Database Name
        common_database_url: Common Database URL.
        auth_database_name: Authentication Database Name
        auth_database_url: Authentication Database URL.

    Returns:
        str: Content of the configuration file.
    """
    jinja2_environment = Environment(loader=FileSystemLoader("src/templates/"))
    template = jinja2_environment.get_template("webuicfg.conf.j2")
    return template.render(
        common_database_name=common_database_name,
        common_database_url=common_database_url,
        auth_database_name=auth_database_name,
        auth_database_url=auth_database_url,
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
        self._common_database = DatabaseRequires(
            self,
            relation_name=COMMON_DATABASE_RELATION_NAME,
            database_name=COMMON_DATABASE_NAME,
            extra_user_roles="admin",
        )
        self._auth_database = DatabaseRequires(
            self,
            relation_name=AUTH_DATABASE_RELATION_NAME,
            database_name=AUTH_DATABASE_NAME,
            extra_user_roles="admin",
        )
        self._logging = LogForwarder(charm=self, relation_name=LOGGING_RELATION_NAME)
        self._sdcore_management = SdcoreManagementProvides(self, SDCORE_MANAGEMENT_RELATION_NAME)
        self.unit.set_ports(GRPC_PORT, WEBUI_URL_PORT)
        self.framework.observe(self.on.webui_pebble_ready, self._configure_webui)
        self.framework.observe(self.on.common_database_relation_joined, self._configure_webui)
        self.framework.observe(
            self.on.common_database_relation_broken, self._on_common_database_relation_broken
        )
        self.framework.observe(self.on.auth_database_relation_joined, self._configure_webui)
        self.framework.observe(
            self.on.auth_database_relation_broken, self._on_auth_database_relation_broken
        )
        self.framework.observe(self._common_database.on.database_created, self._configure_webui)
        self.framework.observe(self._auth_database.on.database_created, self._configure_webui)
        self.framework.observe(self._common_database.on.endpoints_changed, self._configure_webui)
        self.framework.observe(self._auth_database.on.endpoints_changed, self._configure_webui)
        self.framework.observe(
            self.on.sdcore_management_relation_joined, self._publish_sdcore_management_url
        )
        # Handling config changed event to publish the new url if the unit reboots and gets new IP
        self.framework.observe(self.on.config_changed, self._publish_sdcore_management_url)

    def _configure_webui(self, event: EventBase) -> None:
        """Main callback function of the Webui operator.

        Handles config changes.
        Manages pebble layer and Juju unit status.

        Args:
            event: Juju event
        """
        for relation in [COMMON_DATABASE_RELATION_NAME, AUTH_DATABASE_RELATION_NAME]:
            if not self._relation_created(relation):
                self.unit.status = BlockedStatus(f"Waiting for {relation} relation to be created")
                return
        if not self._common_database_is_available():
            self.unit.status = WaitingStatus("Waiting for the common database to be available")
            return
        if not self._auth_database_is_available():
            self.unit.status = WaitingStatus("Waiting for the auth database to be available")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            return
        if not self._container.exists(path=BASE_CONFIG_PATH):
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            return

        config_file_content = render_config_file(
            common_database_name=COMMON_DATABASE_NAME,
            common_database_url=self._get_common_database_url(),
            auth_database_name=AUTH_DATABASE_NAME,
            auth_database_url=self._get_auth_database_url(),
        )
        self._write_config_file(content=config_file_content)
        self._container.add_layer("webui", self._pebble_layer, combine=True)
        self._container.replan()
        self._container.restart(self._service_name)
        self.unit.status = ActiveStatus()

    def _get_common_database_url(self) -> str:
        """Returns the common database url.

        Returns:
            str: The common database url.
        """
        if not self._common_database_is_available():
            raise RuntimeError(f"Database `{COMMON_DATABASE_NAME}` is not available")
        return self._common_database.fetch_relation_data()[self._common_database.relations[0].id][
            "uris"
        ].split(",")[0]

    def _get_auth_database_url(self) -> str:
        """Returns the authentication database url.

        Returns:
            str: The authentication database url.
        """
        if not self._auth_database_is_available():
            raise RuntimeError(f"Database `{AUTH_DATABASE_NAME}` is not available")
        return self._auth_database.fetch_relation_data()[self._auth_database.relations[0].id][
            "uris"
        ].split(",")[0]

    def _common_database_is_available(self) -> bool:
        """Returns whether common database relation is available.

        Returns:
            bool: Whether common database relation is available.
        """
        return bool(self._common_database.is_resource_created())

    def _auth_database_is_available(self) -> bool:
        """Returns whether authentication database relation is available.

        Returns:
            bool: Whether authentication database relation is available.
        """
        return bool(self._auth_database.is_resource_created())

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

    def _on_common_database_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Event handler for common database relation broken.

        Args:
            event: Juju relation broken event
        """
        if not self.model.relations[COMMON_DATABASE_RELATION_NAME]:
            self.unit.status = BlockedStatus(
                f"Waiting for {COMMON_DATABASE_RELATION_NAME} relation"
            )

    def _on_auth_database_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Event handler for auth database relation broken.

        Args:
            event: Juju relation broken event
        """
        if not self.model.relations[AUTH_DATABASE_RELATION_NAME]:
            self.unit.status = BlockedStatus(f"Waiting for {AUTH_DATABASE_RELATION_NAME} relation")

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
