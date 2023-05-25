<div align="center">
  <img src="./icon.svg" alt="ONF Icon" width="200" height="200">
</div>
<br/>
<div align="center">
  <a href="https://charmhub.io/sdcore-webui"><img src="https://charmhub.io/sdcore-webui/badge.svg" alt="CharmHub Badge"></a>
  <a href="https://github.com/canonical/sdcore-webui-operator/actions/workflows/publish-charm.yaml">
    <img src="https://github.com/canonical/sdcore-webui-operator/actions/workflows/publish-charm.yaml/badge.svg?branch=main" alt=".github/workflows/publish-charm.yaml">
  </a>
  <br/>
  <br/>
  <h1>SD-Core Webui Operator</h1>
</div>

A Charmed Operator for SD-Core's Webui component, a configuration service in SD-Core. 

## Usage

```bash
juju deploy mongodb-k8s --trust --channel=5/edge
juju deploy sdcore-webui --trust --channel=edge
juju integrate mongodb-k8s sdcore-webui
```

## Image

- **webui**: `omecproject/5gc-webui:master-1121545`
