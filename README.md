# SD-Core Webui Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-webui-k8s/badge.svg)](https://charmhub.io/sdcore-webui-k8s)

A Charmed Operator for SD-Core's Webui component for K8s, a configuration service in SD-Core. 

## Usage

```bash
juju deploy mongodb-k8s --trust --channel=6/beta
juju deploy sdcore-webui-k8s --trust --channel=1.4/edge
juju integrate mongodb-k8s sdcore-webui-k8s:common_database
juju integrate mongodb-k8s sdcore-webui-k8s:auth_database
```

## Image

- **webui**: `ghcr.io/canonical/sdcore-webui:1.4.0`

