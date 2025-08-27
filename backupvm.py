#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
import time
import portalocker  # Add this
import hashlib
from datetime import datetime

# Supported compression programs and their extensions
COMPRESSION_FORMATS = {
    'zstd': {'ext': '.tar.zst', 'cmd': 'zstd'},
    'gzip': {'ext': '.tar.gz', 'cmd': 'gzip'},
    'bzip2': {'ext': '.tar.bz2', 'cmd': 'bzip2'},
    'xz': {'ext': '.tar.xz', 'cmd': 'xz'},
    'none': {'ext': '.tar', 'cmd': 'cat'},  # 'cat' for no compression
}

class BackupLogger:
    def __init__(self, log_dir=None, vm_name="unknown", host="unknown"):
        self.log_dir = log_dir
        self.vm_name = vm_name
        self.host = host
        self.start_time = datetime.now()
        self.log_file = None
        self.log_path = None
        self.errors = []
        self.warnings = []
        
        if log_dir:
            self._create_log_file()
    
    def _create_log_file(self):
        """Create log file with timestamp and VM info in filename"""
        if self.log_dir is None:
            return  # Should not happen due to check in __init__, but for type safety

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
        
        # Sanitize names for filename
        safe_vm_name = re.sub(r'[^\w\-_.]', '_', self.vm_name)
        safe_host = re.sub(r'[^\w\-_.]', '_', self.host)
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        filename = f"vmbackup_{safe_vm_name}_{safe_host}_{timestamp}.log"
        self.log_path = os.path.join(self.log_dir, filename)
        
        try:
            self.log_file = open(self.log_path, 'w')
            self._write_header()
        except Exception as e:
            print(f"Warning: Could not create log file {self.log_path}: {e}", file=sys.stderr)
            self.log_file = None
    
    def _write_header(self):
        """Write structured header for parsing/charting"""
        if not self.log_file:
            return
        
        # Structured data header (one line for easy parsing)
        header = f"BACKUP_LOG_V1|{self.start_time.isoformat()}|{self.vm_name}|{self.host}|RUNNING|0|0"
        self.log_file.write(f"{header}\n")
        self.log_file.write("="*80 + "\n")
        
        # Human readable header
        self.log_file.write(f"VMware VM Backup Log\n")
        self.log_file.write(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write(f"VM Name: {self.vm_name}\n")
        self.log_file.write(f"Host: {self.host}\n")
        self.log_file.write(f"Log File: {self.log_path}\n")
        self.log_file.write("="*80 + "\n\n")
        self.log_file.flush()
    
    def log(self, message, level="INFO"):
        """Log a message with timestamp and level"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {level}: {message}"
        
        # Always print to console
        if level == "ERROR":
            print(log_entry, file=sys.stderr)
            self.errors.append(message)
        elif level == "WARNING":
            print(log_entry, file=sys.stderr)
            self.warnings.append(message)
        else:
            print(log_entry)
        
        # Write to log file if available and not closed
        if self.log_file and not self.log_file.closed:
            self.log_file.write(f"{log_entry}\n")
            self.log_file.flush()
    
    def finalize(self, status="SUCCESS", final_message="Backup completed successfully"):
        """Finalize the log with status and update header"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        # Log final status
        self.log(f"Backup {status.lower()} after {duration:.1f} seconds",
                level="INFO" if status == "SUCCESS" else "ERROR")
        self.log(final_message)

        if self.warnings:
            self.log(f"Total warnings: {len(self.warnings)}", "WARNING")
        if self.errors:
            self.log(f"Total errors: {len(self.errors)}", "ERROR")

        if self.log_file and self.log_path:
            # Write summary
            self.log_file.write("\n" + "="*80 + "\n")
            self.log_file.write("BACKUP SUMMARY\n")
            self.log_file.write(f"Status: {status}\n")
            self.log_file.write(f"Duration: {duration:.1f} seconds\n")
            self.log_file.write(f"Warnings: {len(self.warnings)}\n")
            self.log_file.write(f"Errors: {len(self.errors)}\n")
            self.log_file.write(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.flush()
            self.log_file.close()

            # Now update the header by reading and rewriting the entire file
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()

                # Replace the first line with updated status
                lines = current_content.split('\n')
                if lines and lines[0].startswith("BACKUP_LOG_V1|"):
                    parts = lines[0].split('|')
                    if len(parts) >= 7:
                        parts[4] = status  # Update status
                        parts[5] = str(len(self.warnings))  # Update warning count
                        parts[6] = str(len(self.errors))  # Update error count
                        lines[0] = '|'.join(parts)

                # Write the updated content back
                with open(self.log_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))

            except Exception as e:
                print(f"Warning: Could not update log header: {e}", file=sys.stderr)

            print(f"Log written to: {self.log_path}")

# Global logger instance
logger = None

def compute_hash(file_path, algo='sha256', chunk_size=65536):
    """Compute hash of a file with the chosen algorithm"""
    h = hashlib.new(algo)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            h.update(chunk)
    return h.hexdigest()

def generate_manifest(archive_path, output_dir, algo='sha256'):
    manifest_path = os.path.join(
        output_dir,
        os.path.basename(archive_path) + f".{algo}.manifest.txt"
    )
    with open(manifest_path, 'w') as mf:
        size = os.path.getsize(archive_path)
        digest = compute_hash(archive_path, algo)
        mf.write(f"Archive: {archive_path}\n")
        mf.write(f"Size: {size} bytes\n")
        mf.write(f"{algo.upper()}: {digest}\n\n")

        # List archive contents
        mf.write("Contents:\n")
        try:
            result = subprocess.run(
                ['tar', '-tvf', archive_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) < 6:
                    continue
                size = parts[2] if parts[2].isdigit() else parts[-4]
                name = parts[-1]
                mf.write(f"{name}\t{size} bytes\n")
        except Exception as e:
            mf.write(f"Could not list contents: {e}\n")

    if logger:
        logger.log(f"Manifest written to {manifest_path}")

def parse_args():
    parser = argparse.ArgumentParser(description='VMware VM Backup Tool')
    parser.add_argument('vm_name', help='VM name to search (partial match supported)')
    parser.add_argument('--out', required=True, help='Output directory (must exist)')
    parser.add_argument('--temp', default='/tmp/vmbackup_temp', help='Temporary mount point')
    parser.add_argument('--username', default='root', help='SSH username for VMware hosts')
    parser.add_argument('--hosts', required=True, nargs='+', help='VMware host IPs to search')
    parser.add_argument('--compression', choices=COMPRESSION_FORMATS.keys(), default='zstd',
                        help='Compression method to use (default: zstd)')
    parser.add_argument('--compression-level', type=int, help='Compression level (optional, program-specific)')
    parser.add_argument('--hash', dest='hash_algo', default='sha256',
                    choices=hashlib.algorithms_available,
                    help='Hash algorithm to use for manifests (default: sha256)')
    parser.add_argument('--log-dir', help='Directory to write log files (optional)')
    return parser.parse_args()

def run_ssh_command(host, username, command, check=True):
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=10', f'{username}@{host}', command],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if logger:
            logger.log(f"SSH command failed on {host}: {e.stderr.strip()}", "ERROR")
        return None

def get_related_vmdk_files(host, username, vmdk_path):
    """Find all related VMDK files for a given disk"""
    vmdk_dir = os.path.dirname(vmdk_path)
    base_name = os.path.basename(vmdk_path).replace('.vmdk', '')

    # Get all files in the directory
    ls_output = run_ssh_command(host, username, f'ls "{vmdk_dir}"')
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

def get_datastore_mapping(host, username):
    ls_output = run_ssh_command(host, username, 'ls -l /vmfs/volumes')
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

def parse_vmx_file(host, username, vmx_path):
    vmx_content = run_ssh_command(host, username, f'cat "{vmx_path}"')
    if not vmx_content:
        return []

    disk_files = []
    for line in vmx_content.split('\n'):
        line = line.strip()
        if any(x in line for x in ['.fileName', '.file']):
            match = re.search(r'=\s*"([^"]+\.(vmdk|iso))"', line)
            if match:
                disk_path = match.group(1)
                # Fix snapshot redirection
                disk_path = re.sub(r'([a-zA-Z0-9]+)-[0-9]{6}\.vmdk', r'\1.vmdk', disk_path)
                if not disk_path.startswith('/'):
                    disk_path = os.path.join(os.path.dirname(vmx_path), disk_path)
                disk_files.append(disk_path)
    return disk_files

def find_vm(vm_name, hosts, username):
    if logger:
        logger.log(f"Searching for VM '{vm_name}' across {len(hosts)} hosts")

    for host in hosts:
        if logger:
            logger.log(f"Checking host {host}")
        datastore_map = get_datastore_mapping(host, username)
        if not datastore_map:
            if logger:
                logger.log(f"Could not get datastore mapping for {host}", "WARNING")
            continue

        all_vms = run_ssh_command(host, username, 'vim-cmd vmsvc/getallvms')
        if not all_vms:
            if logger:
                logger.log(f"Could not get VM list from {host}", "WARNING")
            continue

        for line in all_vms.split('\n'):
            if line.startswith('Vmid') or not line.strip():
                continue

            columns = re.split(r'\s{2,}', line.strip())
            if len(columns) < 3:
                continue

            vm_id, friendly_name, vm_path = columns[0], columns[1], columns[2]

            if vm_name.lower() in friendly_name.lower():
                if logger:
                    logger.log(f"Found matching VM: {friendly_name}")
                ds_match = re.match(r'^\[([^\]]+)\]\s*(.+)$', vm_path)
                if not ds_match:
                    continue

                datastore_name = ds_match.group(1)
                vmx_rel_path = ds_match.group(2)
                vm_dir = os.path.dirname(vmx_rel_path)

                datastore_uuid = datastore_map.get(datastore_name)
                if not datastore_uuid:
                    if logger:
                        logger.log(f"Could not resolve datastore '{datastore_name}'", "WARNING")
                    continue

                full_vmx_path = f"/vmfs/volumes/{datastore_uuid}/{vmx_rel_path}"
                if not run_ssh_command(host, username, f'[ -f "{full_vmx_path}" ] && echo exists'):
                    if logger:
                        logger.log(f"VMX file not found at {full_vmx_path}", "WARNING")
                    continue

                disk_files = parse_vmx_file(host, username, full_vmx_path)
                if not disk_files:
                    if logger:
                        logger.log("No disk files found in VMX configuration", "WARNING")

                vm_info = {
                    'host': host,
                    'username': username,
                    'vm_id': vm_id,
                    'vm_name': friendly_name,
                    'vmx_path': full_vmx_path,
                    'vm_dir': f"/vmfs/volumes/{datastore_uuid}/{vm_dir}",
                    'disk_files': disk_files
                }
                if logger:
                    logger.log(f"VM found successfully on host {host}")
                return vm_info

    raise ValueError(f"VM '{vm_name}' not found or files missing")

def create_snapshot(host, username, vm_id):
    if logger:
        logger.log("Creating backup snapshot")
    run_ssh_command(host, username, f'vim-cmd vmsvc/snapshot.create {vm_id} BackupSnapshot SnapshotBackup 0 1')
    if logger:
        logger.log("Snapshot created successfully")

def is_mounted(path):
    """Check if a path is already mounted"""
    try:
        result = subprocess.run(['mount'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return path in result.stdout
    except Exception:
        return False

def mount_directory(host, username, remote_path, local_path):
    """Mount remote directory only if not already mounted"""
    if is_mounted(local_path):
        if logger:
            logger.log(f"Directory {local_path} is already mounted")
        return True

    os.makedirs(local_path, exist_ok=True)
    try:
        subprocess.run(
            ['sshfs', '-o', 'idmap=user', '-o', 'reconnect', f'{username}@{host}:{remote_path}', local_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if logger:
            logger.log(f"Mounted {remote_path} to {local_path}")
        return True
    except subprocess.CalledProcessError as e:
        if logger:
            logger.log(f"Failed to mount {remote_path} to {local_path}: {e.stderr}", "ERROR")
        return False

def unmount_directory(local_path):
    if is_mounted(local_path):
        subprocess.run(['fusermount', '-u', local_path], check=False)
        if logger:
            logger.log(f"Unmounted {local_path}")

def get_compression_command(compression_format, compression_level=None):
    """Build compression command with optional level"""
    compress_info = COMPRESSION_FORMATS[compression_format]
    cmd = compress_info['cmd']

    # If compression level is specified and not using 'none'
    if compression_level is not None and compression_format != 'none':
        # Different programs have different level flags
        if compression_format == 'gzip':
            return f'{cmd} -{compression_level}'
        elif compression_format == 'zstd':
            return f'{cmd} -{compression_level}'
        elif compression_format == 'xz':
            return f'{cmd} -{compression_level}'
        elif compression_format == 'bzip2':
            return f'{cmd} -{compression_level}'

    return cmd

def backup_vm_config(host, username, vm_dir, output_dir, vm_name, temp_base, compression_format, compression_level=None, hash_algo='sha256'):
    """Backup VM configuration files"""
    config_temp = os.path.join(temp_base, 'config')
    if not mount_directory(host, username, vm_dir, config_temp):
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

        compress_info = COMPRESSION_FORMATS[compression_format]
        output_file = os.path.join(output_dir, f"{vm_name}_config{compress_info['ext']}")
        if logger:
            logger.log(f"Backing up VM configuration to {output_file} using {compression_format} compression")

        # Change to the mounted directory and tar from there
        os.chdir(config_temp)
        try:
            compress_cmd = get_compression_command(compression_format, compression_level)
            subprocess.run(
                ['tar', f'--use-compress-program={compress_cmd}', '-cvf', output_file] + config_files,
                check=True
            )

            # Generate manifest for this archive
            generate_manifest(output_file, output_dir, hash_algo)
            if logger:
                logger.log(f"Configuration backup completed: {len(config_files)} files archived")
        finally:
            os.chdir('/')  # Always change back to root directory

    finally:
        unmount_directory(config_temp)

def backup_vmdk(host, username, vmdk_path, output_dir, vm_name, disk_num, temp_base, compression_format, compression_level=None, hash_algo='sha256'):
    """Backup individual VMDK file and all related files"""
    vmdk_dir = os.path.dirname(vmdk_path)
    base_name = os.path.basename(vmdk_path).replace('.vmdk', '')

    # Get all related VMDK files
    related_files = get_related_vmdk_files(host, username, vmdk_path)
    if logger:
        logger.log(f"Found {len(related_files)} related VMDK files for {vmdk_path}")

    # Create a unique mount point for this VMDK set using timestamp and PID
    timestamp = int(time.time())
    pid = os.getpid()
    vmdk_temp = os.path.join(temp_base, f'vmdk_{disk_num}_{timestamp}_{pid}')

    # Mount the directory containing the VMDK files
    if not mount_directory(host, username, vmdk_dir, vmdk_temp):
        raise ValueError(f"Failed to mount VMDK directory {vmdk_dir}")

    try:
        # Verify all related files exist
        missing_files = []
        for file in related_files:
            local_path = os.path.join(vmdk_temp, os.path.basename(file))
            if not os.path.exists(local_path):
                missing_files.append(file)

        if missing_files:
            if logger:
                logger.log(f"Missing VMDK files: {', '.join(missing_files)}", "WARNING")

        # Create a tar archive of all found files
        found_files = [f for f in related_files if os.path.basename(f) not in missing_files]
        if not found_files:
            raise ValueError("No VMDK files found to back up")

        compress_info = COMPRESSION_FORMATS[compression_format]
        output_file = os.path.join(output_dir, f"{vm_name}_disk{disk_num}{compress_info['ext']}")
        if logger:
            logger.log(f"Backing up {len(found_files)} VMDK files to {output_file} using {compression_format} compression")

        # Change to the mounted directory and tar from there
        os.chdir(vmdk_temp)
        try:
            compress_cmd = get_compression_command(compression_format, compression_level)
            subprocess.run(
                ['tar', f'--use-compress-program={compress_cmd}', '-cvf', output_file] +
                [os.path.basename(f) for f in found_files],
                check=True
            )
            
            # Generate manifest for this archive
            generate_manifest(output_file, output_dir, hash_algo)
            if logger:
                logger.log(f"Disk {disk_num} backup completed: {len(found_files)} files archived")
        finally:
            os.chdir('/')  # Always change back to root directory

    finally:
        unmount_directory(vmdk_temp)
        try:
            os.rmdir(vmdk_temp)  # Clean up the empty directory
        except OSError:
            pass  # Ignore if directory not empty or other error

def cleanup(host, username, vm_id, temp_folder):
    if logger:
        logger.log("Starting cleanup process")
        logger.log("Unmounting any remaining mounts")
    for mount_dir in os.listdir(temp_folder):
        unmount_directory(os.path.join(temp_folder, mount_dir))

    if logger:
        logger.log("Removing snapshots")
    run_ssh_command(host, username, f'vim-cmd vmsvc/snapshot.removeall {vm_id}')
    if logger:
        logger.log("Cleanup completed")

def main():
    global logger
    args = parse_args()

    # Initialize logger early with minimal info
    logger = BackupLogger(args.log_dir, args.vm_name, "searching")

    # Lock based on VM name
    safe_vm_name = re.sub(r'\W+', '_', args.vm_name)  # sanitize VM name for filename
    lockfile_path = f'/tmp/backupvm_{safe_vm_name}.lock'

    try:
        lock_file = open(lockfile_path, 'w')
        portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.exceptions.LockException:
        error_msg = f"Another backup of VM '{args.vm_name}' is already in progress. Exiting."
        if logger:
            logger.log(error_msg, "ERROR")
            logger.finalize("FAILED", error_msg)
        sys.exit(1)

    try:
        if logger:
            logger.log("Starting VMware VM backup process")
            logger.log(f"Target VM: {args.vm_name}")
            logger.log(f"Output directory: {args.out}")
            logger.log(f"Compression: {args.compression}" +
                      (f" (level {args.compression_level})" if args.compression_level else ""))
            logger.log(f"Hash algorithm: {args.hash_algo}")
        
        # Verify output directory exists
        if not os.path.exists(args.out):
            raise ValueError(f"Output directory {args.out} does not exist")

        # Create temp directory if it doesn't exist
        os.makedirs(args.temp, exist_ok=True)
        if logger:
            logger.log(f"Using temporary directory: {args.temp}")

        vm_info = find_vm(args.vm_name, args.hosts, args.username)
        
        # Update logger with actual host info now that we found the VM
        logger.host = vm_info['host']
        logger.vm_name = vm_info['vm_name']

        if logger:
            logger.log(f"VM Details:")
            logger.log(f"  Name: {vm_info['vm_name']}")
            logger.log(f"  ID: {vm_info['vm_id']}")
            logger.log(f"  Host: {vm_info['host']}")
            logger.log(f"  VM Directory: {vm_info['vm_dir']}")
            logger.log(f"  VMX File: {vm_info['vmx_path']}")
            logger.log(f"  Disk Files: {len(vm_info['disk_files'])} found")
            for i, disk in enumerate(vm_info['disk_files'], 1):
                logger.log(f"    Disk {i}: {disk}")

        create_snapshot(vm_info['host'], vm_info['username'], vm_info['vm_id'])

        # Backup VM configuration first
        if logger:
            logger.log("Starting configuration backup")
        backup_vm_config(
            vm_info['host'],
            vm_info['username'],
            vm_info['vm_dir'],
            args.out,
            vm_info['vm_name'],
            args.temp,
            args.compression,
            args.compression_level,
            args.hash_algo
        )

        # Backup each VMDK and its related files
        vmdk_count = 0
        for i, vmdk_path in enumerate(vm_info['disk_files'], 1):
            if vmdk_path.endswith('.vmdk'):  # Only backup VMDKs, skip ISOs
                vmdk_count += 1
                try:
                    if logger:
                        logger.log(f"Starting backup of disk {i}: {os.path.basename(vmdk_path)}")
                    backup_vmdk(
                        vm_info['host'],
                        vm_info['username'],
                        vmdk_path,
                        args.out,
                        vm_info['vm_name'],
                        i,
                        args.temp,
                        args.compression,
                        args.compression_level,
                        args.hash_algo
                    )
                except Exception as e:
                    if logger:
                        logger.log(f"Error backing up {vmdk_path}: {e}", "ERROR")
            else:
                if logger:
                    logger.log(f"Skipping non-VMDK file: {vmdk_path}")

        success_msg = f"Backup completed successfully! Backed up configuration + {vmdk_count} disk(s) to: {args.out}"
        if logger:
            logger.finalize("SUCCESS", success_msg)

    except Exception as e:
        error_msg = f"Backup failed: {str(e)}"
        if logger:
            logger.log(error_msg, "ERROR")
            logger.finalize("FAILED", error_msg)
        sys.exit(1)
    finally:
        if 'vm_info' in locals():
            cleanup(vm_info['host'], vm_info['username'], vm_info['vm_id'], args.temp)
        if 'lock_file' in locals():
            lock_file.close()
            
if __name__ == "__main__":
    main()