# OpenShift Disconnected Mirroring Tool (With Auto-Installer)

This repository contains a Python script to automate the mirroring process for a Red Hat OpenShift 4.x disconnected (offline) installation using the `oc-mirror` plugin. 

## What's New
* **Auto-Downloading of Prerequisites**: If the `oc` and `oc-mirror` CLI tools are not found in your system's `$PATH`, the script will automatically reach out to the Red Hat OpenShift mirrors, download the binaries for your specified version, extract them into a local `./bin` directory, and temporarily add them to the execution `$PATH`.

## Prerequisites Before Running

1. **Internet Access (If Auto-Downloading):** Your bastion host needs access to `mirror.openshift.com` if it needs to download the `oc` and `oc-mirror` tools.
2. **Authentication:** Your `~/.docker/config.json` (or `${XDG_RUNTIME_DIR}/containers/auth.json` for Podman) must contain combined authentication for:
   * `quay.io` and `registry.redhat.io` (your Red Hat pull secret).
   * Your internal RHEL mirror registry.
3. **Local Registry:** A container registry must be running and accessible on your target RHEL server.

## Usage

1. Make the script executable:
   ```bash
   chmod +x mirror_ocp.py
   ```

2. Run the script by passing your internal registry endpoint:
   ```bash
   ./mirror_ocp.py --registry my-rhel-registry.internal.lan:5000
   ```

### Optional Arguments
* `--version`: Target OpenShift version. Also used to dynamically fetch the correct `oc` and `oc-mirror` tool versions if they are missing (default: `4.21`).
* `--channel`: Override the release channel (default: `stable-4.21`).
* `--config-file`: Specify a custom name for the generated configuration file (default: `imageset-config.yaml`).

## Next Steps Post-Mirroring
After a successful run, apply the generated configurations to your OpenShift cluster:
```bash
oc apply -f ./oc-mirror-workspace/results-*/release-signatures/
oc apply -f ./oc-mirror-workspace/results-*/imageContentSourcePolicy.yaml
```