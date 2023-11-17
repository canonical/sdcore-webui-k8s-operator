# SD-Core Webui Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-webui/badge.svg)](https://charmhub.io/sdcore-webui)

A Charmed Operator for SD-Core's Webui component, a configuration service in SD-Core. 

## Usage

```bash
juju deploy mongodb-k8s --trust --channel=5/edge
juju deploy sdcore-webui --trust --channel=edge
juju integrate mongodb-k8s sdcore-webui
```

## Image

- **webui**: `ghcr.io/canonical/sdcore-webui:1.3`
