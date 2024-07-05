# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import call

from fixtures import WebuiUnitTestFixtures
from ops.model import ModelError

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


class TestCharmWorkloadConfiguration(WebuiUnitTestFixtures):
    def test_given_config_file_not_written_when_databases_are_created_then_config_file_is_written(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)

        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_config_file_content_doesnt_match_when_database_changed_then_content_is_updated(
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)
        (root / CONTAINER_CONFIG_FILE_PATH).write_text("Obviously different content")

        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_storage_attached_and_config_file_exists_when_pebble_ready_then_config_file_is_written(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        root = self.harness.get_filesystem_root(CONTAINER)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

        self.harness.container_pebble_ready(container_name=CONTAINER)

        expected_config_file_content = read_file_content(EXPECTED_CONFIG_FILE_PATH)
        assert (root / CONTAINER_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_container_is_ready_db_relation_exists_and_storage_attached_when_pebble_ready_then_pebble_plan_is_applied(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

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
                        "WEBUI_ENDPOINT": "123.456.789",
                        "UPF_CONFIG_PATH": "/etc/webui/upf_config.json",
                        "GNB_CONFIG_PATH": "/etc/webui/gnb_config.json",
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

        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()

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
                        "WEBUI_ENDPOINT": "123.456.789",
                        "UPF_CONFIG_PATH": "/etc/webui/upf_config.json",
                        "GNB_CONFIG_PATH": "/etc/webui/gnb_config.json",
                    },
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan(CONTAINER).to_dict()
        assert expected_plan == updated_plan
    """
    def test_given_webui_endpoint_url_not_available_when_sdcore_management_relation_joined_then_management_url_not_set(  # noqa: E501
        self
    ):
        self.mock_check_output.return_value = ""

        self.create_sdcore_management_relation()

        self.mock_set_management_url.assert_not_called()

    def test_given_webui_endpoint_url_available_when_sdcore_management_relation_joined_then_management_url_is_passed_in_relation(  # noqa: E501
        self
    ):
        pod_ip = "10.0.0.1"
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        self.mock_check_output.return_value = pod_ip.encode()

        self.create_sdcore_management_relation()

        self.mock_set_management_url.assert_called_once_with(
            management_url=f"http://{pod_ip}:5000",
        )
    """
    def test_given_storage_not_attached_when_sdcore_config_relation_is_created_then_config_url_is_not_published_for_relations(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=False)
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        self.create_sdcore_config_relation("requirer")
        self.mock_set_webui_url_in_all_relations.assert_not_called()

    def test_given_webui_service_is_running_db_relations_are_not_joined_when_sdcore_config_relation_is_joined_then_config_url_is_not_published_for_relations(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = None
        self.create_sdcore_config_relation("requirer")
        self.mock_set_webui_url_in_all_relations.assert_not_called()

    def test_given_webui_service_is_running_db_relations_are_not_joined_when_several_sdcore_config_relations_are_joined_then_config_url_is_set_in_all_relations(  # noqa: E501
        self
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = None
        self.create_common_database_relation_and_populate_data()
        self.create_auth_database_relation_and_populate_data()
        relation_id_1 = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, "requirer1")
        self.harness.add_relation_unit(relation_id=relation_id_1, remote_unit_name="requirer1")
        relation_id_2 = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, "requirer2")
        self.harness.add_relation_unit(relation_id=relation_id_2, remote_unit_name="requirer2")
        calls = [
            call.emit(webui_url="webui:9876"),
            call.emit(webui_url="webui:9876"),
        ]
        self.mock_set_webui_url_in_all_relations.assert_has_calls(calls)

    def test_given_webui_service_is_not_running_when_sdcore_config_relation_joined_then_config_url_is_not_set_in_the_relations(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=CONTAINER, val=True)
        self.harness.add_storage("config", attach=True)
        self.mock_get_service.side_effect = ModelError()
        self.create_sdcore_config_relation(requirer="requirer1")
        self.mock_set_webui_url_in_all_relations.assert_not_called()
