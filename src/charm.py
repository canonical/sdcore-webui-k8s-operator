#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G Webui service for K8s."""

import json
import logging
from ipaddress import IPv4Address
from subprocess import CalledProcessError, check_output
from typing import List, Optional, Tuple

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires  # type: ignore[import]
from charms.loki_k8s.v1.loki_push_api import LogForwarder  # type: ignore[import]
from charms.sdcore_gnbsim_k8s.v0.fiveg_gnb_identity import (  # type: ignore[import]
    GnbIdentityRequires,
)
from charms.sdcore_upf_k8s.v0.fiveg_n4 import N4Requires  # type: ignore[import]
from charms.sdcore_webui_k8s.v0.sdcore_config import (  # type: ignore[import]
    SdcoreConfigProvides,
)
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer  # type: ignore[import]
from jinja2 import Environment, FileSystemLoader
from ops import ActiveStatus, BlockedStatus, CollectStatusEvent, ModelError, WaitingStatus
from ops.charm import CharmBase, EventBase
from ops.main import main
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/webui"
CONFIG_FILE_NAME = "webuicfg.conf"
FIVEG_N4_RELATION_NAME = "fiveg_n4"
GNB_IDENTITY_RELATION_NAME = "fiveg_gnb_identity"
COMMON_DATABASE_RELATION_NAME = "common_database"
AUTH_DATABASE_RELATION_NAME = "auth_database"
AUTH_DATABASE_NAME = "authentication"
COMMON_DATABASE_NAME = "free5gc"
SDCORE_CONFIG_RELATION_NAME = "sdcore-config"
GRPC_PORT = 9876
WEBUI_URL_PORT = 5000
LOGGING_RELATION_NAME = "logging"
WORKLOAD_VERSION_FILE_NAME = "/etc/workload-version"
GNB_CONFIG_PATH = f"{BASE_CONFIG_PATH}/gnb_config.json"
UPF_CONFIG_PATH = f"{BASE_CONFIG_PATH}/upf_config.json"
WEBUI_CONFIG_PATH = f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"


def _get_pod_ip() -> Optional[str]:
    """Return the pod IP using juju client."""
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
    """Render webui configuration file based on Jinja template."""
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
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to perform if we're removing the
            # charm.
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
        self.unit.set_ports(GRPC_PORT, WEBUI_URL_PORT)
        self.ingress = IngressPerAppRequirer(
            charm=self,
            port=WEBUI_URL_PORT,
            relation_name="ingress",
            strip_prefix=True,
        )
        self.fiveg_n4 = N4Requires(charm=self, relation_name=FIVEG_N4_RELATION_NAME)
        self._gnb_identity = GnbIdentityRequires(self, GNB_IDENTITY_RELATION_NAME)
        self._logging = LogForwarder(charm=self, relation_name=LOGGING_RELATION_NAME)
        self._sdcore_config = SdcoreConfigProvides(self, SDCORE_CONFIG_RELATION_NAME)
        self.framework.observe(self.on.update_status, self._configure_webui)
        self.framework.observe(self.on.webui_pebble_ready, self._configure_webui)
        self.framework.observe(self.on.common_database_relation_joined, self._configure_webui)
        self.framework.observe(self.on.auth_database_relation_joined, self._configure_webui)
        self.framework.observe(self._common_database.on.database_created, self._configure_webui)
        self.framework.observe(self._auth_database.on.database_created, self._configure_webui)
        self.framework.observe(self._common_database.on.endpoints_changed, self._configure_webui)
        self.framework.observe(self._auth_database.on.endpoints_changed, self._configure_webui)
        self.framework.observe(self.on.sdcore_config_relation_joined, self._configure_webui)
        self.framework.observe(self.fiveg_n4.on.fiveg_n4_available, self._configure_webui)
        self.framework.observe(
            self._gnb_identity.on.fiveg_gnb_identity_available,
            self._configure_webui,
        )
        self.framework.observe(
            self.on[GNB_IDENTITY_RELATION_NAME].relation_broken,
            self._configure_webui,
        )
        self.framework.observe(
            self.on[FIVEG_N4_RELATION_NAME].relation_broken,
            self._configure_webui,
        )
        # Handling config changed event to publish the new url if the unit reboots and gets new IP
        self.framework.observe(self.on.config_changed, self._configure_webui)

    def _configure_webui(self, _: EventBase) -> None:
        """Handle Juju events.

        Whenever a Juju event is emitted, this method performs a couple of checks to make sure that
        the workload is ready to be started. Then, it configures the Webui workload,
        runs the Pebble services and expose the service information through charm's interface.
        """
        if not self._container.can_connect():
            return
        if not self._container.exists(path=BASE_CONFIG_PATH):
            return
        self._create_upf_config_file()
        self._create_gnb_config_file()
        for relation in [COMMON_DATABASE_RELATION_NAME, AUTH_DATABASE_RELATION_NAME]:
            if not self._relation_created(relation):
                return
        if not self._common_database_resource_is_available():
            return
        if not self._auth_database_resource_is_available():
            return
        desired_config_file = self._generate_webui_config_file()

        if config_update_required := self._is_config_update_required(desired_config_file):
            self._write_file_in_workload(WEBUI_CONFIG_PATH, desired_config_file)

        self._configure_workload(restart=config_update_required)
        self._publish_sdcore_config_url()

    def _on_collect_unit_status(self, event: CollectStatusEvent):   # noqa: C901
        """Check the unit status and set to Unit when CollectStatusEvent is fired.

        Also sets the workload version if present in rock.
        """
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to perform if we're removing the
            # charm.
            event.add_status(BlockedStatus("Scaling is not implemented for this charm"))
            logger.info("Scaling is not implemented for this charm")
            return
        for relation in [COMMON_DATABASE_RELATION_NAME, AUTH_DATABASE_RELATION_NAME]:
            if not self._relation_created(relation):
                event.add_status(BlockedStatus(f"Waiting for {relation} relation to be created"))
                logger.info(f"Waiting for {relation} relation to be created")
                return
        if not self._common_database_resource_is_available():
            event.add_status(WaitingStatus("Waiting for the common database to be available"))
            logger.info("Waiting for the common database to be available")
            return
        if not self._auth_database_resource_is_available():
            event.add_status(WaitingStatus("Waiting for the auth database to be available"))
            logger.info("Waiting for the auth database to be available")
            return
        if not self._container.can_connect():
            event.add_status(WaitingStatus("Waiting for container to be ready"))
            logger.info("Waiting for container to be ready")
            return

        self.unit.set_workload_version(self._get_workload_version())

        if not self._container.exists(path=BASE_CONFIG_PATH):
            event.add_status(WaitingStatus("Waiting for storage to be attached"))
            logger.info("Waiting for storage to be attached")
            return
        if not self._webui_config_file_exists():
            event.add_status(WaitingStatus("Waiting for webui config file to be stored"))
            logger.info("Waiting for webui config file to be stored")
            return
        if not self._container.exists(path=UPF_CONFIG_PATH):
            event.add_status(WaitingStatus("Waiting for UPF config file to be stored"))
            logger.info("Waiting for UPF config file to be stored")
            return
        if not self._container.exists(path=GNB_CONFIG_PATH):
            event.add_status(WaitingStatus("Waiting for GNB config file to be stored"))
            logger.info("Waiting for GNB config file to be stored")
            return
        if not self._webui_service_is_running():
            event.add_status(WaitingStatus("Waiting for webui service to start"))
            logger.info("Waiting for webui service to start")
            return

        event.add_status(ActiveStatus())

    def _publish_sdcore_config_url(self) -> None:
        if not self._relation_created(SDCORE_CONFIG_RELATION_NAME):
            return
        if not self._webui_service_is_running():
            return
        webui_config_url = self._get_webui_config_url()
        self._sdcore_config.set_webui_url_in_all_relations(webui_url=webui_config_url)

    def _configure_workload(self, restart: bool = False) -> None:
        """Configure and restart the workload if required.

        This method detects the changes between the Pebble layer and the Pebble services.
        If a change is detected, it applies the desired configuration.
        Then, it restarts the workload if a restart is required.

        Args:
            restart (bool): Whether to restart the Webui container.
        """
        plan = self._container.get_plan()
        if plan.services != self._pebble_layer.services:
            self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
            self._container.replan()
            logger.info("New layer added: %s", self._pebble_layer)
        if restart:
            self._container.restart(self._service_name)
            logger.info("Restarted container %s", self._service_name)
            return

    def _is_config_update_required(self, content: str) -> bool:
        return not self._webui_config_file_exists() or not self._webui_config_file_content_matches(
            content=content)

    def _webui_config_file_content_matches(self, content: str) -> bool:
        if not self._webui_config_file_exists():
            return False
        existing_content = self._container.pull(path=WEBUI_CONFIG_PATH)
        return existing_content.read() == content

    def _webui_config_file_exists(self) -> bool:
        return bool(self._container.exists(WEBUI_CONFIG_PATH))

    def _generate_webui_config_file(self) -> str:
        return render_config_file(
            common_database_name=COMMON_DATABASE_NAME,
            common_database_url=self._get_common_database_url(),
            auth_database_name=AUTH_DATABASE_NAME,
            auth_database_url=self._get_auth_database_url(),
        )

    def _webui_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False
        try:
            service = self._container.get_service(self._service_name)
        except ModelError:
            return False
        return service.is_running()

    def _create_upf_config_file(self) -> None:
        """Generate the UPF config file based on the content of the `fiveg_n4` relations.

        If the relation does not exist, an empty list [] is written on the file.
        """
        if not self.model.relations.get(FIVEG_N4_RELATION_NAME):
            logger.info("Relation %s not available", FIVEG_N4_RELATION_NAME)
        upf_existing_content = self._get_file_content(file_path=UPF_CONFIG_PATH)
        new_upf_config = self._get_upf_config()
        if not upf_existing_content or not self._file_content_matches(
            existing_content=upf_existing_content,
            new_content=new_upf_config,
        ):
            self._write_file_in_workload(UPF_CONFIG_PATH, new_upf_config)

    def _create_gnb_config_file(self) -> None:
        """Generate the gNB config file based on the content of the `fiveg_gnb_identity` relations.

        If the relation does not exist, an empty list [] is written on the file.
        """
        if not self.model.relations.get(GNB_IDENTITY_RELATION_NAME):
            logger.info("Relation %s not available", GNB_IDENTITY_RELATION_NAME)
        gnb_existing_content = self._get_file_content(file_path=GNB_CONFIG_PATH)
        gnb_new_config = self._get_gnb_config()
        if not gnb_existing_content or not self._file_content_matches(
            existing_content=gnb_existing_content,
            new_content=gnb_new_config,
        ):
            self._write_file_in_workload(GNB_CONFIG_PATH, gnb_new_config)

    def _get_file_content(self, file_path: str) -> str:
        """Return the content of the file as a string.

        Return an empty string if the file does not exist.
        """
        if self._container.exists(path=file_path):
            existing_content_stringio = self._container.pull(path=file_path)
            return existing_content_stringio.read()
        return ""

    def _get_upf_host_port_list_from_relation(self) -> List[Tuple[str, int]]:
        upf_host_port_list = []
        for fiveg_n4_relation in self.model.relations.get(FIVEG_N4_RELATION_NAME, []):
            if not fiveg_n4_relation.app:
                logger.warning(
                    "Application missing from the %s relation data",
                    FIVEG_N4_RELATION_NAME,
                )
                continue
            port = fiveg_n4_relation.data[fiveg_n4_relation.app].get("upf_port", "")
            hostname = fiveg_n4_relation.data[fiveg_n4_relation.app].get("upf_hostname", "")
            if hostname and port:
                upf_host_port_list.append((hostname, int(port)))
        return upf_host_port_list

    def _get_gnb_name_tac_list_from_relation(self) -> List[Tuple[str, int]]:
        gnb_name_tac_list = []
        for gnb_identity_relation in self.model.relations.get(GNB_IDENTITY_RELATION_NAME, []):
            if not gnb_identity_relation.app:
                logger.warning(
                    "Application missing from the %s relation data",
                    GNB_IDENTITY_RELATION_NAME,
                )
                continue
            gnb_name = gnb_identity_relation.data[gnb_identity_relation.app].get("gnb_name", "")
            gnb_tac = gnb_identity_relation.data[gnb_identity_relation.app].get("tac", "")
            if gnb_name and gnb_tac:
                gnb_name_tac_list.append((gnb_name, int(gnb_tac)))
        return gnb_name_tac_list

    def _get_upf_config(self) -> str:
        """Get the UPF configuration (UPF hostname and port) for the NMS in json format."""
        upf_host_port_list = self._get_upf_host_port_list_from_relation()

        upf_config = []
        for upf_hostname, upf_port in upf_host_port_list:
            upf_config_entry = {
                "hostname": upf_hostname,
                "port": str(upf_port),
            }
            upf_config.append(upf_config_entry)
        return json.dumps(upf_config, sort_keys=True)

    def _get_gnb_config(self) -> str:
        """Get the gNB configuration (gNB name ang TAC) in json format."""
        gnb_name_tac_list = self._get_gnb_name_tac_list_from_relation()

        gnb_config = []
        for gnb_name, gnb_tac in gnb_name_tac_list:
            gnb_conf_entry = {"name": gnb_name, "tac": str(gnb_tac)}
            gnb_config.append(gnb_conf_entry)

        return json.dumps(gnb_config, sort_keys=True)

    @staticmethod
    def _file_content_matches(existing_content: str, new_content: str) -> bool:
        """Return whether two config file contents match."""
        try:
            existing_content_list = json.loads(existing_content)
            new_content_list = json.loads(new_content)
            return existing_content_list == new_content_list
        except json.JSONDecodeError:
            return False

    def _get_common_database_url(self) -> str:
        if not self._common_database_resource_is_available():
            raise RuntimeError(f"Database `{COMMON_DATABASE_NAME}` is not available")
        return self._common_database.fetch_relation_data()[self._common_database.relations[0].id][
            "uris"
        ].split(",")[0]

    def _get_auth_database_url(self) -> str:
        if not self._auth_database_resource_is_available():
            raise RuntimeError(f"Database `{AUTH_DATABASE_NAME}` is not available")
        return self._auth_database.fetch_relation_data()[self._auth_database.relations[0].id][
            "uris"
        ].split(",")[0]

    def _common_database_resource_is_available(self) -> bool:
        return bool(self._common_database.is_resource_created())

    def _auth_database_resource_is_available(self) -> bool:
        return bool(self._auth_database.is_resource_created())

    def _get_workload_version(self) -> str:
        """Return the workload version.

        Checks for the presence of /etc/workload-version file
        and if present, returns the contents of that file. If
        the file is not present, an empty string is returned.

        Returns:
            string: A human readable string representing the
            version of the workload
        """
        if self._container.exists(path=f"{WORKLOAD_VERSION_FILE_NAME}"):
            version_file_content = self._container.pull(
                path=f"{WORKLOAD_VERSION_FILE_NAME}"
            ).read()
            return version_file_content
        return ""

    def _write_file_in_workload(self, path: str, content: str) -> None:
        self._container.push(path=path, source=content)
        logger.info("Pushed %s config file", path)

    def _relation_created(self, relation_name: str) -> bool:
        return bool(self.model.relations[relation_name])

    def _get_webui_config_url(self) -> str:
        return f"{self._service_name}:{GRPC_PORT}"

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
            "SWAGGER_HOST": _get_pod_ip(),
            "UPF_CONFIG_PATH": UPF_CONFIG_PATH,
            "GNB_CONFIG_PATH": GNB_CONFIG_PATH,
        }


if __name__ == "__main__":  # pragma: nocover
    main(WebuiOperatorCharm)
