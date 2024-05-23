# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from unittest.mock import call, patch

import pytest
from ops import BoundEvent, testing
from ops.charm import CharmBase

from lib.charms.sdcore_webui_k8s.v0.sdcore_management import (
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

CHARM_LIB_PATH = "lib.charms.sdcore_webui_k8s.v0.sdcore_management"
NAMESPACE = "some_namespace"
MANAGEMENT_URL = "http://1.2.3.4:1234"
RELATION_NAME = "sdcore-management"
REMOTE_APP_NAME = "dummy-sdcore-management-provider"

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


class TestSdcoreManagementRequirer:

    patcher_management_url_available = patch(
        f"{CHARM_LIB_PATH}.SdcoreManagementRequirerCharmEvents.management_url_available",
    )

    @pytest.fixture()
    def setUp(self):
        self.mock_management_url_available = TestSdcoreManagementRequirer.patcher_management_url_available.start()  # noqa: E501
        self.mock_management_url_available.__class__ = BoundEvent

    def tearDown(self) -> None:
        patch.stopall()

    @pytest.fixture(autouse=True)
    def harness(self, setUp, request):
        self.harness = testing.Harness(DummySdcoreManagementRequires, meta=METADATA)
        self.harness.set_model_name(name=NAMESPACE)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()
        yield self.harness
        self.harness.cleanup()
        request.addfinalizer(self.tearDown)

    def create_sdcore_management_relation(self):
        relation_id = self.harness.add_relation(
            relation_name=RELATION_NAME, remote_app=REMOTE_APP_NAME
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{REMOTE_APP_NAME}/0"
        )

        return relation_id

    def test_given_management_url_in_relation_data_when_relation_changed_then_management_url_available_event_emitted(  # noqa: E501
        self
    ):
        relation_id = self.create_sdcore_management_relation()
        relation_data = {
            "management_url": MANAGEMENT_URL,
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )
        calls = [
            call.emit(
                management_url=MANAGEMENT_URL,
            ),
        ]
        self.mock_management_url_available.assert_has_calls(calls, any_order=True)

    def test_given_management_url_not_in_relation_data_when_relation_changed_then_management_url_available_event_not_emitted(  # noqa: E501
        self,
    ):
        relation_id = self.create_sdcore_management_relation()
        relation_data = {}
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )

        self.mock_management_url_available.assert_not_called()

    def test_given_management_url_not_valid_in_relation_data_when_relation_changed_then_management_url_available_event_not_emitted(  # noqa: E501
        self
    ):
        relation_id = self.create_sdcore_management_relation()
        relation_data = {
            "management_url": "invalid url",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )

        self.mock_management_url_available.assert_not_called()

    def test_given_management_url_in_relation_data_when_get_management_url_then_address_is_returned(  # noqa: E501
        self,
    ):
        relation_id = self.create_sdcore_management_relation()
        relation_data = {
            "management_url": MANAGEMENT_URL,
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )

        management_url = self.harness.charm.sdcore_management_requirer.management_url
        assert management_url == MANAGEMENT_URL

    def test_given_management_url_changed_in_relation_data_when_get_management_url_then_new_address_is_returned(  # noqa: E501
        self,
    ):
        relation_id = self.create_sdcore_management_relation()
        relation_data = {
            "management_url": MANAGEMENT_URL,
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )
        relation_data = {
            "management_url": "http://different.endpoint:1234",
        }
        self.harness.update_relation_data(
            relation_id=relation_id, app_or_unit=REMOTE_APP_NAME, key_values=relation_data
        )

        management_url = self.harness.charm.sdcore_management_requirer.management_url
        assert management_url == "http://different.endpoint:1234"
