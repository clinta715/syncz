# VMware VM Backup Tool Documentation

## Overview

This Python script provides automated backup functionality for VMware virtual machines running on ESXi hosts. It creates consistent snapshots, backs up VM configuration files and disk images, and generates verification manifests with configurable compression and hashing options.

## Features

- **Snapshot-based backups**: Creates temporary snapshots for consistent backups
- **Multiple compression formats**: Support for zstd, gzip, bzip2, xz, or no compression
- **Integrity verification**: Generates manifest files with checksums
- **Multi-host search**: Searches across multiple ESXi hosts for VMs
- **Concurrent safety**: Uses file locking to prevent multiple simultaneous backups of the same VM
- **Comprehensive logging**: Structured logging with timestamps and status tracking
- **VMDK file discovery**: Automatically finds and backs up all related VMDK files (flat files, snapshots, etc.)

## Prerequisites

### System Requirements

- **Operating System**: Linux (tested on Ubuntu/Debian/CentOS)
- **Python**: Python 3.6 or higher
- **SSH Access**: Passwordless SSH access to VMware ESXi hosts
- **SSHFS**: For mounting remote filesystems
- **Network**: Network connectivity to ESXi hosts

### VMware ESXi Configuration

1. **Enable SSH** on your ESXi hosts:
   ```bash
   # On ESXi host console or via vSphere Client
   # Navigate to Host > Manage > Services > TSM-SSH > Start
   ```

2. **Set up SSH key authentication** (recommended):
   ```bash
   # On backup server
   ssh-keygen -t rsa -b 4096
   ssh-copy-id root@your-esxi-host
   ```

3. **Test SSH connectivity**:
   ```bash
   ssh root@your-esxi-host "vim-cmd vmsvc/getallvms"
   ```

## Installation

### 1. Install System Dependencies

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3 python3-pip sshfs openssh-client tar
```

#### CentOS/RHEL:
```bash
sudo yum install python3 python3-pip fuse-sshfs openssh-clients tar
# Or for newer versions:
sudo dnf install python3 python3-pip fuse-sshfs openssh-clients tar
```

### 2. Install Python Requirements

Create a `requirements.txt` file:
```txt
portalocker>=2.0.0
```

Install the Python dependencies:
```bash
# Using pip
pip3 install portalocker

# Or using requirements file
pip3 install -r requirements.txt

# For system-wide installation (may require sudo)
sudo pip3 install portalocker
```

### 3. Install Compression Tools (Optional)

Install additional compression tools based on your needs:

```bash
# Ubuntu/Debian
sudo apt install zstd gzip bzip2 xz-utils

# CentOS/RHEL
sudo yum install zstd gzip bzip2 xz
```

### 4. Download and Setup Script

```bash
# Download the script
wget https://example.com/backupvm.py
# Or copy from your source

# Make executable
chmod +x backupvm.py

# Optional: Move to system PATH
sudo cp backupvm.py /usr/local/bin/backupvm
```

## Usage

### Basic Syntax

```bash
./backupvm.py VM_NAME --out OUTPUT_DIR --hosts HOST1 [HOST2 ...]
```

### Required Arguments

- `VM_NAME`: Name or partial name of the VM to backup (case-insensitive partial matching)
- `--out`: Output directory where backup files will be stored (must exist)
- `--hosts`: One or more ESXi host IP addresses or hostnames

### Optional Arguments

- `--username`: SSH username for ESXi hosts (default: `root`)
- `--temp`: Temporary mount point directory (default: `/tmp/vmbackup_temp`)
- `--compression`: Compression method - `zstd`, `gzip`, `bzip2`, `xz`, `none` (default: `zstd`)
- `--compression-level`: Compression level (1-9 for most formats)
- `--hash`: Hash algorithm for manifests (default: `sha256`)
- `--log-dir`: Directory to write detailed log files

### Examples

#### Basic backup with default settings:
```bash
./backupvm.py "web-server" --out /backup/vms --hosts 192.168.1.100
```

#### Backup with custom compression and logging:
```bash
./backupvm.py "database-prod" \
  --out /backup/vms \
  --hosts 192.168.1.100 192.168.1.101 \
  --compression gzip \
  --compression-level 6 \
  --log-dir /var/log/vmbackup \
  --hash sha512
```

#### Multiple hosts with different username:
```bash
./backupvm.py "test-vm" \
  --out /backup/test \
  --hosts esxi-host1.local esxi-host2.local \
  --username admin \
  --temp /mnt/vmbackup_temp
```

#### No compression (fastest backup):
```bash
./backupvm.py "large-vm" \
  --out /fast-storage/backups \
  --hosts 10.0.0.100 \
  --compression none
```

## Output Files

The script creates several files in the output directory:

### Backup Archives
- `{VM_NAME}_config.tar.{ext}`: VM configuration files (VMX, VMXF, VMSD, NVRAM)
- `{VM_NAME}_disk1.tar.{ext}`: First disk and related VMDK files
- `{VM_NAME}_disk2.tar.{ext}`: Second disk (if exists)
- ... (additional disks as needed)

### Manifest Files
- `{VM_NAME}_config.tar.{ext}.{hash}.manifest.txt`: Configuration archive manifest
- `{VM_NAME}_disk1.tar.{ext}.{hash}.manifest.txt`: Disk archive manifests

### Example Output Structure
```
/backup/vms/
├── web-server_config.tar.zst
├── web-server_config.tar.zst.sha256.manifest.txt
├── web-server_disk1.tar.zst
├── web-server_disk1.tar.zst.sha256.manifest.txt
├── web-server_disk2.tar.zst
└── web-server_disk2.tar.zst.sha256.manifest.txt
```

### Manifest File Contents
```
Archive: /backup/vms/web-server_config.tar.zst
Size: 1234567 bytes
SHA256: abc123def456...

Contents:
web-server.vmx    4096 bytes
web-server.vmxf   512 bytes
web-server.nvram  8684 bytes
```

## Log Files

When `--log-dir` is specified, detailed log files are created with structured headers for easy parsing:

### Log File Format
- Filename: `vmbackup_{VM_NAME}_{HOST}_{TIMESTAMP}.log`
- Location: `{LOG_DIR}/vmbackup_web-server_192-168-1-100_20240826_143022.log`

### Log Structure
```
BACKUP_LOG_V1|2024-08-26T14:30:22|web-server|192.168.1.100|SUCCESS|0|0
================================================================================
VMware VM Backup Log
Start Time: 2024-08-26 14:30:22
VM Name: web-server
Host: 192.168.1.100
Log File: /var/log/vmbackup/vmbackup_web-server_192-168-1-100_20240826_143022.log
================================================================================

[14:30:22] INFO: Starting VMware VM backup process
[14:30:23] INFO: Searching for VM 'web-server' across 1 hosts
...
[14:35:45] INFO: Backup completed successfully! Backed up configuration + 2 disk(s)

================================================================================
BACKUP SUMMARY
Status: SUCCESS
Duration: 323.2 seconds
Warnings: 0
Errors: 0
End Time: 2024-08-26 14:35:45
```

## Restore Process

### Extracting Archives
```bash
# Extract configuration
tar -xf web-server_config.tar.zst

# Extract disk files
tar -xf web-server_disk1.tar.zst
```

### Verification
```bash
# Verify archive integrity using manifest
sha256sum web-server_config.tar.zst
# Compare with value in manifest file

# List archive contents
tar -tvf web-server_disk1.tar.zst
```

## Troubleshooting

### Common Issues

#### SSH Connection Problems
```bash
# Test SSH connectivity
ssh -o ConnectTimeout=10 root@esxi-host "vim-cmd vmsvc/getallvms"

# Check SSH keys
ssh-add -l
```

#### Permission Issues
```bash
# Ensure backup user can write to output directory
ls -la /backup/vms/
chmod 755 /backup/vms/

# Check temporary directory permissions
ls -la /tmp/vmbackup_temp/
```

#### SSHFS Mount Issues
```bash
# Check if sshfs is installed
which sshfs

# Test manual mount
sshfs root@esxi-host:/vmfs/volumes /tmp/test-mount

# Check for orphaned mounts
mount | grep sshfs
fusermount -u /path/to/stuck/mount
```

#### VM Not Found
```bash
# Verify VM name and check ESXi host directly
ssh root@esxi-host "vim-cmd vmsvc/getallvms | grep -i vm-name"

# Check datastore accessibility
ssh root@esxi-host "ls -l /vmfs/volumes/"
```

### Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Another backup of VM 'x' is already in progress` | Lock file exists | Wait for other backup to finish or remove `/tmp/backupvm_*.lock` |
| `VM 'x' not found or files missing` | VM doesn't exist or inaccessible | Check VM name and host connectivity |
| `Failed to mount VMDK directory` | SSHFS mount failed | Check SSH connectivity and permissions |
| `Could not get datastore mapping` | ESXi host access issue | Verify SSH access and ESXi host status |

## Performance Considerations

### Compression Trade-offs
- **zstd**: Best balance of speed and compression (recommended)
- **gzip**: Good compatibility, moderate speed
- **xz**: Best compression ratio, slowest
- **none**: Fastest, largest files

### Network and Storage
- Use gigabit or faster network connections
- Consider compression level vs. network speed
- Ensure sufficient free space (2-3x VM size recommended)
- Use fast storage for temporary directory

### Resource Usage
- CPU: Compression is CPU-intensive
- Memory: Minimal memory usage
- Network: High bandwidth during backup
- Storage: Temporary space for mounts

## Automation and Scheduling

### Cron Example
```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backupvm "prod-server" --out /backup/daily --hosts 192.168.1.100 --log-dir /var/log/vmbackup 2>&1

# Weekly backup with higher compression
0 1 * * 0 /usr/local/bin/backupvm "database" --out /backup/weekly --hosts 192.168.1.100 192.168.1.101 --compression xz --compression-level 9 --log-dir /var/log/vmbackup 2>&1
```

### Backup Script Wrapper
```bash
#!/bin/bash
# backup-all-vms.sh

VMS=("web-server" "database-prod" "app-server")
HOSTS="192.168.1.100 192.168.1.101"
OUTPUT_DIR="/backup/$(date +%Y-%m-%d)"

mkdir -p "$OUTPUT_DIR"

for vm in "${VMS[@]}"; do
    echo "Backing up $vm..."
    /usr/local/bin/backupvm "$vm" \
        --out "$OUTPUT_DIR" \
        --hosts $HOSTS \
        --log-dir /var/log/vmbackup \
        --compression zstd \
        --compression-level 3
done
```

## Security Considerations

1. **SSH Key Security**: Use dedicated SSH keys with limited scope
2. **File Permissions**: Restrict access to backup directories (700/750)
3. **Network Security**: Use VPN or isolated backup networks
4. **Log Security**: Protect log files from unauthorized access
5. **Backup Encryption**: Consider encrypting backup archives for long-term storage

## Version Information

- **Script Version**: Compatible with Python 3.6+
- **VMware Compatibility**: ESXi 6.0+, vSphere 6.0+
- **Tested Platforms**: Ubuntu 18.04+, CentOS 7+, Debian 9+

For support and updates, check the project repository or contact your system administrator.