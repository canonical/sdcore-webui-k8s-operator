# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from io import StringIO
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus, WaitingStatus

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
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, service_name, ports: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(WebuiOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _database_is_available(self) -> str:
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
        return database_url

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.exists")
    def test_given_config_file_not_written_when_database_is_created_then_config_file_is_written(
        self,
        patch_exists,
        patch_push,
    ):
        patch_exists.side_effect = [True, False]
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        patch_push.assert_called_with(
            path="/etc/webui/webuicfg.conf",
            source=expected_config_file_content,
        )

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    def test_given_config_file_content_doesnt_match_when_database_changed_then_content_is_updated(
        self,
        patch_exists,
        patch_pull,
        patch_push,
    ):
        patch_exists.side_effect = [True, True]
        patch_pull.return_value = StringIO("Obviously different content")
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        expected_config_file_content = read_file_content("tests/unit/expected_webui_cfg.json")

        patch_push.assert_called_with(
            path="/etc/webui/webuicfg.conf",
            source=expected_config_file_content,
        )

    @patch("ops.model.Container.exists")
    def test_given_config_file_is_written_when_pebble_ready_then_pebble_plan_is_applied(
        self,
        patch_exists,
    ):
        patch_exists.return_value = True

        self._database_is_available()

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

    @patch("ops.model.Container.exists")
    def test_given_config_file_is_written_when_pebble_ready_then_status_is_active(
        self, patch_exists
    ):
        patch_exists.return_value = True

        self._database_is_available()

        self.harness.container_pebble_ready("webui")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.exists")
    def test_given_config_file_is_not_written_when_pebble_ready_then_status_is_waiting(
        self, patch_exists
    ):
        patch_exists.return_value = False

        self._database_is_available()

        self.harness.container_pebble_ready("webui")

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for config file to be written"),
        )

    @patch("ops.model.Container.exists")
    def test_given_storage_not_attached_when_on_database_created_then_status_is_waiting(
        self,
        patch_exists,
    ):
        patch_exists.return_value = False
        self.harness.set_can_connect(container="webui", val=True)

        self.harness.charm._on_database_created(event=Mock(uris="1.9.11.4:1234,5.6.7.8:1111"))

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for storage to be attached")
        )
