#!/usr/bin/env python3

import subprocess
import sys
import os
import argparse
import textwrap
import urllib.request
import tarfile
import urllib.error
import json
import base64

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
            # Replaced carriage returns to prevent output overwriting in the console
            print(line.replace('\r', ''), end='')
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
        try:
            tar.extractall(path=dest_dir, filter='fully_trusted')
        except TypeError:
            print("[WARNING] Python version does not support the 'filter' parameter in tarfile. Falling back to standard extraction.")
            tar.extractall(path=dest_dir)
    os.remove(file_path)

def ensure_podman():
    """Checks if Podman is installed, and installs it via dnf if not."""
    if subprocess.run(['which', 'podman'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        print("[INFO] Podman is already installed.")
        return

    print("[WARNING] Podman not found. Attempting to install via dnf...")
    install_cmd = ["sudo", "dnf", "install", "-y", "podman"]
    run_command(install_cmd, "Failed to install Podman. Ensure you have sudo privileges and an active RHEL subscription/repo.")
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
            oc_mirror_url = "https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/latest/oc-mirror.rhel9.tar.gz"
            try:
                download_and_extract(oc_mirror_url, bin_dir)
            except urllib.error.URLError:
                print("[WARNING] Target oc-mirror URL failed, attempting standard URL...")
                download_and_extract(f"{base_url}/oc-mirror.tar.gz", bin_dir)
                
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

def setup_auth_file(pull_secret_path):
    """Sets up the containers directory and formats the pull secret as auth.json."""
    xdg_runtime = os.environ.get('XDG_RUNTIME_DIR', f"/run/user/{os.getuid()}")
    containers_dir = os.path.join(xdg_runtime, "containers")
    auth_file = os.path.join(containers_dir, "auth.json")

    print(f"\n=========================================================")
    print("[INFO] Configuring Podman Authentication...")
    print("=========================================================")
    print(f"[INFO] Checking for directory: {containers_dir}")
    
    if not os.path.exists(containers_dir):
        print(f"[INFO] Directory does not exist. Creating it (mkdir -p {containers_dir})...")
        os.makedirs(containers_dir, exist_ok=True)
        
    if os.path.exists(pull_secret_path):
        print(f"[INFO] Found pull secret at '{pull_secret_path}'.")
        print(f"[INFO] Formatting and saving to {auth_file}...")
        try:
            with open(pull_secret_path, 'r') as f:
                secret_data = json.load(f)
            with open(auth_file, 'w') as f:
                json.dump(secret_data, f, indent=4)
            print("[SUCCESS] Auth file successfully generated.")
        except Exception as e:
            print(f"[ERROR] Failed to process pull secret: {e}")
            sys.exit(1)
    else:
        print(f"[WARNING] Pull secret file '{pull_secret_path}' not found.")
        print("[WARNING] Relying on existing Podman authentication (if any).")
        
    # Export it for the current environment so oc-mirror knows exactly where to look
    os.environ["REGISTRY_AUTH_FILE"] = auth_file
    return auth_file

def append_registry_auth(auth_file, registry_url, admin_user, admin_pass):
    """Appends the local mirror registry credentials directly to the auth.json file."""
    print(f"\n[INFO] Appending local registry credentials to {auth_file}...")
    
    if not os.path.exists(auth_file):
        print(f"[ERROR] Auth file {auth_file} does not exist. Cannot append credentials.")
        return
        
    try:
        with open(auth_file, 'r') as f:
            auth_data = json.load(f)
            
        if 'auths' not in auth_data:
            auth_data['auths'] = {}
            
        email = ""
        for registry, data in auth_data['auths'].items():
            if 'email' in data:
                email = data['email']
                break
                
        if not email:
            email = "admin@localdomain"
            
        credentials = f"{admin_user}:{admin_pass}"
        encoded_creds = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        
        auth_data['auths'][registry_url] = {
            "auth": encoded_creds,
            "email": email
        }
        
        with open(auth_file, 'w') as f:
            json.dump(auth_data, f, indent=4)
            
        print(f"[SUCCESS] Appended base64 encoded credentials for {registry_url} to {auth_file}.")
        
    except Exception as e:
        print(f"[ERROR] Failed to append credentials to auth file: {e}")
        sys.exit(1)

def configure_firewall(port):
    """Configures firewalld to allow traffic on the specified port."""
    print(f"\n[INFO] Configuring firewall to allow port {port}/tcp...")
    
    # Check if firewalld is running
    status_cmd = subprocess.run(['sudo', 'firewall-cmd', '--state'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if status_cmd.returncode != 0:
         print("[WARNING] firewalld is not running or not installed. Skipping firewall configuration.")
         return

    add_port_cmd = ["sudo", "firewall-cmd", f"--add-port={port}/tcp", "--permanent"]
    run_command(add_port_cmd, f"Failed to add port {port}/tcp to the firewall.")
    
    reload_cmd = ["sudo", "firewall-cmd", "--reload"]
    run_command(reload_cmd, "Failed to reload the firewall.")
    print(f"[SUCCESS] Firewall configured to allow port {port}/tcp.")

def setup_local_mirror_registry(registry_fqdn, auth_file):
    """Installs Red Hat's official mirror-registry tool and authenticates podman."""
    print("\n=========================================================")
    print("[INFO] Setting up Local Mirror Registry (Quay)...")
    print("=========================================================")
    
    bin_dir = os.path.join(os.getcwd(), "bin")
    mirror_registry_url = "https://mirror.openshift.com/pub/cgw/mirror-registry/latest/mirror-registry-amd64.tar.gz"
    
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
    
    # Configure the firewall for the extracted port before starting the registry
    configure_firewall(port)
    
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
    
    # Explicitly append auth using base64 injection into auth.json
    append_registry_auth(auth_file, registry_url, admin_user, admin_pass)
    
    print(f"\n[INFO] Registry credentials injected. Skipping 'podman login' execution to preserve required email keys.")

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
    parser.add_argument("--pull-secret", default="./pull-secret.txt", help="Path to the Red Hat pull secret (default: ./pull-secret.txt)")
    
    args = parser.parse_args()

    print("=========================================================")
    print("      OpenShift Disconnected Mirroring Automation        ")
    print("=========================================================")
    print(f"Target Registry: {args.registry}")
    print(f"OCP Version:     {args.version}")
    print(f"Pull Secret:     {args.pull_secret}")
    print("=========================================================\n")

    # 0. Ensure Podman is installed (Required for mirror-registry and auth)
    ensure_podman()

    # 1. Download/Verify Tools (oc, oc-mirror)
    tools_were_missing = ensure_tools(args.version)
    
    # 2. Setup Authentication (Replicates `mkdir -p` and `cat | jq .`)
    auth_file_path = setup_auth_file(args.pull_secret)
    
    # 3. Configure Local Mirror Registry if tools were missing
    if tools_were_missing:
        print("\n[INFO] 'oc-mirror' was missing. Assuming fresh setup. Configuring local mirror registry...")
        setup_local_mirror_registry(args.registry, auth_file_path)
        # We need to tell oc-mirror to not verify TLS if we just stood up a self-signed registry
        os.environ["REGISTRY_AUTH_PREFERENCE"] = "podman"
        mirror_tls_flag = "--dest-skip-tls"
    else:
        mirror_tls_flag = ""

    # 4. Build Config
    generate_imageset_config(args.version, args.channel, args.config_file)

    # 5. Execute Mirror
    # Appending the tls flag if we just built the registry self-signed
    # Also appended the --v2 flag requested
    mirror_cmd = [
        "oc-mirror",
        "--v2",
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
