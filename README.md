Here is a comprehensive Python script to automate the mirroring process for a Red Hat OpenShift 4.21 disconnected (offline) installation.

Red Hat uses the `oc-mirror` plugin as the standard method for mirroring OpenShift releases, operators, and additional images to a private registry. This script assumes you are running it from a RHEL bastion host that has access to both the internet (Red Hat Quay) and your internal mirror registry.

Prerequisites Before Running the Script
Install CLI Tools: Ensure oc and the `oc-mirror` plugin are installed on your RHEL bastion.

Authentication: Your `~/.docker/config.json` (or `${XDG_RUNTIME_DIR}/containers/auth.json` for Podman) must contain combined authentication for:
 - quay.io and registry.redhat.io (your Red Hat pull secret).
 - Your internal RHEL mirror registry.
 - Local Registry: A container registry (like Quay, Nexus, or a simple Podman registry container) must be running on your target RHEL server.

## How to use this script
Save the script: Save the code above to a file named mirror_ocp.py on your bastion server.

Make it executable:

```
chmod +x mirror_ocp.py
Run the script: Pass your internal RHEL registry's FQDN and port.
```

```
./mirror_ocp.py --registry my-rhel-registry.internal.lan:5000
```
Note on Fully Air-Gapped Environments (No Bastion):
If your network is strictly air-gapped and you cannot use a bastion that touches both the internet and the internal network simultaneously, you will need to run oc-mirror to a file archive first:
Change the `mirror_cmd` target in the Python script from `docker://{args.registry}` to `file://./mirror-archive`.
You would then move that archive folder via a secure medium (like a USB drive) to the isolated RHEL server, and run `oc-mirror --from ./mirror-archive docker://<internal-registry>` to unpack it.

## Next Steps Post-Mirroring
After a successful run, apply the generated configurations to your OpenShift cluster:
```
oc apply -f ./oc-mirror-workspace/results-*/release-signatures/
oc apply -f ./oc-mirror-workspace/results-*/imageContentSourcePolicy.yaml
```