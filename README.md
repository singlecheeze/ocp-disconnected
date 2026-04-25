# OpenShift Disconnected Mirroring Tool (With Auto-Installer)

This repository contains a Python script to automate the mirroring process for a Red Hat OpenShift 4.x disconnected (offline) installation. 

## Key Features
* **Pull Secret Formatting & Base64 Auth Injection**: Automatically maps your pull secret to your Podman directory. It then generates a base64 string of the local mirror registry credentials and dynamically injects them into the `auths` block of the `auth.json` file.
* **Auto-Install Podman**: Automatically checks for and installs Podman via `dnf` if it is not present on the system.
* **Auto-Downloading of Tools**: Fetches `oc` and `oc-mirror` automatically if they are missing from your `$PATH`.
* **Automatic Registry Configuration**: If `oc-mirror` is not found, the script downloads and installs Red Hat's official `mirror-registry` (a lightweight Quay instance).
* **Firewall Configuration**: Automatically configures `firewalld` to allow inbound traffic on the designated registry port.
* **v2 Engine**: Defaults to using the `--v2` flag when executing `oc-mirror` and conforms to the `v2alpha1` API format.
* **Local Workspace & Caching**: Explicitly defines the mirror workspace (`workspace`) and cache (`cache`) directories within the current working path.

## Prerequisites

1. **Internet Access**: Your bastion host needs internet access to `mirror.openshift.com` if tools need to be downloaded, and standard RHEL repo access if Podman needs to be installed via `dnf`.
2. **Sudo Privileges**: Required to install Podman, configure the local mirror registry, and manage system firewalls (`firewalld`).
3. **Red Hat Pull Secret:** You must have your Red Hat pull secret (from console.redhat.com) stored locally. By default, the script looks for it at `./pull-secret.txt`.

## Usage

1. Make the script executable:
   ```bash
   chmod +x mirror_ocp.py
   ```

2. Run the script by passing your intended internal registry endpoint. Place your `pull-secret.txt` file in the same directory.
   ```bash
   ./mirror_ocp.py --registry my-registry.localdomain:8443
   ```

### Optional Arguments
* `--pull-secret`: Specify a custom path to your pull secret (default: `./pull-secret.txt`).
* `--version`: Target OpenShift version (default: `4.21`).
* `--channel`: Override the release channel (default: `stable-4.21`).
* `--config-file`: Specify a custom name for the generated configuration file (default: `imageset-config.yaml`).
