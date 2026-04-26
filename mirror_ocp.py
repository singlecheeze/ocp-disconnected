#!/usr/bin/env python3

import subprocess
import sys
import os
import argparse
import urllib.request
import tarfile
import urllib.error
import json
import base64
import socket
import getpass

# Ensure standard output and error streams are unbuffered for child processes
os.environ["PYTHONUNBUFFERED"] = "1"
# Force Ansible color output (useful if Ansible is called under the hood)
os.environ["ANSIBLE_FORCE_COLOR"] = "1"

def authenticate_sudo():
    """Checks if sudo requires a password, prompts if necessary, and caches the credential."""
    print("\n[INFO] Checking sudo privileges for system configuration...")
    # Check if we already have sudo access without a password or if it's already cached
    check_cmd = subprocess.run(['sudo', '-n', '-v'], capture_output=True)
    if check_cmd.returncode == 0:
        print("[INFO] Sudo access is already available.")
        return

    # If not, prompt the user explicitly
    sudo_password = getpass.getpass(prompt="[SUDO] Enter password: ")
    
    cmd = ['sudo', '-S', '-v']
    process = subprocess.run(cmd, input=sudo_password + '\n', text=True, capture_output=True)
    if process.returncode != 0:
        print("[ERROR] Incorrect sudo password or user lacks sudo privileges.")
        sys.exit(1)
    print("[SUCCESS] Sudo authenticated.")

def run_command(command, error_message):
    """Executes a shell command and streams the output line by line."""
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
        
    return auth_file

def append_registry_auth(auth_file, registry_url, admin_user, admin_pass):
    """Prepends the local mirror registry credentials to the beginning of the auth.json file."""
    print(f"\n[INFO] Injecting local registry credentials to {auth_file}...")
    
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
        
        print(f"[INFO] Encoded Credentials: {encoded_creds}")
        
        # Prepend the new registry to the beginning of the auths dictionary
        new_auths = {
            registry_url: {
                "auth": encoded_creds,
                "email": email
            }
        }
        new_auths.update(auth_data['auths'])
        auth_data['auths'] = new_auths
        
        with open(auth_file, 'w') as f:
            json.dump(auth_data, f, indent=4)
            
        print(f"[SUCCESS] Prepended base64 encoded credentials for {registry_url} to {auth_file}.")
        
    except Exception as e:
        print(f"[ERROR] Failed to prepend credentials to auth file: {e}")
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
    admin_pass = "Welcome1"
    
    # Set quayRoot to current working directory + "/mirror"
    current_dir = os.path.abspath(os.getcwd())
    quay_root = os.path.join(current_dir, "mirror")

    install_cmd = [
        "sudo", os.path.join(bin_dir, "mirror-registry"),
        "install",
        "--quayHostname", hostname,
        "--initUser", admin_user,
        "--initPassword", admin_pass,
        "--quayRoot", quay_root
    ]
    
    print("[INFO] Running mirror-registry installer. (Note: this requires sudo privileges)")
    run_command(install_cmd, "Failed to install the local mirror registry.")
    print("[SUCCESS] Local Mirror Registry (Quay) is successfully configured!")
    
    # Copy the Quay Root CA to the system's trust anchors and update CA trust
    cert_src = os.path.join(quay_root, "quay-rootCA", "rootCA.pem")
    cert_dest = "/etc/pki/ca-trust/source/anchors/"
    
    print(f"\n[INFO] Copying generated root CA to system trust anchors...")
    cp_cmd = ["sudo", "cp", cert_src, cert_dest]
    run_command(cp_cmd, f"Failed to copy {cert_src} to {cert_dest}")
    
    print(f"[INFO] Updating system CA trust...")
    update_trust_cmd = ["sudo", "update-ca-trust", "extract"]
    run_command(update_trust_cmd, "Failed to update CA trust.")
    print("[SUCCESS] System CA trust updated successfully.")
    
    # Explicitly append auth using base64 injection into auth.json
    append_registry_auth(auth_file, registry_url, admin_user, admin_pass)
    
    print(f"\n[INFO] Registry credentials injected. Skipping 'podman login' execution to preserve required email keys.")

def generate_imageset_config(version, channel, template_file, config_path):
    """Reads the template file, substitutes variables, and saves the ImageSetConfiguration."""
    print(f"\n[INFO] Loading ImageSetConfiguration template from {template_file}...")
    if not os.path.exists(template_file):
        print(f"[ERROR] Missing template file: {template_file}. Ensure it exists in the working directory.")
        sys.exit(1)
        
    try:
        with open(template_file, 'r') as f:
            content = f.read()
        
        # Replace placeholders natively
        content = content.replace('{channel}', channel)
        content = content.replace('{version}', version)
        
        with open(config_path, 'w') as f:
            f.write(content)
        print(f"[SUCCESS] Generated runtime config '{config_path}' from template '{template_file}'")
    except Exception as e:
        print(f"[ERROR] Failed to process template: {e}")
        sys.exit(1)

def main():
    default_registry = f"{socket.getfqdn()}:8443"
    
    parser = argparse.ArgumentParser(description="Automate OCP Mirroring & Local Registry Setup.")
    parser.add_argument("--registry", default=default_registry, help=f"Target mirror registry (default: {default_registry})")
    parser.add_argument("--version", default="4.21", help="OpenShift major.minor version (default: 4.21)")
    parser.add_argument("--channel", default="stable-4.21", help="OpenShift release channel (default: stable-4.21)")
    parser.add_argument("--template-file", default="imageset-config-template.yaml", help="Path to the ImageSetConfiguration template file")
    parser.add_argument("--config-file", default="imageset-config.yaml", help="Path to generate the config file")
    parser.add_argument("--pull-secret", default="./pull-secret.txt", help="Path to the Red Hat pull secret (default: ./pull-secret.txt)")
    
    args = parser.parse_args()
    
    # Prompt for sudo password at the very beginning of the script
    authenticate_sudo()

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

    # 4. Build Config from External Template
    generate_imageset_config(args.version, args.channel, args.template_file, args.config_file)

    # Determine current directory for workspace
    current_dir = os.path.abspath(os.getcwd())
    workspace_path = os.path.join(current_dir, "workspace")
    
    # Make sure the target directory exists before running
    os.makedirs(workspace_path, exist_ok=True)
    
    # 5. Execute Mirror
    mirror_cmd = [
        "oc-mirror",
        "--config", args.config_file,
        "--workspace", f"file://{workspace_path}",
        "--parallel-images=10",
        f"docker://{args.registry}",
        "--v2"
    ]
    
    print("\n[INFO] Starting mirror synchronization...")
    run_command(mirror_cmd, "oc-mirror process failed. Verify your Red Hat pull secret and storage capacity.")
    
    print("\n=========================================================")
    print("[SUCCESS] Process completed successfully!")
    print("=========================================================")

if __name__ == "__main__":
    main()
