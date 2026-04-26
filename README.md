# OpenShift Disconnected Mirroring Tool (With Auto-Installer)

This repository contains a Python script to automate the mirroring process for a Red Hat OpenShift 4.x disconnected (offline) installation. 

## Key Features
* **External Config Templates**: Automatically loads the mirror configuration from an external `imageset-config-template.yaml` file, substituting dynamic versioning and channel paths. This allows easy external customization.
* **Dynamic Target Registry**: Automatically detects the fully qualified domain name (FQDN) of the system it is running on to set up and target the mirror registry seamlessly.
* **Pull Secret Formatting & Base64 Auth Injection**: Automatically maps your pull secret to your Podman directory. It then generates a base64 string of the local mirror registry credentials and dynamically injects them into the `auths` block of the `auth.json` file.
* **Auto-Install Podman**: Automatically checks for and installs Podman via `dnf` if it is not present on the system.
* **Auto-Downloading of Tools**: Fetches `oc` and `oc-mirror` automatically if they are missing from your `$PATH`.
* **Automatic Registry Configuration**: If `oc-mirror` is not found, the script downloads and installs Red Hat's official `mirror-registry` (a lightweight Quay instance). The registry data is placed directly in the `mirror` directory alongside the script for easy management.
* **Trust Store Configuration**: After registry installation, the tool automatically imports the new Quay root CA certificate (`rootCA.pem`) into the system's trust anchors (`/etc/pki/ca-trust/source/anchors/`) and updates the system's CA trust list to securely route without ignoring TLS.
* **Firewall Configuration**: Automatically configures `firewalld` to allow inbound traffic on the designated registry port.
* **v2 Engine**: Defaults to using the `--v2` flag when executing `oc-mirror` and conforms to the `v2alpha1` API format.
* **Optimized Syncing**: Implements `--parallel-images=10` and `--parallel-layers=10` for faster download and extraction concurrency.
* **Real-time Terminal Output**: The script is optimized with `ANSIBLE_FORCE_COLOR=1` and an unbuffered `PYTHONUNBUFFERED=1` character-by-character stdout stream for rich, responsive real-time feedback during underlying playbook or command execution.
* **Local Workspace**: Explicitly defines the mirror workspace directory using absolute `file://` URIs within the current working path.

## Prerequisites

1. **Internet Access**: Your bastion host needs internet access to `mirror.openshift.com` if tools need to be downloaded, and standard RHEL repo access if Podman needs to be installed via `dnf`.
2. **Sudo Privileges**: Required to install Podman, configure the local mirror registry, and manage system firewalls (`firewalld`). The script will prompt you for this password upon execution.
3. **Red Hat Pull Secret:** You must have your Red Hat pull secret stored locally. **You can download it from the bottom of the console found at this link: [https://console.redhat.com/openshift/downloads](https://console.redhat.com/openshift/downloads).** By default, the script looks for it at `./pull-secret.txt`.

## Usage

1. Make the script executable:
   ```bash
   chmod +x mirror_ocp.py
   ```

2. Ensure the `imageset-config-template.yaml` and `pull-secret.txt` files are located in the same directory as the script.

3. Run the script. By default, it will detect your system's hostname and use port 8443 for the registry. 
   ```bash
   ./mirror_ocp.py
   ```

### Optional Arguments
* `--registry`: Override the target mirror registry (default: `<system-fqdn>:8443`).
* `--template-file`: Specify the path to the template yaml (default: `imageset-config-template.yaml`).
* `--pull-secret`: Specify a custom path to your pull secret (default: `./pull-secret.txt`).
* `--version`: Target OpenShift version (default: `4.21`).
* `--channel`: Override the release channel (default: `stable-4.21`).
* `--config-file`: Specify a custom name for the generated runtime configuration file (default: `imageset-config.yaml`).

## Acknowledgments
A special note of thanks: this blog post was very helpful in developing this tool: [https://myopenshiftblog.com/disconnected-registry-mirroring/](https://myopenshiftblog.com/disconnected-registry-mirroring/)
