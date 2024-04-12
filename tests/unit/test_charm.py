# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from charm import WebuiOperatorCharm
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

COMMON_DATABASE_RELATION_NAME = "common_database"
AUTH_DATABASE_RELATION_NAME = "auth_database"


def read_file_content(path: str) -> str:
    """Read a file and returns as a string.

    Args:
        path (str): path to the file.

    Returns:
        str: content of the file.
    """
    with open(path, "r") as f:
        content = f.read()
    return content


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(WebuiOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.harness.set_leader(is_leader=True)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _create_common_database_relation_and_populate_data(self) -> int:
        common_database_url = "1.9.11.4:1234"
        common_database_username = "banana"
        common_database_password = "pizza"
        common_database_relation_id = self.harness.add_relation(
            COMMON_DATABASE_RELATION_NAME, "mongodb"
        )
        self.harness.add_relation_unit(
            relation_id=common_database_relation_id, remote_unit_name="mongodb/0"
        )
        self.harness.update_relation_data(
            relation_id=common_database_relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": common_database_username,
                "password": common_database_password,
                "uris": common_database_url,
            },
        )
        return common_database_relation_id

    def _create_auth_database_relation_and_populate_data(self) -> int:
        auth_database_url = "1.9.11.4:1234"
        auth_database_username = "apple"
        auth_database_password = "hamburger"
        auth_database_relation_id = self.harness.add_relation(
            AUTH_DATABASE_RELATION_NAME, "mongodb"
        )
        self.harness.add_relation_unit(
            relation_id=auth_database_relation_id, remote_unit_name="mongodb/0"
        )
        self.harness.update_relation_data(
            relation_id=auth_database_relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": auth_database_username,
                "password": auth_database_password,
                "uris": auth_database_url,
            },
        )
        return auth_database_relation_id

    def test_given_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.container_pebble_ready("webui")
        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for common_database relation to be created"),
        )

    def test_given_auth_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.container_pebble_ready("webui")
        self._create_common_database_relation_and_populate_data()
        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for auth_database relation to be created"),
        )

    def test_given_config_file_not_written_when_databases_are_created_then_config_file_is_written(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        self.harness.set_can_connect(container="webui", val=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        self.assertEqual(
            (root / "etc/webui/webuicfg.conf").read_text(), expected_config_file_content
        )

    def test_given_config_file_content_doesnt_match_when_database_changed_then_content_is_updated(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("Obviously different content")
        self.harness.set_can_connect(container="webui", val=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        self.assertEqual(
            (root / "etc/webui/webuicfg.conf").read_text(), expected_config_file_content
        )

    def test_given_storage_attached_and_config_file_exists_when_pebble_ready_then_config_file_is_written(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(container_name="webui")

        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        self.assertEqual(
            (root / "etc/webui/webuicfg.conf").read_text(), expected_config_file_content
        )

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_pebble_plan_is_applied(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(container_name="webui")

        expected_plan = {
            "services": {
                "webui": {
                    "override": "replace",
                    "command": "/bin/webconsole --webuicfg /etc/webui/webuicfg.conf",
                    "startup": "enabled",
                    "environment": {
                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                        "GRPC_TRACE": "all",
                        "GRPC_VERBOSITY": "debug",
                        "CONFIGPOD_DEPLOYMENT": "5G",
                    },
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("webui").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_container_is_ready_and_storage_attached_when_db_relation_added_then_pebble_plan_is_applied(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        expected_plan = {
            "services": {
                "webui": {
                    "override": "replace",
                    "command": "/bin/webconsole --webuicfg /etc/webui/webuicfg.conf",
                    "startup": "enabled",
                    "environment": {
                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                        "GRPC_TRACE": "all",
                        "GRPC_VERBOSITY": "debug",
                        "CONFIGPOD_DEPLOYMENT": "5G",
                    },
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("webui").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready("webui")
        self.harness.evaluate_status()

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_container_is_ready_and_storage_attached_when_database_created_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.evaluate_status()
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_container_is_ready_and_storage_attached_when_db_enpoints_changed_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        self._create_auth_database_relation_and_populate_data()
        relation_id = self._create_common_database_relation_and_populate_data()

        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={"endpoints": "some-endpoint"},
        )
        self.harness.evaluate_status()
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_charm_active_status_when_database_relation_breaks_then_status_is_blocked(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        database_relation_id = self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.container_pebble_ready("webui")

        self.harness.remove_relation(database_relation_id)
        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for common_database relation to be created"),
        )

    def test_given_storage_not_attached_when_on_databases_are_created_then_status_is_waiting(self):
        self.harness.set_can_connect(container="webui", val=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for storage to be attached")
        )

    def test_given_storage_attached_but_cannot_connect_to_container_when_db_created_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=False)
        self.harness.add_storage("config", attach=True)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.evaluate_status()

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    def test_given_storage_not_attached_when_on_database_endpoints_changed_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self._create_auth_database_relation_and_populate_data()
        relation_id = self._create_common_database_relation_and_populate_data()
        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={"endpoints": "some endpoint"},
        )
        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for storage to be attached")
        )

    @patch("charm.check_output")
    @patch(
        "charms.sdcore_webui_k8s.v0.sdcore_management.SdcoreManagementProvides.set_management_url"
    )
    def test_given_webui_url_not_available_when_sdcore_management_relation_joined_then_url_not_set(  # noqa: E501
        self,
        patch_set_management_url,
        patch_check_output,
    ):
        patch_check_output.return_value = ""
        sdcore_management_relation = self.harness.add_relation("sdcore-management", "requirer")
        self.harness.add_relation_unit(
            relation_id=sdcore_management_relation, remote_unit_name="requirer/0"
        )
        patch_set_management_url.assert_not_called()

    @patch("charm.check_output")
    @patch(
        "charms.sdcore_webui_k8s.v0.sdcore_management.SdcoreManagementProvides.set_management_url"
    )
    def test_given_webui_url_available_when_sdcore_management_relation_joined_then_url_is_passed_in_relation(  # noqa: E501
        self,
        patch_set_management_url,
        patch_check_output,
    ):
        patch_check_output.return_value = b"10.0.0.1"
        sdcore_management_relation = self.harness.add_relation("sdcore-management", "requirer")
        self.harness.add_relation_unit(
            relation_id=sdcore_management_relation, remote_unit_name="requirer/0"
        )
        patch_set_management_url.assert_called_once_with(
            management_url="http://10.0.0.1:5000",
        )

    def test_given_common_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(COMMON_DATABASE_RELATION_NAME, "mongodb")
        self._create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for the common database to be available"),
        )

    def test_given_auth_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(AUTH_DATABASE_RELATION_NAME, "mongodb")
        self._create_common_database_relation_and_populate_data()

        self.harness.evaluate_status()

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for the auth database to be available"),
        )

    def test_given_config_file_does_not_exist_when_collect_status_then_status_is_waiting(self):
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)

        self.harness.evaluate_status()

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for config file to be stored")
        )

    def test_given_service_is_not_running_when_collect_status_then_status_is_waiting(self):
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.add_storage("config", attach=True)

        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("something")

        self.harness.evaluate_status()
        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for webui service to start")
        )

    def test_given_unit_is_not_leader_when_collect_status_then_status_is_blocked(self):
        self.harness.set_leader(is_leader=False)
        self.harness.evaluate_status()

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Scaling is not implemented for this charm"),
        )
