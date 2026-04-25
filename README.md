# OpenShift Disconnected Mirroring Tool (With Auto-Installer)

This repository contains a Python script to automate the mirroring process for a Red Hat OpenShift 4.x disconnected (offline) installation. 

## Key Features
* **Auto-Install Podman**: Automatically checks for and installs Podman via `dnf` if it is not present on the system.
* **Auto-Downloading of Tools**: Fetches `oc` and `oc-mirror` automatically if they are missing from your `$PATH`.
* **Automatic Registry Configuration**: If `oc-mirror` is not found, the script downloads and installs Red Hat's official `mirror-registry` (a lightweight Quay instance).
* **Automatic Authentication**: Automatically runs `podman login` to authenticate against the newly created local mirror registry.

## Prerequisites

1. **Internet Access**: Your bastion host needs internet access to `mirror.openshift.com` if tools need to be downloaded, and standard RHEL repo access if Podman needs to be installed via `dnf`.
2. **Sudo Privileges**: Required to install Podman (if missing) and configure the local mirror registry (which configures systemd and firewall rules).
3. **Red Hat Pull Secret:** You must have your Red Hat pull secret (from console.redhat.com) stored locally. You can log into the Red Hat registries prior to running the script using:
   ```bash
   podman login registry.redhat.io
   podman login quay.io
   ```

## Usage

1. Make the script executable:
   ```bash
   chmod +x mirror_ocp.py
   ```

2. Run the script by passing your intended internal registry endpoint:
   ```bash
   ./mirror_ocp.py --registry my-registry.localdomain:8443
   ```

### Default Credentials for Auto-Installed Registry
If the script automatically installs the `mirror-registry`, it will initialize it with `admin` / `RedHat123!` and **automatically authenticate** your user via Podman.

### Optional Arguments
* `--version`: Target OpenShift version (default: `4.21`).
* `--channel`: Override the release channel (default: `stable-4.21`).
* `--config-file`: Specify a custom name for the generated configuration file (default: `imageset-config.yaml`).
