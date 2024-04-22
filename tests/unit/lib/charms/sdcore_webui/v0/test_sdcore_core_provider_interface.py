# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

import pytest
from ops import testing

from tests.unit.lib.charms.sdcore_webui.v0.dummy_sdcore_config_provider_charm.src.dummy_provider_charm import (  # noqa: E501
    DummySdcoreConfigProviderCharm,
)

DUMMY_PROVIDER_CHARM = "tests.unit.lib.charms.sdcore_webui.v0.dummy_sdcore_config_provider_charm.src.dummy_provider_charm.DummySdcoreConfigProviderCharm"  # noqa: E501


class TestSdcoreConfigProvider(unittest.TestCase):
    def setUp(self):
        self.relation_name = "sdcore_config"
        self.remote_app_name = "dummy-sdcore-config-requirer"
        self.remote_unit_name = f"{self.remote_app_name}/0"
        self.harness = testing.Harness(DummySdcoreConfigProviderCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _create_relation(self, remote_app_name: str):
        relation_id = self.harness.add_relation(
            relation_name=self.relation_name, remote_app=remote_app_name
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{remote_app_name}/0"
        )

        return relation_id

    def test_given_unit_is_leader_when_sdcore_config_relation_joined_then_data_is_in_application_databag(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        expected_webui_url = "sdcore-webui-k8s:9876"

        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.app.name
        )
        self.assertEqual(relation_data["webui_url"], expected_webui_url)

    def test_given_unit_is_not_leader_when_sdcore_config_relation_joined_then_data_is_not_in_application_databag(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=False)

        with pytest.raises(RuntimeError):
            relation_id = self._create_relation(remote_app_name=self.remote_app_name)
            relation_data = self.harness.get_relation_data(
                relation_id=relation_id, app_or_unit=self.harness.charm.app.name
            )
            self.assertEqual(relation_data, {})

    @patch(f"{DUMMY_PROVIDER_CHARM}.WEBUI_URL", new_callable=PropertyMock)
    def test_given_provided_webui_url_is_not_valid_when_set_url_then_error_is_raised(  # noqa: E501
        self, patch_webui_url
    ):
        self.harness.set_leader(is_leader=True)
        patch_webui_url.return_value = False

        with pytest.raises(ValueError):
            self._create_relation(remote_app_name=self.remote_app_name)

    def test_given_unit_is_leader_and_sdcore_config_relation_is_not_created_when_set_webui_information_then_runtime_error_is_raised(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        relation_id_for_unexsistant_relation = 0

        with pytest.raises(RuntimeError) as e:
            self.harness.charm.webui_url_provider.set_webui_url(
                webui_url="sdcore-webui-k8s:9876", relation_id=relation_id_for_unexsistant_relation
            )
        self.assertEqual(str(e.value), "Relation sdcore_config not created yet.")

    def test_given_unit_is_leader_when_multiple_sdcore_config_relation_joined_then_data_in_application_databag(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        remote_app_name_1 = self.remote_app_name
        remote_app_name_2 = f"second-{self.remote_app_name}"
        expected_webui_url = "sdcore-webui-k8s:9876"

        relation_id_1 = self._create_relation(remote_app_name=remote_app_name_1)

        self.harness.get_relation_data(
            relation_id=relation_id_1, app_or_unit=self.harness.charm.app.name
        )
        relation_id_2 = self._create_relation(remote_app_name=remote_app_name_2)
        relation_data_2 = self.harness.get_relation_data(
            relation_id=relation_id_2, app_or_unit=self.harness.charm.app.name
        )
        self.assertEqual(relation_data_2["webui_url"], expected_webui_url)
