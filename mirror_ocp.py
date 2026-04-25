#!/usr/bin/env python3

import subprocess
import sys
import os
import argparse
import textwrap
import urllib.request
import tarfile
import urllib.error


def run_command(command, error_message):
    """Executes a shell command and streams the output."""
    print(f"\n[INFO] Running: {' '.join(command)}")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in process.stdout:
            print(line, end='')
        process.wait()

        if process.returncode != 0:
            print(f"\n[ERROR] {error_message}")
            sys.exit(process.returncode)
    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {e}")
        sys.exit(1)


def download_and_extract(url, dest_dir):
    """Downloads a tar.gz file and extracts it to the destination directory."""
    file_name = url.split('/')[-1]
    file_path = os.path.join(dest_dir, file_name)
    print(f"[INFO] Downloading {url} ...")
    try:
        urllib.request.urlretrieve(url, file_path)
    except urllib.error.URLError as e:
        print(f"[ERROR] Failed to download from {url}: {e}")
        raise

    print(f"[INFO] Extracting {file_name} ...")
    with tarfile.open(file_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)
    os.remove(file_path)


def ensure_podman():
    """Checks if Podman is installed, and installs it via dnf if not."""
    if subprocess.run(['which', 'podman'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        print("[INFO] Podman is already installed.")
        return

    print("[WARNING] Podman not found. Attempting to install via dnf...")
    install_cmd = ["sudo", "dnf", "install", "-y", "podman"]
    run_command(install_cmd,
                "Failed to install Podman. Ensure you have sudo privileges and an active RHEL subscription/repo.")
    print("[SUCCESS] Podman installed successfully.")


def ensure_tools(version):
    """Checks for oc and oc-mirror. If missing, downloads them and returns True (meaning missing)."""
    tools = ['oc', 'oc-mirror']
    tools_missing = False

    for tool in tools:
        if subprocess.run(['which', tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            tools_missing = True
            break

    if not tools_missing:
        print("[INFO] All prerequisite tools ('oc', 'oc-mirror') found in PATH.")
        return False

    print("[WARNING] Prerequisites not found in PATH. Downloading them locally...")
    bin_dir = os.path.join(os.getcwd(), "bin")
    os.makedirs(bin_dir, exist_ok=True)

    base_url = f"https://mirror.openshift.com/pub/openshift-v4/clients/ocp/latest-{version}"

    try:
        if not os.path.exists(os.path.join(bin_dir, "oc")):
            download_and_extract(f"{base_url}/openshift-client-linux.tar.gz", bin_dir)

        if not os.path.exists(os.path.join(bin_dir, "oc-mirror")):
            try:
                download_and_extract(f"{base_url}/oc-mirror.tar.gz", bin_dir)
            except urllib.error.URLError:
                download_and_extract(f"{base_url}/oc-mirror-linux.tar.gz", bin_dir)

    except Exception as e:
        print(f"[ERROR] Could not automatically download tools. Details: {e}")
        sys.exit(1)

    for tool in tools:
        tool_path = os.path.join(bin_dir, tool)
        if os.path.exists(tool_path):
            os.chmod(tool_path, 0o755)

    os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
    print(f"[INFO] Added {bin_dir} to PATH for this session.")
    return True


def setup_local_mirror_registry(registry_fqdn):
    """Installs Red Hat's official mirror-registry tool and authenticates podman."""
    print("\n=========================================================")
    print("[INFO] Setting up Local Mirror Registry (Quay)...")
    print("=========================================================")

    bin_dir = os.path.join(os.getcwd(), "bin")
    mirror_registry_url = "https://mirror.openshift.com/pub/openshift-v4/clients/mirror-registry/latest/mirror-registry.tar.gz"

    if not os.path.exists(os.path.join(bin_dir, "mirror-registry")):
        try:
            download_and_extract(mirror_registry_url, bin_dir)
        except Exception as e:
            print(f"[ERROR] Failed to download mirror-registry tool: {e}")
            sys.exit(1)

    # Extract hostname from registry string
    hostname = registry_fqdn.split(':')[0]
    port = registry_fqdn.split(':')[1] if ':' in registry_fqdn else '8443'
    registry_url = f"{hostname}:{port}"

    admin_user = "admin"
    admin_pass = "RedHat123!"

    install_cmd = [
        "sudo", os.path.join(bin_dir, "mirror-registry"),
        "install",
        "--quayHostname", hostname,
        "--initUser", admin_user,
        "--initPassword", admin_pass
    ]

    print("[INFO] Running mirror-registry installer. (Note: this requires sudo privileges)")
    run_command(install_cmd, "Failed to install the local mirror registry.")
    print("[SUCCESS] Local Mirror Registry (Quay) is successfully configured!")

    print(f"\n[INFO] Authenticating podman to {registry_url}...")
    login_cmd = [
        "podman", "login", registry_url,
        "-u", admin_user,
        "-p", admin_pass,
        "--tls-verify=false"  # Needed for self-signed certs generated by mirror-registry
    ]
    run_command(login_cmd, f"Failed to authenticate Podman against {registry_url}")
    print("[SUCCESS] Successfully logged into local mirror registry.")


def generate_imageset_config(version, channel, config_path):
    """Generates the ImageSetConfiguration YAML file."""
    config_content = textwrap.dedent(f"""\
        kind: ImageSetConfiguration
        apiVersion: mirror.openshift.io/v1alpha2
        storageConfig:
          local:
            path: ./oc-mirror-workspace
        mirror:
          platform:
            channels:
            - name: {channel}
              type: ocp
          operators:
          - catalog: registry.redhat.io/redhat/redhat-operator-index:v{version}
            packages:
            - name: local-storage-operator
            - name: openshift-gitops-operator
            - name: advanced-cluster-management
          additionalImages:
          - name: registry.redhat.io/ubi8/ubi:latest
    """)

    try:
        with open(config_path, 'w') as f:
            f.write(config_content)
        print(f"\n[INFO] Generated ImageSetConfiguration at {config_path}")
    except IOError as e:
        print(f"[ERROR] Failed to write config file: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Automate OCP Mirroring & Local Registry Setup.")
    parser.add_argument("--registry", required=True, help="Target mirror registry (e.g., my-registry.localdomain:8443)")
    parser.add_argument("--version", default="4.21", help="OpenShift major.minor version (default: 4.21)")
    parser.add_argument("--channel", default="stable-4.21", help="OpenShift release channel (default: stable-4.21)")
    parser.add_argument("--config-file", default="imageset-config.yaml", help="Path to generate the config file")

    args = parser.parse_args()

    print("=========================================================")
    print("      OpenShift Disconnected Mirroring Automation        ")
    print("=========================================================")
    print(f"Target Registry: {args.registry}")
    print(f"OCP Version:     {args.version}")
    print("=========================================================\n")

    # 0. Ensure Podman is installed (Required for mirror-registry and auth)
    ensure_podman()

    # 1. Download/Verify Tools (oc, oc-mirror)
    tools_were_missing = ensure_tools(args.version)

    # 2. Configure Local Mirror Registry if tools were missing
    if tools_were_missing:
        print("[INFO] 'oc-mirror' was missing. Assuming fresh setup. Configuring local mirror registry...")
        setup_local_mirror_registry(args.registry)
        # We need to tell oc-mirror to not verify TLS if we just stood up a self-signed registry
        os.environ["REGISTRY_AUTH_PREFERENCE"] = "podman"
        mirror_tls_flag = "--dest-skip-tls"
    else:
        mirror_tls_flag = ""

    # 3. Check Auth File (Podman auth file location)
    auth_file = os.path.expanduser('~/.docker/config.json')
    podman_auth_file = os.path.expanduser(f"/run/user/{os.getuid()}/containers/auth.json")

    if os.environ.get('REGISTRY_AUTH_FILE'):
        auth_file = os.environ.get('REGISTRY_AUTH_FILE')
    elif os.path.exists(podman_auth_file):
        auth_file = podman_auth_file

    if not os.path.exists(auth_file):
        print(
            f"\n[WARNING] Auth file not found at {auth_file}. Ensure you are authenticated to registry.redhat.io / quay.io.")
    else:
        print(f"\n[INFO] Using container auth file: {auth_file}")

    # 4. Build Config
    generate_imageset_config(args.version, args.channel, args.config_file)

    # 5. Execute Mirror
    # We append the tls flag if we just built the registry self-signed
    mirror_cmd = [
        "oc-mirror",
        "--config", args.config_file,
        f"docker://{args.registry}"
    ]

    if mirror_tls_flag:
        mirror_cmd.insert(1, mirror_tls_flag)

    print("\n[INFO] Starting mirror synchronization...")
    run_command(mirror_cmd, "oc-mirror process failed. Verify your Red Hat pull secret and storage capacity.")

    print("\n=========================================================")
    print("[SUCCESS] Process completed successfully!")
    print("=========================================================")


if __name__ == "__main__":
    main()
