# SD-Core Webui Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-webui-k8s/badge.svg)](https://charmhub.io/sdcore-webui-k8s)

A Charmed Operator for SD-Core's Webui component for K8s, a configuration service in SD-Core. 

## Usage

```bash
juju deploy mongodb-k8s --trust --channel=5/edge
juju deploy sdcore-webui-k8s --channel=edge
juju integrate mongodb-k8s sdcore-webui-k8s
```

## Image

- **webui**: `ghcr.io/canonical/sdcore-webui:1.3`

