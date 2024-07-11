# SD-Core Webui Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-webui-k8s/badge.svg)](https://charmhub.io/sdcore-webui-k8s)

A Charmed Operator for SD-Core's Webui component for K8s, a configuration service in SD-Core. 

## Usage

```bash
juju deploy traefik-k8s --trust --config external_hostname=<your hostname> --config routing_mode=subdomain
juju deploy sdcore-upf-k8s --channel=1.5/edge --trust
juju deploy sdcore-gnbsim-k8s --trust --channel=1.5/edge
juju deploy mongodb-k8s --trust --channel=6/beta
juju deploy sdcore-webui-k8s --trust --channel=1.5/edge
juju integrate mongodb-k8s sdcore-webui-k8s:common_database
juju integrate mongodb-k8s sdcore-webui-k8s:auth_database
juju integrate sdcore-webui-k8s:ingress traefik-k8s:ingress
juju integrate sdcore-webui-k8s:fiveg_n4 sdcore-upf-k8s:fiveg_n4
juju integrate sdcore-webui-k8s:fiveg_gnb_identity sdcore-gnbsim-k8s:fiveg_gnb_identity
```

You should now be able to access the NMS at `https://<model name>-sdcore-nms-k8s.<your hostname>`

## Image

- **webui**: `ghcr.io/canonical/sdcore-webui:1.4.1`

