#!/usr/bin/env python3

import subprocess
import sys
import os
import argparse
import textwrap


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


def check_prerequisites():
    """Checks if required CLI tools are installed."""
    tools = ['oc', 'oc-mirror']
    for tool in tools:
        if subprocess.run(['which', tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            print(f"[ERROR] Required tool '{tool}' is not installed or not in PATH.")
            sys.exit(1)
    print("[INFO] All prerequisite tools found.")


def generate_imageset_config(version, channel, config_path):
    """Generates the ImageSetConfiguration YAML file."""
    # This configuration mirrors the platform release and a few essential operators.
    # Modify the packages list based on your specific workload requirements.
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
    parser = argparse.ArgumentParser(description="Automate OCP 4.21 Mirroring to a target RHEL registry.")
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

    # 1. Verify environment
    check_prerequisites()

    # 2. Ensure auth file is accessible (oc-mirror relies on Docker/Podman auth)
    auth_file = os.environ.get('REGISTRY_AUTH_FILE', os.path.expanduser('~/.docker/config.json'))
    if not os.path.exists(auth_file):
        print(
            f"[WARNING] Auth file not found at {auth_file}. Ensure you are authenticated to Quay and your local registry.")
    else:
        print(f"[INFO] Using container auth file: {auth_file}")

    # 3. Create the ImageSetConfiguration
    generate_imageset_config(args.version, args.channel, args.config_file)

    # 4. Execute the oc-mirror command
    # NOTE: To do a fully air-gapped file transfer instead of direct-to-registry,
    # replace 'docker://...' with 'file://./mirror-archive'
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
    print("Next Steps:")
    print("1. Apply the generated ImageContentSourcePolicy (ICSP) or ImageDigestMirrorSet (IDMS) to your cluster.")
    print("2. The output manifests are located in the ./oc-mirror-workspace/results-*/ directory.")
    print("   Apply them using: oc apply -f ./oc-mirror-workspace/results-*/release-signatures/")
    print("                     oc apply -f ./oc-mirror-workspace/results-*/imageContentSourcePolicy.yaml")


if __name__ == "__main__":
    main()