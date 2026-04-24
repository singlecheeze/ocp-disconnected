# OpenShift Disconnected Mirroring Tool (With Local Registry Auto-Installer)

This repository contains a Python script to automate the mirroring process for a Red Hat OpenShift 4.x disconnected (offline) installation. 

## Key Features
* **Auto-Downloading of Tools**: Fetches `oc` and `oc-mirror` automatically if they are missing from your `$PATH`.
* **Automatic Registry Configuration**: If `oc-mirror` is not found (implying a fresh setup), the script will automatically download and install Red Hat's official `mirror-registry` (a lightweight Quay instance), as is standard for disconnected setups described in Red Hat blogs and documentation. 

## Prerequisites

1. **Internet Access**: Your bastion host needs internet access to `mirror.openshift.com` if tools/registry need to be downloaded.
2. **Sudo Privileges**: If the local mirror registry needs to be set up, the script requires `sudo` privileges to configure Podman, firewall rules, and systemd via the `mirror-registry` installer.
3. **Authentication:** Your `~/.docker/config.json` (or `${XDG_RUNTIME_DIR}/containers/auth.json`) must contain your Red Hat pull secret from console.redhat.com.

## Usage

1. Make the script executable:
   ```bash
   chmod +x mirror_ocp.py
   ```

2. Run the script by passing your intended internal registry endpoint. If using the auto-installed mirror registry, the default port is `8443`.
   ```bash
   ./mirror_ocp.py --registry my-rhel-registry.internal.lan:8443
   ```

### Default Credentials for Auto-Installed Registry
If the script automatically installs the `mirror-registry`, it will initialize it with:
* **Username**: `admin`
* **Password**: `RedHat123!`

**Important:** Before the mirroring begins, make sure you add these credentials to your podman/docker authentication file:
```bash
podman login my-rhel-registry.internal.lan:8443 -u admin -p RedHat123!
```

### Optional Arguments
* `--version`: Target OpenShift version (default: `4.21`).
* `--channel`: Override the release channel (default: `stable-4.21`).
* `--config-file`: Specify a custom name for the generated configuration file (default: `imageset-config.yaml`).
