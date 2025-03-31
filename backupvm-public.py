#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
from concurrent.futures import ThreadPoolExecutor
import time

VMWARE_HOSTS = ["192.168.1.1"]

def parse_args():
    parser = argparse.ArgumentParser(description='VMware VM Backup Tool')
    parser.add_argument('vm_name', help='VM name to search (partial match supported)')
    parser.add_argument('--out', help='Output archive path (default: ./<vmname>.tar.zst)')
    parser.add_argument('--temp', default='/tmp/vmbackup_temp', help='Temporary mount point')
    return parser.parse_args()

def run_ssh_command(host, command, check=True):
    """Execute SSH command and return output"""
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

def get_datastore_uuid(host, datastore_name):
    """Resolve datastore name to UUID by examining /vmfs/volumes"""
    ls_output = run_ssh_command(host, 'ls -l /vmfs/volumes')
    if not ls_output:
        return None

    for line in ls_output.split('\n'):
        if datastore_name in line:
            parts = line.split()
            if '->' in parts:
                return parts[-1]
            elif re.match(r'^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$', parts[-1]):
                return parts[-1]
    return None

def find_vm(vm_name):
    """Find VM by searching the friendly name column"""
    for host in VMWARE_HOSTS:
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
                vm_rel_path = ds_match.group(2)
                vm_dir = os.path.dirname(vm_rel_path)

                datastore_uuid = get_datastore_uuid(host, datastore_name)
                if not datastore_uuid:
                    continue

                full_vm_path = f"/vmfs/volumes/{datastore_uuid}/{vm_dir}"

                return {
                    'host': host,
                    'vm_id': vm_id,
                    'vm_path': full_vm_path,
                    'vm_name': friendly_name
                }

    raise ValueError(f"VM containing '{vm_name}' not found on any host")

def create_snapshot(host, vm_id):
    print("Creating snapshot...")
    run_ssh_command(host, f'vim-cmd vmsvc/snapshot.create {vm_id} BackupSnapshot SnapshotBackup 0 1')

def mount_vm_dir(host, vm_path, temp_folder):
    print(f"Mounting VM directory from {host}...")
    os.makedirs(temp_folder, exist_ok=True)
    subprocess.run(
        ['sshfs', '-o', 'idmap=user', '-o', 'reconnect', f'root@{host}:{vm_path}', temp_folder],
        check=True
    )

def calculate_total_size(temp_folder):
    """Calculate total size of VM files to be backed up"""
    find_cmd = [
        'find', temp_folder,
        '-type', 'f',
        '(', '-name', '*.vmdk', '-o', '-name', '*.vmx',
        '-o', '-name', '*.vmxf', '-o', '-name', '*.vmsd', ')',
        '-not', '(', '-name', '*00000*', '-o', '-name', '*sesparse*', ')',
        '-exec', 'du', '-sb', '{}', '+'
    ]

    try:
        result = subprocess.run(
            find_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            return 0

        total = 0
        for line in result.stdout.split('\n'):
            if line:
                parts = line.split()
                if parts:
                    total += int(parts[0])
        return total
    except Exception:
        return 0

def create_backup(temp_folder, output_path):
    print("Creating backup archive...")

    total_size = calculate_total_size(temp_folder)
    print(f"Total size to back up: {total_size/1024/1024:.1f} MB")

    find_cmd = [
        'find', temp_folder,
        '-type', 'f',
        '(', '-name', '*.vmdk', '-o', '-name', '*.vmx',
        '-o', '-name', '*.vmxf', '-o', '-name', '*.vmsd', ')',
        '-not', '(', '-name', '*00000*', '-o', '-name', '*sesparse*', ')',
        '-print0'
    ]

    tar_cmd = [
        'tar',
        '--null',
        '--ignore-failed-read',
        '--use-compress-program=zstd',
        '-cvf', output_path,
        '-T', '-'
    ]

    print("Starting backup...")
    with subprocess.Popen(find_cmd, stdout=subprocess.PIPE) as find_proc, \
         subprocess.Popen(tar_cmd, stdin=find_proc.stdout, stdout=subprocess.PIPE) as tar_proc:

        def monitor_progress():
            while tar_proc.poll() is None:
                try:
                    current_size = os.path.getsize(output_path)
                except OSError:
                    current_size = 0
                progress = (current_size / total_size) * 100 if total_size > 0 else 0
                print(f"\rProgress: {progress:.1f}% ({current_size/1024/1024:.1f}MB/{total_size/1024/1024:.1f}MB)", end='')
                time.sleep(1)

        with ThreadPoolExecutor() as executor:
            future = executor.submit(monitor_progress)
            tar_proc.wait()
            future.cancel()

        print()

        if tar_proc.returncode != 0:
            raise subprocess.CalledProcessError(tar_proc.returncode, 'tar')

def cleanup(host, vm_id, temp_folder):
    print("Unmounting remote filesystem...")
    subprocess.run(['fusermount', '-u', temp_folder], check=False)

    print("Removing snapshots...")
    run_ssh_command(host, f'vim-cmd vmsvc/snapshot.removeall {vm_id}')

def main():
    try:
        args = parse_args()
        vm_info = find_vm(args.vm_name)
        print(f"Found VM {vm_info['vm_name']} (ID: {vm_info['vm_id']}) on host {vm_info['host']}")
        print(f"VM Path: {vm_info['vm_path']}")

        output_path = args.out or f"./{vm_info['vm_name']}.tar.zst"

        create_snapshot(vm_info['host'], vm_info['vm_id'])
        mount_vm_dir(vm_info['host'], vm_info['vm_path'], args.temp)
        create_backup(args.temp, output_path)

        print(f"Backup completed successfully: {output_path}")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'vm_info' in locals():
            cleanup(vm_info['host'], vm_info['vm_id'], args.temp)

if __name__ == "__main__":
    main()
