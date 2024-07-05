# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from fixtures import WebuiUnitTestFixtures
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus

AUTH_DATABASE_RELATION_NAME = "auth_database"
CONTAINER = "webui"
CONTAINER_CONFIG_FILE_PATH = "etc/webui/webuicfg.conf"
COMMON_DATABASE_RELATION_NAME = "common_database"
UPF_CONFIG_FILE = "etc/webui/upf_config.json"
GNB_CONFIG_FILE = "etc/webui/gnb_config.json"


class TestCharmStatus(WebuiUnitTestFixtures):

    def test_given_common_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self.create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for common_database relation to be created")  # noqa: E501

    def test_given_auth_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.create_common_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus("Waiting for auth_database relation to be created")  # noqa: E501

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_container_is_ready_and_storage_attached_when_database_created_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)

        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_container_is_ready_and_storage_attached_when_db_enpoints_changed_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.create_auth_database_relation_and_populate_data()
        relation_id = self.create_common_database_relation_and_populate_data()

        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={"endpoints": "some-endpoint"},
        )
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_charm_active_status_when_database_relation_breaks_then_status_is_blocked(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        database_relation_id = self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.remove_relation(database_relation_id)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus(
            "Waiting for common_database relation to be created"
        )

    @pytest.mark.parametrize(
        "existing_config_file,app_name",
        [
            pytest.param(UPF_CONFIG_FILE, "GNB", id="gNB_config_file_is_missing"),
            pytest.param(GNB_CONFIG_FILE, "UPF", id="UPF_config_file_is_missing"),
        ],
    )
    def test_given_config_file_not_available_when_evaluate_status_then_status_is_waiting(
        self, existing_config_file, app_name
    ):
        self.harness.disable_hooks()
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)
        (root / CONTAINER_CONFIG_FILE_PATH).write_text("something")
        (root / existing_config_file).write_text("something")
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.enable_hooks()
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            f"Waiting for {app_name} config file to be stored"
        )

    def test_given_storage_not_attached_when_on_databases_are_created_then_status_is_waiting(self):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for storage to be attached"
        )

    def test_given_storage_attached_but_cannot_connect_to_container_when_db_created_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=False)
        self.harness.add_storage("config", attach=True)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for container to be ready")

    def test_given_storage_not_attached_when_on_database_endpoints_changed_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.create_auth_database_relation_and_populate_data()
        relation_id = self.create_common_database_relation_and_populate_data()

        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={"endpoints": "some endpoint"},
        )
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for storage to be attached"
        )

    def test_given_common_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(COMMON_DATABASE_RELATION_NAME, "mongodb")
        self.create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for the common database to be available")  # noqa: E501

    def test_given_auth_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(AUTH_DATABASE_RELATION_NAME, "mongodb")
        self.create_common_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for the auth database to be available")  # noqa: E501

    def test_given_config_file_does_not_exist_when_collect_status_then_status_is_waiting(self):
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for config file to be stored")  # noqa: E501

    def test_given_service_is_not_running_when_collect_status_then_status_is_waiting(self):
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = ModelError()
        root = self.harness.get_filesystem_root(CONTAINER)
        (root / CONTAINER_CONFIG_FILE_PATH).write_text("something")
        (root / UPF_CONFIG_FILE).write_text("some")
        (root / GNB_CONFIG_FILE).write_text("content")

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for webui service to start")  # noqa: E501

    def test_given_unit_is_not_leader_when_collect_status_then_status_is_blocked(self):
        self.harness.set_leader(is_leader=False)

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus("Scaling is not implemented for this charm")  # noqa: E501
