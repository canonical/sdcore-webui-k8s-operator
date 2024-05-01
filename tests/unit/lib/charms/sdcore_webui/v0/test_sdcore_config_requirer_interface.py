# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops import testing

from tests.unit.lib.charms.sdcore_webui.v0.dummy_sdcore_config_requirer_charm.src.dummy_requirer_charm import (  # noqa: E501
    DummySdcoreConfigRequirerCharm,
)

DUMMY_REQUIRER_CHARM = "tests.unit.lib.charms.sdcore_webui.v0.dummy_sdcore_config_requirer_charm.src.dummy_requirer_charm.DummySdcoreConfigRequirerCharm"  # noqa: E501


class TestSdcoreConfigRequirer(unittest.TestCase):
    def setUp(self):
        self.relation_name = "sdcore_config"
        self.remote_app_name = "dummy-sdcore-config-provider"
        self.remote_unit_name = f"{self.remote_app_name}/0"
        self.harness = testing.Harness(DummySdcoreConfigRequirerCharm)
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

    @patch(f"{DUMMY_REQUIRER_CHARM}._on_webui_url_available")
    def test_given_webui_information_in_relation_data_when_relation_changed_then_webui_url_available_event_emitted(  # noqa: E501
        self, patch_on_webui_url_available
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "webui_url": "sdcore-webui-k8s:9876",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )

        patch_on_webui_url_available.assert_called()

    @patch(f"{DUMMY_REQUIRER_CHARM}._on_webui_url_available")
    def test_given_webui_information_not_in_relation_data_when_relation_changed_then_webui_url_available_event_not_emitted(  # noqa: E501
        self, patch_on_webui_url_available
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)
        relation_data = {}

        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )

        patch_on_webui_url_available.assert_not_called()

    @patch(f"{DUMMY_REQUIRER_CHARM}._on_webui_url_available")
    def test_given_invalid_webui_information_in_relation_data_when_relation_changed_then_webui_url_available_event_not_emitted(  # noqa: E501
        self, patch_on_webui_url_available
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)
        relation_data = {"foo": "bar"}

        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )

        patch_on_webui_url_available.assert_not_called()

    def test_given_invalid_webui_information_in_relation_data_when_relation_changed_then_error_is_logged(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)
        relation_data = {"foo": "bar"}

        with self.assertLogs(level="DEBUG") as log:
            self.harness.update_relation_data(
                relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
            )
            self.assertIn(
                "ERROR:lib.charms.sdcore_webui_k8s.v0.sdcore_config:Invalid data", log.output[0]
            )

    def test_given_webui_information_in_relation_data_when_get_webui_url_is_called_then_expected_url_is_returned(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "webui_url": "sdcore-webui-k8s:9876",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )

        webui_url = self.harness.charm.webui_requirer.webui_url
        self.assertEqual(webui_url, "sdcore-webui-k8s:9876")

    def test_given_webui_information_not_in_relation_data_when_get_webui_url_then_returns_none(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)
        relation_data = {}

        with self.assertLogs(level="DEBUG") as log:
            self.harness.update_relation_data(
                relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
            )
            webui_url = self.harness.charm.webui_requirer.webui_url
            self.assertIsNone(webui_url)
            self.assertIn(
                "ERROR:lib.charms.sdcore_webui_k8s.v0.sdcore_config:Invalid data",  # noqa: E501
                log.output[0],
            )

    def test_given_webui_information_in_relation_data_is_not_valid_when_get_webui_url_then_returns_none_and_error_is_logged(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)
        relation_data = {"foo": "bar"}

        with self.assertLogs(level="DEBUG") as log:
            self.harness.update_relation_data(
                relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
            )
            webui_url = self.harness.charm.webui_requirer.webui_url
            self.assertIsNone(webui_url)
            self.assertIn(
                "ERROR:lib.charms.sdcore_webui_k8s.v0.sdcore_config:Invalid data",  # noqa: E501
                log.output[0],
            )

    @patch("lib.charms.sdcore_webui_k8s.v0.sdcore_config.SdcoreConfigRequirerCharmEvents.webui_broken")
    def test_given_sdcore_config_relation_created_when_relation_broken_then_webui_broken_event_emitted(  # noqa: E501
        self, patched_webui_broken_event
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        self.harness.remove_relation(relation_id)

        calls = [call.emit()]
        patched_webui_broken_event.assert_has_calls(calls)

