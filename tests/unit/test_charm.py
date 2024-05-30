# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import Mock, call, patch

import pytest
from charm import WebuiOperatorCharm
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, ModelError, WaitingStatus

AUTH_DATABASE_RELATION_NAME = "auth_database"
CONTAINER = "webui"
CONTAINER_CONFIG_FILE_PATH = "etc/webui/webuicfg.conf"
COMMON_DATABASE_RELATION_NAME = "common_database"
EXPECTED_CONFIG_FILE_PATH = "tests/unit/expected_webui_cfg.json"
SDCORE_CONFIG_RELATION_NAME = "sdcore-config"


def read_file_content(path: str) -> str:
    with open(path, "r") as f:
        content = f.read()
    return content


class TestCharm:

    patcher_check_output = patch("charm.check_output")
    patcher_set_management_url = patch(
        "charms.sdcore_webui_k8s.v0.sdcore_management.SdcoreManagementProvides.set_management_url"
    )
    patcher_get_service = patch("ops.model.Container.get_service")
    patcher_set_webui_url = patch(
        "charms.sdcore_webui_k8s.v0.sdcore_config.SdcoreConfigProvides.set_webui_url"
    )
    patcher_set_webui_url_in_all_relations = patch(
        "charms.sdcore_webui_k8s.v0.sdcore_config.SdcoreConfigProvides.set_webui_url_in_all_relations"
    )

    @pytest.fixture()
    def setUp(self):
        self.mock_check_output = TestCharm.patcher_check_output.start()
        self.mock_set_management_url = TestCharm.patcher_set_management_url.start()
        self.mock_get_service = TestCharm.patcher_get_service.start()
        self.mock_set_webui_url = TestCharm.patcher_set_webui_url.start()
        self.mock_set_webui_url_in_all_relations = TestCharm.patcher_set_webui_url_in_all_relations.start()  # noqa: E501

    @staticmethod
    def tearDown() -> None:
        patch.stopall()

    @pytest.fixture(autouse=True)
    def harness(self, setUp, request):
        self.harness = testing.Harness(WebuiOperatorCharm)
        self.harness.set_model_name(name="whatever")
        self.harness.set_leader(is_leader=True)
        self.harness.begin()
        yield self.harness
        self.harness.cleanup()
        request.addfinalizer(self.tearDown)

    def _create_common_database_relation_and_populate_data(self) -> int:
        relation_id = self.harness.add_relation(COMMON_DATABASE_RELATION_NAME, "mongodb")  # type:ignore
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="mongodb/0")  # type:ignore
        self.harness.update_relation_data(  # type:ignore
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": "banana",
                "password": "pizza",
                "uris": "1.9.11.4:1234",
            },
        )
        return relation_id

    def _create_auth_database_relation_and_populate_data(self) -> int:
        relation_id = self.harness.add_relation(AUTH_DATABASE_RELATION_NAME, "mongodb")  # type:ignore
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="mongodb/0")  # type:ignore
        self.harness.update_relation_data(  # type:ignore
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={
                "username": "apple",
                "password": "hamburger",
                "uris": "1.8.11.4:1234",
            },
        )
        return relation_id

    def _create_sdcore_management_relation(self) -> None:
        relation_id = self.harness.add_relation("sdcore-management", "requirer")  # type:ignore
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="requirer/0")  # type:ignore

    def _create_sdcore_config_relation(self, requirer) -> None:
        relation_id = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, requirer)  # type:ignore
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name=f"{requirer}/0")  # type:ignore

    def test_given_common_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for common_database relation to be created")  # noqa: E501

    def test_given_auth_database_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self._create_common_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus("Waiting for auth_database relation to be created")  # noqa: E501

    def test_given_config_file_not_written_when_databases_are_created_then_config_file_is_written(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_config_file_content_doesnt_match_when_database_changed_then_content_is_updated(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)
        (root / CONTAINER_CONFIG_FILE_PATH).write_text("Obviously different content")

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_storage_attached_and_config_file_exists_when_pebble_ready_then_config_file_is_written(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(container_name=CONTAINER)

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_pebble_plan_is_applied(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(container_name=CONTAINER)

        expected_plan = {
            "services": {
                CONTAINER: {
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
        updated_plan = self.harness.get_container_pebble_plan(CONTAINER).to_dict()
        assert expected_plan == updated_plan

    def test_given_container_is_ready_and_storage_attached_when_db_relation_added_then_pebble_plan_is_applied(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        expected_plan = {
            "services": {
                CONTAINER: {
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
        updated_plan = self.harness.get_container_pebble_plan(CONTAINER).to_dict()
        assert expected_plan == updated_plan

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(CONTAINER)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_container_is_ready_and_storage_attached_when_database_created_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)

        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_container_is_ready_and_storage_attached_when_db_enpoints_changed_then_status_is_active(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self._create_auth_database_relation_and_populate_data()
        relation_id = self._create_common_database_relation_and_populate_data()

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
        database_relation_id = self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.remove_relation(database_relation_id)
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus(
            "Waiting for common_database relation to be created"
        )

    def test_given_storage_not_attached_when_on_databases_are_created_then_status_is_waiting(self):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for storage to be attached"
        )

    def test_given_storage_attached_but_cannot_connect_to_container_when_db_created_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=False)
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for container to be ready")

    def test_given_storage_not_attached_when_on_database_endpoints_changed_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self._create_auth_database_relation_and_populate_data()
        relation_id = self._create_common_database_relation_and_populate_data()

        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="mongodb",
            key_values={"endpoints": "some endpoint"},
        )
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for storage to be attached"
        )

    def test_given_webui_endpoint_url_not_available_when_sdcore_management_relation_joined_then_management_url_not_set(  # noqa: E501
        self
    ):
        self.mock_check_output.return_value = ""

        self._create_sdcore_management_relation()

        self.mock_set_management_url.assert_not_called()

    def test_given_webui_endpoint_url_available_when_sdcore_management_relation_joined_then_management_url_is_passed_in_relation(  # noqa: E501
        self
    ):
        pod_ip = "10.0.0.1"
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.mock_check_output.return_value = pod_ip.encode()

        self._create_sdcore_management_relation()

        self.mock_set_management_url.assert_called_once_with(
            management_url=f"http://{pod_ip}:5000",
        )

    def test_given_webui_service_is_running_db_relations_are_joined_and_sdcore_config_relation_is_joined_when_config_changed_then_config_url_is_published_for_all_relations(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = None
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self._create_sdcore_config_relation("requirer")
        self.harness.charm._configure_webui(Mock())
        self.mock_set_webui_url_in_all_relations.assert_called_once_with(webui_url="webui:9876")

    def test_given_webui_service_is_running_when_several_sdcore_config_relations_are_joined_then_config_url_is_set_in_all_relations(  # noqa: E501
        self
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = None
        relation_id_1 = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, "requirer1")
        self.harness.add_relation_unit(relation_id=relation_id_1, remote_unit_name="requirer1")
        relation_id_2 = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, "requirer2")
        self.harness.add_relation_unit(relation_id=relation_id_2, remote_unit_name="requirer2")
        calls = [
            call.emit(webui_url="webui:9876", relation_id=relation_id_1),
            call.emit(webui_url="webui:9876", relation_id=relation_id_2),
        ]
        self.mock_set_webui_url.assert_has_calls(calls)

    def test_given_webui_service_is_not_running_when_sdcore_config_relation_joined_then_config_url_is_not_set_in_the_relations(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = ModelError()
        self._create_sdcore_config_relation(requirer="requirer1")
        self.mock_set_webui_url.assert_not_called()

    def test_given_common_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(COMMON_DATABASE_RELATION_NAME, "mongodb")
        self._create_auth_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for the common database to be available")  # noqa: E501

    def test_given_auth_db_relation_is_created_but_not_available_when_collect_status_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.harness.add_relation(AUTH_DATABASE_RELATION_NAME, "mongodb")
        self._create_common_database_relation_and_populate_data()

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for the auth database to be available")  # noqa: E501

    def test_given_config_file_does_not_exist_when_collect_status_then_status_is_waiting(self):
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for config file to be stored")  # noqa: E501

    def test_given_service_is_not_running_when_collect_status_then_status_is_waiting(self):
        self._create_common_database_relation_and_populate_data()
        self._create_auth_database_relation_and_populate_data()
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = ModelError()
        root = self.harness.get_filesystem_root(CONTAINER)
        (root / CONTAINER_CONFIG_FILE_PATH).write_text("something")

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus("Waiting for webui service to start")  # noqa: E501

    def test_given_unit_is_not_leader_when_collect_status_then_status_is_blocked(self):
        self.harness.set_leader(is_leader=False)

        self.harness.evaluate_status()

        assert self.harness.model.unit.status == BlockedStatus("Scaling is not implemented for this charm")  # noqa: E501
