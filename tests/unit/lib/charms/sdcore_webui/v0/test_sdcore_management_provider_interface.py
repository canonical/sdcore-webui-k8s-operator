# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from unittest.mock import PropertyMock, patch

import pytest
from ops import testing
from ops.charm import CharmBase, RelationJoinedEvent

from lib.charms.sdcore_webui_k8s.v0.sdcore_management import SdcoreManagementProvides

METADATA = """
name: sdcore-management-dummy-provider
description: |
  Dummy charm implementing the provider side of the sdcore_management interface.
summary: |
  Dummy charm implementing the provider side of the sdcore_management interface.
requires:
  sdcore-management:
    interface: sdcore-management
"""

logger = logging.getLogger(__name__)

RELATION_NAME = "sdcore-management"
REMOTE_APP_NAME = "dummy-sdcore-management-requirer"


class DummySdcoreManagementProvides(CharmBase):
    """Dummy charm implementing the provider side of the sdcore_management interface."""

    MANAGEMENT_URL = "http://1.2.3.4:1234"

    def __init__(self, *args):
        super().__init__(*args)
        self.sdcore_management_provider = SdcoreManagementProvides(self, RELATION_NAME)
        self.framework.observe(
            self.on.sdcore_management_relation_joined, self._on_sdcore_management_relation_joined
        )

    def _on_sdcore_management_relation_joined(self, event: RelationJoinedEvent):
        if self.unit.is_leader():
            self.sdcore_management_provider.set_management_url(
                management_url=self.MANAGEMENT_URL,
            )


class TestSdcoreManagementProvider:

    @pytest.fixture(autouse=True)
    def harness(self):
        self.harness = testing.Harness(DummySdcoreManagementProvides, meta=METADATA)
        self.harness.set_model_name(name="some_namespace")
        self.harness.set_leader(is_leader=True)
        self.harness.begin()
        yield self.harness
        self.harness.cleanup()

    def _create_relation(self):
        relation_id = self.harness.add_relation(
            relation_name=RELATION_NAME, remote_app=REMOTE_APP_NAME
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{REMOTE_APP_NAME}/0"
        )
        return relation_id

    def test_given_unit_is_leader_and_data_is_valid_when_sdcore_management_relation_joined_then_data_is_in_application_databag(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)

        relation_id = self._create_relation()
        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.app.name
        )

        assert relation_data["management_url"] == DummySdcoreManagementProvides.MANAGEMENT_URL

    def test_given_unit_is_not_leader_when_sdcore_management_relation_joined_then_data_is_not_in_application_databag(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=False)

        relation_id = self._create_relation()
        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.app.name
        )

        assert relation_data == {}

    def test_given_unit_is_leader_but_address_is_invalid_when_sdcore_management_relation_joined_then_value_error_is_raised(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        with patch.object(
            DummySdcoreManagementProvides, "MANAGEMENT_URL", new_callable=PropertyMock
        ) as patched_address:
            patched_address.return_value = "invalid address"
            with pytest.raises(ValueError):
                self._create_relation()
