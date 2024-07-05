# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import patch

import pytest
from charm import WebuiOperatorCharm
from ops import testing

AUTH_DATABASE_RELATION_NAME = "auth_database"
COMMON_DATABASE_RELATION_NAME = "common_database"
SDCORE_CONFIG_RELATION_NAME = "sdcore-config"
FIVEG_N4_RELATION_NAME = "fiveg_n4"
TEST_FIVEG_N4_PROVIDER_APP_NAME = "fiveg_n4_provider_app"
GNB_IDENTITY_RELATION_NAME = "fiveg_gnb_identity"
TEST_GNB_IDENTITY_PROVIDER_APP_NAME = "fiveg_gnb_identity_provider_app"

class WebuiUnitTestFixtures:

    patcher_check_output = patch("charm.check_output")
    patcher_set_management_url = patch(
        "charms.sdcore_webui_k8s.v0.sdcore_management.SdcoreManagementProvides.set_management_url"
    )
    patcher_get_service = patch("ops.model.Container.get_service")
    patcher_set_webui_url_in_all_relations = patch(
        "charms.sdcore_webui_k8s.v0.sdcore_config.SdcoreConfigProvides.set_webui_url_in_all_relations"
    )

    @pytest.fixture()
    def setUp(self):
        self.mock_check_output = WebuiUnitTestFixtures.patcher_check_output.start()
        self.mock_set_management_url = WebuiUnitTestFixtures.patcher_set_management_url.start()
        self.mock_get_service = WebuiUnitTestFixtures.patcher_get_service.start()
        self.mock_set_webui_url_in_all_relations = WebuiUnitTestFixtures.patcher_set_webui_url_in_all_relations.start()  # noqa: E501

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

    def create_common_database_relation_and_populate_data(self) -> int:
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

    def create_auth_database_relation_and_populate_data(self) -> int:
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

    def create_sdcore_config_relation(self, requirer) -> None:
        relation_id = self.harness.add_relation(SDCORE_CONFIG_RELATION_NAME, requirer)  # type:ignore
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name=f"{requirer}/0")  # type:ignore

    def set_gnb_identity_relation_data(self, key_values) -> int:
        """Create the fiveg_gnb_identity relation and set its data.

        Returns:
            int: ID of the created relation
        """
        gnb_identity_relation_id = self.harness.add_relation(
            relation_name=GNB_IDENTITY_RELATION_NAME,
            remote_app=TEST_GNB_IDENTITY_PROVIDER_APP_NAME,
        )
        self.harness.update_relation_data(
            relation_id=gnb_identity_relation_id,
            app_or_unit=TEST_GNB_IDENTITY_PROVIDER_APP_NAME,
            key_values=key_values,
        )
        return gnb_identity_relation_id

    def set_n4_relation_data(self, key_values) -> int:
        """Create the fiveg_n4 relation and set its data.

        Returns:
            int: ID of the created relation
        """
        fiveg_n4_relation_id = self.harness.add_relation(
            relation_name=FIVEG_N4_RELATION_NAME,
            remote_app=TEST_FIVEG_N4_PROVIDER_APP_NAME,
        )
        self.harness.update_relation_data(
            relation_id=fiveg_n4_relation_id,
            app_or_unit=TEST_FIVEG_N4_PROVIDER_APP_NAME,
            key_values=key_values,
        )
        return fiveg_n4_relation_id
