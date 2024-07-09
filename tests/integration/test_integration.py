#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import time
from collections import Counter
from pathlib import Path

import pytest
import requests  # type: ignore[import]
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

async def get_sdcore_nms_endpoint(ops_test: OpsTest) -> str:
    """Retrieve the SD-Core NMS endpoint by using Traefik's `show-proxied-endpoints` action."""
    assert ops_test.model
    traefik = ops_test.model.applications[TRAEFIK_CHARM_NAME]
    traefik_unit = traefik.units[0]
    t0 = time.time()
    timeout = 30  # seconds
    while time.time() - t0 < timeout:
        proxied_endpoint_action = await traefik_unit.run_action(
            action_name="show-proxied-endpoints"
        )
        action_output = await ops_test.model.get_action_output(
            action_uuid=proxied_endpoint_action.entity_id, wait=30
        )

        if "proxied-endpoints" in action_output:
            proxied_endpoints = json.loads(action_output["proxied-endpoints"])
            return proxied_endpoints[APP_NAME]["url"]
        else:
            logger.info("Traefik did not return proxied endpoints yet")
        time.sleep(2)

    raise TimeoutError("Traefik did not return proxied endpoints")


async def get_traefik_ip(ops_test: OpsTest) -> str:
    """Retrieve the IP of the Traefik Application."""
    assert ops_test.model
    app_status = await ops_test.model.get_status(filters=[TRAEFIK_CHARM_NAME])
    return app_status.applications[TRAEFIK_CHARM_NAME].public_address


def _get_host_from_url(url: str) -> str:
    """Return the host from a URL formatted as http://<host>:<port>/ or as http://<host>/."""
    return url.split("//")[1].split(":")[0].split("/")[0]


def ui_is_running(ip: str, host: str) -> bool:
    """Return whether the UI is running."""
    #url = f"http://{ip}/network-configuration"
    url = f"http://{ip}/config/v1/network-slice"
    headers = {"Host": host}
    t0 = time.time()
    timeout = 300  # seconds
    while time.time() - t0 < timeout:
        try:
            response = requests.get(url=url, headers=headers, timeout=5)
            response.raise_for_status()
            if "5G NMS" in response.content.decode("utf-8"):
                return True
        except Exception as e:
            logger.info(f"UI is not running yet: {e}")
        time.sleep(2)
    return False

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
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:ingress", relation2=f"{TRAEFIK_CHARM_NAME}:ingress"
    )
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TRAEFIK_CHARM_NAME],
        status="active",
        timeout=500,
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
async def test_given_related_to_traefik_when_fetch_ui_then_returns_html_content(
    ops_test: OpsTest, deploy
):
    nms_url = await get_sdcore_nms_endpoint(ops_test)
    traefik_ip = await get_traefik_ip(ops_test)
    nms_host = _get_host_from_url(nms_url)
    assert ui_is_running(ip=traefik_ip, host=nms_host)


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
