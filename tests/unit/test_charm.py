# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import WebuiOperatorCharm


def read_file_content(path: str) -> str:
    """Reads a file and returns as a string.

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

    def _create_database_relation_and_populate_data(self) -> int:
        database_url = "http://6.6.6.6"
        database_username = "banana"
        database_password = "pizza"
        database_relation_id = self.harness.add_relation("database", "mongodb")
        self.harness.add_relation_unit(
            relation_id=database_relation_id, remote_unit_name="mongodb/0"
        )
        self.harness.update_relation_data(
            relation_id=database_relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": database_username,
                "password": database_password,
                "uris": database_url,
            },
        )
        return database_relation_id

    def test_given_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.set_can_connect(container="webui", val=True)
        self.harness.container_pebble_ready("webui")
        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for database relation to be created"),
        )

    def test_given_config_file_not_written_when_database_is_created_then_config_file_is_written(
        self,
    ):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        self.assertEqual(
            (root / "etc/webui/webuicfg.conf").read_text(), expected_config_file_content
        )

    def test_given_config_file_content_doesnt_match_when_database_changed_then_content_is_updated(
        self,
    ):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("Obviously different content")
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        self.assertEqual(
            (root / "etc/webui/webuicfg.conf").read_text(), expected_config_file_content
        )

    def test_given_config_file_is_written_when_pebble_ready_then_pebble_plan_is_applied(self):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("Obviously different content")

        self._create_database_relation_and_populate_data()

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

    def test_given_config_file_is_written_when_pebble_ready_then_status_is_active(self):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("Obviously different content")

        self._create_database_relation_and_populate_data()

        self.harness.container_pebble_ready("webui")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_webui_charm_in_active_state_when_database_relation_breaks_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root("webui")
        (root / "etc/webui/webuicfg.conf").write_text("Obviously different content")
        database_relation_id = self._create_database_relation_and_populate_data()
        self.harness.container_pebble_ready("webui")

        self.harness.remove_relation(database_relation_id)

        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Waiting for database relation")
        )

    def test_given_config_file_is_not_written_when_pebble_ready_then_status_is_waiting(self):
        self.harness.add_storage("config", attach=True)

        self._create_database_relation_and_populate_data()

        self.harness.container_pebble_ready("webui")

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for config file to be written"),
        )

    def test_given_storage_not_attached_when_on_database_created_then_status_is_waiting(self):
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for storage to be attached")
        )

    @patch("charm.check_output")
    @patch("charms.sdcore_webui.v0.sdcore_management.SdcoreManagementProvides.set_management_url")
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
    @patch("charms.sdcore_webui.v0.sdcore_management.SdcoreManagementProvides.set_management_url")
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
