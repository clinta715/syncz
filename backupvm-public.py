#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
import time

VMWARE_HOSTS = [""]

def parse_args():
    parser = argparse.ArgumentParser(description='VMware VM Backup Tool')
    parser.add_argument('vm_name', help='VM name to search (partial match supported)')
    parser.add_argument('--out', required=True, help='Output directory (must exist)')
    parser.add_argument('--temp', default='/tmp/vmbackup_temp', help='Temporary mount point')
    return parser.parse_args()

def run_ssh_command(host, command, check=True):
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=10', f'root@{host}', command],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"SSH command failed on {host}: {e.stderr.strip()}", file=sys.stderr)
        return None

def get_related_vmdk_files(host, vmdk_path):
    """Find all related VMDK files for a given disk"""
    vmdk_dir = os.path.dirname(vmdk_path)
    base_name = os.path.basename(vmdk_path).replace('.vmdk', '')

    # Get all files in the directory
    ls_output = run_ssh_command(host, f'ls "{vmdk_dir}"')
    if not ls_output:
        return []

    # Pattern to match related VMDK files
    pattern = re.compile(
        r'^' + re.escape(base_name) +
        r'(-flat|-s\d{1,3}|-f\d{1,3}|-\d{1,3})?\.vmdk$'
    )

    related_files = []
    for file in ls_output.split('\n'):
        file = file.strip()
        if file and pattern.match(file):
            full_path = os.path.join(vmdk_dir, file)
            related_files.append(full_path)

    return related_files or [vmdk_path]  # Fallback to original if no matches

def get_datastore_mapping(host):
    ls_output = run_ssh_command(host, 'ls -l /vmfs/volumes')
    if not ls_output:
        return {}

    mapping = {}
    for line in ls_output.split('\n'):
        if not line.strip():
            continue

        parts = line.split()
        if '->' in parts:
            symlink = parts[-3]
            uuid = parts[-1]
            mapping[symlink] = uuid
            mapping[uuid] = uuid
        elif re.match(r'^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$', parts[-1]):
            uuid = parts[-1]
            mapping[uuid] = uuid
    return mapping

def parse_vmx_file(host, vmx_path):
    vmx_content = run_ssh_command(host, f'cat "{vmx_path}"')
    if not vmx_content:
        return []

    disk_files = []
    for line in vmx_content.split('\n'):
        line = line.strip()
        if any(x in line for x in ['.fileName', '.file']):
            match = re.search(r'=\s*"([^"]+\.(vmdk|iso))"', line)
            if match:
                disk_path = match.group(1)
                if not disk_path.startswith('/'):
                    disk_path = os.path.join(os.path.dirname(vmx_path), disk_path)
                disk_files.append(disk_path)
    return disk_files

def find_vm(vm_name):
    for host in VMWARE_HOSTS:
        datastore_map = get_datastore_mapping(host)
        if not datastore_map:
            continue

        all_vms = run_ssh_command(host, 'vim-cmd vmsvc/getallvms')
        if not all_vms:
            continue

        for line in all_vms.split('\n'):
            if line.startswith('Vmid') or not line.strip():
                continue

            columns = re.split(r'\s{2,}', line.strip())
            if len(columns) < 3:
                continue

            vm_id, friendly_name, vm_path = columns[0], columns[1], columns[2]

            if vm_name.lower() in friendly_name.lower():
                ds_match = re.match(r'^\[([^\]]+)\]\s*(.+)$', vm_path)
                if not ds_match:
                    continue

                datastore_name = ds_match.group(1)
                vmx_rel_path = ds_match.group(2)
                vm_dir = os.path.dirname(vmx_rel_path)

                datastore_uuid = datastore_map.get(datastore_name)
                if not datastore_uuid:
                    print(f"Warning: Could not resolve datastore '{datastore_name}'")
                    continue

                full_vmx_path = f"/vmfs/volumes/{datastore_uuid}/{vmx_rel_path}"
                if not run_ssh_command(host, f'[ -f "{full_vmx_path}" ] && echo exists'):
                    print(f"Warning: VMX file not found at {full_vmx_path}")
                    continue

                disk_files = parse_vmx_file(host, full_vmx_path)
                if not disk_files:
                    print(f"Warning: No disk files found in VMX configuration")

                return {
                    'host': host,
                    'vm_id': vm_id,
                    'vm_name': friendly_name,
                    'vmx_path': full_vmx_path,
                    'vm_dir': f"/vmfs/volumes/{datastore_uuid}/{vm_dir}",
                    'disk_files': disk_files
                }
    raise ValueError(f"VM '{vm_name}' not found or files missing")

def create_snapshot(host, vm_id):
    print("Creating snapshot...")
    run_ssh_command(host, f'vim-cmd vmsvc/snapshot.create {vm_id} BackupSnapshot SnapshotBackup 0 1')

def is_mounted(path):
    """Check if a path is already mounted"""
    try:
        result = subprocess.run(['mount'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return path in result.stdout
    except Exception:
        return False

def mount_directory(host, remote_path, local_path):
    """Mount remote directory only if not already mounted"""
    if is_mounted(local_path):
        print(f"Directory {local_path} is already mounted")
        return True

    os.makedirs(local_path, exist_ok=True)
    try:
        subprocess.run(
            ['sshfs', '-o', 'idmap=user', '-o', 'reconnect', f'root@{host}:{remote_path}', local_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to mount {remote_path} to {local_path}: {e.stderr}", file=sys.stderr)
        return False

def unmount_directory(local_path):
    if is_mounted(local_path):
        subprocess.run(['fusermount', '-u', local_path], check=False)

def backup_vm_config(host, vm_dir, output_dir, vm_name, temp_base):
    """Backup VM configuration files"""
    config_temp = os.path.join(temp_base, 'config')
    if not mount_directory(host, vm_dir, config_temp):
        raise ValueError(f"Failed to mount VM directory {vm_dir}")

    try:
        # Find all config files in the mounted directory
        config_files = []
        for root, _, files in os.walk(config_temp):
            for file in files:
                if file.endswith(('.vmx', '.vmxf', '.vmsd', '.nvram')):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, config_temp)
                    config_files.append(rel_path)

        if not config_files:
            raise ValueError("No VM configuration files found")

        output_file = os.path.join(output_dir, f"{vm_name}_config.tar.zst")
        print(f"Backing up VM configuration to {output_file}")

        # Change to the mounted directory and tar from there
        os.chdir(config_temp)
        try:
            subprocess.run(
                ['tar', '--use-compress-program=zstd', '-cvf', output_file] + config_files,
                check=True
            )
        finally:
            os.chdir('/')  # Always change back to root directory

    finally:
        unmount_directory(config_temp)

def backup_vmdk(host, vmdk_path, output_dir, vm_name, disk_num, temp_base):
    """Backup individual VMDK file and all related files"""
    vmdk_dir = os.path.dirname(vmdk_path)
    base_name = os.path.basename(vmdk_path).replace('.vmdk', '')

    # Get all related VMDK files
    related_files = get_related_vmdk_files(host, vmdk_path)
    print(f"Found {len(related_files)} related VMDK files for {vmdk_path}")

    # Create a unique mount point for this VMDK set
    vmdk_temp = os.path.join(temp_base, f'vmdk_{disk_num}')

    # Mount the directory containing the VMDK files
    if not mount_directory(host, vmdk_dir, vmdk_temp):
        raise ValueError(f"Failed to mount VMDK directory {vmdk_dir}")

    try:
        # Verify all related files exist
        missing_files = []
        for file in related_files:
            local_path = os.path.join(vmdk_temp, os.path.basename(file))
            if not os.path.exists(local_path):
                missing_files.append(file)

        if missing_files:
            print(f"Warning: Missing VMDK files: {', '.join(missing_files)}")

        # Create a tar archive of all found files
        found_files = [f for f in related_files if os.path.basename(f) not in missing_files]
        if not found_files:
            raise ValueError("No VMDK files found to back up")

        output_file = os.path.join(output_dir, f"{vm_name}_disk{disk_num}.tar.zst")
        print(f"Backing up {len(found_files)} VMDK files to {output_file}")

        # Change to the mounted directory and tar from there
        os.chdir(vmdk_temp)
        try:
            subprocess.run(
                ['tar', '--use-compress-program=zstd', '-cvf', output_file] +
                [os.path.basename(f) for f in found_files],
                check=True
            )
        finally:
            os.chdir('/')  # Always change back to root directory

    finally:
        unmount_directory(vmdk_temp)

def cleanup(host, vm_id, temp_folder):
    print("Unmounting any remaining mounts...")
    for mount in os.listdir(temp_folder):
        unmount_directory(os.path.join(temp_folder, mount))

    print("Removing snapshots...")
    run_ssh_command(host, f'vim-cmd vmsvc/snapshot.removeall {vm_id}')

def main():
    args = parse_args()
    try:
        # Verify output directory exists
        if not os.path.exists(args.out):
            raise ValueError(f"Output directory {args.out} does not exist")

        # Create temp directory if it doesn't exist
        os.makedirs(args.temp, exist_ok=True)

        vm_info = find_vm(args.vm_name)
        print(f"Found VM {vm_info['vm_name']} (ID: {vm_info['vm_id']}) on host {vm_info['host']}")
        print(f"VM Directory: {vm_info['vm_dir']}")
        print(f"VMX File: {vm_info['vmx_path']}")
        print(f"Disk Files: {', '.join(vm_info['disk_files'])}")

        create_snapshot(vm_info['host'], vm_info['vm_id'])

        # Backup VM configuration first
        backup_vm_config(vm_info['host'], vm_info['vm_dir'], args.out, vm_info['vm_name'], args.temp)

        # Backup each VMDK and its related files
        for i, vmdk_path in enumerate(vm_info['disk_files'], 1):
            if vmdk_path.endswith('.vmdk'):  # Only backup VMDKs, skip ISOs
                try:
                    backup_vmdk(
                        vm_info['host'],
                        vmdk_path,
                        args.out,
                        vm_info['vm_name'],
                        i,
                        args.temp
                    )
                except Exception as e:
                    print(f"Error backing up {vmdk_path}: {e}", file=sys.stderr)

        print(f"Backup completed successfully in directory: {args.out}")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'vm_info' in locals():
            cleanup(vm_info['host'], vm_info['vm_id'], args.temp)

if __name__ == "__main__":
    main()
