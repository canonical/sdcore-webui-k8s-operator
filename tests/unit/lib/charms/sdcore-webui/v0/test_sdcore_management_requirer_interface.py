# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import unittest
from unittest.mock import call, patch

from ops import testing
from ops.charm import CharmBase

from lib.charms.sdcore_webui.v0.sdcore_management import (
    ManagementUrlAvailable,
    SdcoreManagementRequires,
)

METADATA = """
name: sdcore-management-dummy-requirer
description: |
  Dummy charm implementing the requirer side of the sdcore_management interface.
summary: |
  Dummy charm implementing the requirer side of the sdcore_management interface.
requires:
  sdcore-management:
    interface: sdcore-management
"""

logger = logging.getLogger(__name__)

CHARM_LIB_PATH = "lib.charms.sdcore_webui.v0.sdcore_management"


class DummySdcoreManagementRequires(CharmBase):
    """Dummy charm implementing the requirer side of the sdcore_management interface."""

    def __init__(self, *args):
        super().__init__(*args)
        self.sdcore_management_requirer = SdcoreManagementRequires(self, "sdcore-management")
        self.framework.observe(
            self.sdcore_management_requirer.on.management_url_available,
            self._on_management_url_available,
        )

    def _on_management_url_available(self, event: ManagementUrlAvailable):
        logger.info("sdcore-webui endpoint address: %s", event.management_url)


class TestSdcoreManagementRequirer(unittest.TestCase):
    def setUp(self):
        self.relation_name = "sdcore-management"
        self.remote_app_name = "dummy-sdcore-management-provider"
        self.remote_unit_name = f"{self.remote_app_name}/0"
        self.harness = testing.Harness(DummySdcoreManagementRequires, meta=METADATA)
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

    @patch(
        f"{CHARM_LIB_PATH}.SdcoreManagementRequirerCharmEvents.management_url_available",
    )
    def test_given_management_url_in_relation_data_when_relation_changed_then_management_url_available_event_emitted(  # noqa: E501
        self,
        patch_url_available,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "management_url": "http://1.2.3.4:1234",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        calls = [
            call.emit(
                management_url="http://1.2.3.4:1234",
            ),
        ]
        patch_url_available.assert_has_calls(calls, any_order=True)

    @patch(
        f"{CHARM_LIB_PATH}.SdcoreManagementRequirerCharmEvents.management_url_available",
    )
    def test_given_management_url_not_in_relation_data_when_relation_changed_then_management_url_available_event_not_emitted(  # noqa: E501
        self,
        patch_url_available,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {}
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        patch_url_available.assert_not_called()

    @patch(
        f"{CHARM_LIB_PATH}.SdcoreManagementRequirerCharmEvents.management_url_available",
    )
    def test_given_management_url_not_valid_in_relation_data_when_relation_changed_then_management_url_available_event_not_emitted(  # noqa: E501
        self,
        patch_url_available,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "management_url": "invalid url",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        patch_url_available.assert_not_called()

    def test_given_management_url_in_relation_data_when_get_management_url_then_address_is_returned(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "management_url": "http://1.2.3.4:1234",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        management_url = self.harness.charm.sdcore_management_requirer.management_url
        self.assertEqual(management_url, "http://1.2.3.4:1234")

    def test_given_management_url_changed_in_relation_data_when_get_management_url_then_new_address_is_returned(  # noqa: E501
        self,
    ):
        relation_id = self._create_relation(remote_app_name=self.remote_app_name)

        relation_data = {
            "management_url": "http://1.2.3.4:1234",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        relation_data = {
            "management_url": "http://different.endpoint:1234",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=self.remote_app_name, key_values=relation_data
        )
        management_url = self.harness.charm.sdcore_management_requirer.management_url
        self.assertEqual(management_url, "http://different.endpoint:1234")
