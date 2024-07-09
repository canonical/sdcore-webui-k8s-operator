#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from collections import Counter
from pathlib import Path

import pytest
import yaml
from juju.application import Application
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
DATABASE_APP_NAME = "mongodb-k8s"
DATABASE_APP_CHANNEL = "6/beta"
COMMON_DATABASE_RELATION_NAME = "common_database"
AUTH_DATABASE_RELATION_NAME = "auth_database"
LOGGING_RELATION_NAME = "logging"
GNBSIM_CHARM_NAME = "sdcore-gnbsim-k8s"
GNBSIM_CHARM_CHANNEL = "1.5/edge"
GNBSIM_RELATION_NAME = "fiveg_gnb_identity"
GRAFANA_AGENT_APP_NAME = "grafana-agent-k8s"
GRAFANA_AGENT_APP_CHANNEL = "latest/stable"
UPF_CHARM_NAME = "sdcore-upf-k8s"
UPF_CHARM_CHANNEL = "1.5/edge"
UPF_RELATION_NAME = "fiveg_n4"
TRAEFIK_CHARM_NAME = "traefik-k8s"
TRAEFIK_CHARM_CHANNEL = "latest/stable"


async def _deploy_database(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(
        DATABASE_APP_NAME,
        application_name=DATABASE_APP_NAME,
        channel=DATABASE_APP_CHANNEL,
        trust=True,
    )


async def _deploy_grafana_agent(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(
        GRAFANA_AGENT_APP_NAME,
        application_name=GRAFANA_AGENT_APP_NAME,
        channel=GRAFANA_AGENT_APP_CHANNEL,
    )

async def _deploy_traefik(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(
        TRAEFIK_CHARM_NAME,
        application_name=TRAEFIK_CHARM_NAME,
        config={"external_hostname": "pizza.com", "routing_mode": "subdomain"},
        channel=TRAEFIK_CHARM_CHANNEL,
        trust=True,
    )

async def _deploy_sdcore_upf(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(
        UPF_CHARM_NAME,
        application_name=UPF_CHARM_NAME,
        channel=UPF_CHARM_CHANNEL,
        trust=True,
    )

async def _deploy_sdcore_gnbsim(ops_test: OpsTest):
    assert ops_test.model
    await ops_test.model.deploy(
        GNBSIM_CHARM_NAME,
        application_name=GNBSIM_CHARM_NAME,
        channel=GNBSIM_CHARM_CHANNEL,
        trust=True,
    )

@pytest.fixture(scope="module")
@pytest.mark.abort_on_fail
async def deploy(ops_test: OpsTest, request):
    """Deploy required components."""
    charm = Path(request.config.getoption("--charm_path")).resolve()
    resources = {
        "webui-image": METADATA["resources"]["webui-image"]["upstream-source"],
    }
    assert ops_test.model
    await ops_test.model.deploy(
        charm,
        resources=resources,
        application_name=APP_NAME,
        trust=True,
    )
    await _deploy_database(ops_test)
    await _deploy_grafana_agent(ops_test)
    await _deploy_traefik(ops_test)
    await _deploy_sdcore_upf(ops_test)
    await _deploy_sdcore_gnbsim(ops_test)

@pytest.mark.abort_on_fail
async def test_given_charm_is_built_when_deployed_then_status_is_blocked(
    ops_test: OpsTest, deploy
):
    assert ops_test.model
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="blocked",
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_relate_and_wait_for_active_status(ops_test: OpsTest, deploy):
    assert ops_test.model
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{COMMON_DATABASE_RELATION_NAME}", relation2=f"{DATABASE_APP_NAME}"
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{AUTH_DATABASE_RELATION_NAME}", relation2=f"{DATABASE_APP_NAME}"
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{LOGGING_RELATION_NAME}", relation2=GRAFANA_AGENT_APP_NAME
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{GNBSIM_RELATION_NAME}", relation2=GNBSIM_CHARM_NAME
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{UPF_RELATION_NAME}", relation2=UPF_CHARM_NAME
    )
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=1000,
    )


@pytest.mark.skip(
    reason="Bug in MongoDB: https://github.com/canonical/mongodb-k8s-operator/issues/218"
)
@pytest.mark.abort_on_fail
async def test_remove_database_and_wait_for_blocked_status(ops_test: OpsTest, deploy):
    assert ops_test.model
    await ops_test.model.remove_application(DATABASE_APP_NAME, block_until_done=True)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", timeout=60)


@pytest.mark.skip(
    reason="Bug in MongoDB: https://github.com/canonical/mongodb-k8s-operator/issues/218"
)
@pytest.mark.abort_on_fail
async def test_restore_database_and_wait_for_active_status(ops_test: OpsTest, deploy):
    assert ops_test.model
    await _deploy_database(ops_test)
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{COMMON_DATABASE_RELATION_NAME}", relation2=DATABASE_APP_NAME
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:{AUTH_DATABASE_RELATION_NAME}", relation2=DATABASE_APP_NAME
    )
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)


@pytest.mark.abort_on_fail
async def test_when_scale_app_beyond_1_then_only_one_unit_is_active(
    ops_test: OpsTest, deploy
):
    assert ops_test.model
    assert isinstance(app := ops_test.model.applications[APP_NAME], Application)
    await app.scale(3)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], timeout=1000, wait_for_at_least_units=3)
    unit_statuses = Counter(unit.workload_status for unit in app.units)
    assert unit_statuses.get("active") == 1
    assert unit_statuses.get("blocked") == 2


async def test_remove_app(ops_test: OpsTest, deploy):
    assert ops_test.model
    await ops_test.model.remove_application(APP_NAME, block_until_done=True)
