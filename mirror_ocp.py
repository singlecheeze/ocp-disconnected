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
        print("[ERROR] Ensure you have internet access or pre-install the tools manually.")
        raise

    print(f"[INFO] Extracting {file_name} ...")
    with tarfile.open(file_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)
    os.remove(file_path)


def ensure_tools(version):
    """Checks for oc and oc-mirror in PATH. If missing, downloads and installs them locally."""
    tools = ['oc', 'oc-mirror']
    tools_missing = False

    for tool in tools:
        if subprocess.run(['which', tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            tools_missing = True
            break

    if not tools_missing:
        print("[INFO] All prerequisite tools ('oc', 'oc-mirror') found in PATH.")
        return

    print("[WARNING] Prerequisites not found in PATH. Attempting to download them locally...")
    bin_dir = os.path.join(os.getcwd(), "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # Check if they exist in our local ./bin directory first
    if os.path.exists(os.path.join(bin_dir, "oc")) and os.path.exists(os.path.join(bin_dir, "oc-mirror")):
        print(f"[INFO] Tools found in local bin directory: {bin_dir}")
    else:
        base_url = f"https://mirror.openshift.com/pub/openshift-v4/clients/ocp/latest-{version}"

        try:
            # Download OpenShift Client (oc)
            oc_url = f"{base_url}/openshift-client-linux.tar.gz"
            download_and_extract(oc_url, bin_dir)

            # Download oc-mirror plugin
            # Naming convention sometimes fluctuates between oc-mirror.tar.gz and oc-mirror-linux.tar.gz
            oc_mirror_url = f"{base_url}/oc-mirror.tar.gz"
            try:
                download_and_extract(oc_mirror_url, bin_dir)
            except urllib.error.URLError:
                print("[INFO] 'oc-mirror.tar.gz' not found, falling back to 'oc-mirror-linux.tar.gz'...")
                oc_mirror_url = f"{base_url}/oc-mirror-linux.tar.gz"
                download_and_extract(oc_mirror_url, bin_dir)

        except Exception as e:
            print(f"[ERROR] Could not automatically download tools. Please install them manually. Details: {e}")
            sys.exit(1)

        # Ensure executable permissions
        for tool in tools:
            tool_path = os.path.join(bin_dir, tool)
            if os.path.exists(tool_path):
                os.chmod(tool_path, 0o755)

    # Prepend local bin directory to the script's PATH
    os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
    print(f"[INFO] Added {bin_dir} to PATH for this session.")

    # Final verification
    for tool in tools:
        if subprocess.run(['which', tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            print(f"[ERROR] Tool '{tool}' could not be installed/found even after download attempt.")
            sys.exit(1)

    print("[INFO] All prerequisite tools successfully verified.")


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
        print(f"[INFO] Generated ImageSetConfiguration at {config_path}")
    except IOError as e:
        print(f"[ERROR] Failed to write config file: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Automate OCP Mirroring to a target RHEL registry with auto-downloader.")
    parser.add_argument("--registry", required=True, help="Target mirror registry (e.g., registry.internal.com:5000)")
    parser.add_argument("--version", default="4.21", help="OpenShift major.minor version (default: 4.21)")
    parser.add_argument("--channel", default="stable-4.21", help="OpenShift release channel (default: stable-4.21)")
    parser.add_argument("--config-file", default="imageset-config.yaml", help="Path to generate the config file")

    args = parser.parse_args()

    print("=========================================================")
    print("      OpenShift Disconnected Mirroring Script            ")
    print("=========================================================")
    print(f"Target Registry: {args.registry}")
    print(f"OCP Version:     {args.version}")
    print(f"Channel:         {args.channel}")
    print("=========================================================\n")

    # 1. Download/Verify Tools
    ensure_tools(args.version)

    # 2. Check Auth
    auth_file = os.environ.get('REGISTRY_AUTH_FILE', os.path.expanduser('~/.docker/config.json'))
    if not os.path.exists(auth_file):
        print(
            f"[WARNING] Auth file not found at {auth_file}. Ensure you are authenticated to Quay and your local registry.")
    else:
        print(f"[INFO] Using container auth file: {auth_file}")

    # 3. Build Config
    generate_imageset_config(args.version, args.channel, args.config_file)

    # 4. Execute Mirror
    mirror_cmd = [
        "oc-mirror",
        "--config", args.config_file,
        f"docker://{args.registry}"
    ]

    run_command(mirror_cmd,
                "oc-mirror process failed. Check your network connectivity, registry authentication, and storage space.")

    print("\n=========================================================")
    print("[SUCCESS] Mirroring completed successfully!")
    print("=========================================================")


if __name__ == "__main__":
    main()