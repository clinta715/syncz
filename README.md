# VMware Backup Tools

A comprehensive suite of tools for backing up VMware virtual machines and generating beautiful reporting dashboards.

## 🚀 Features

### BackupVM Script (`backupvm.py`)
- **Automated VM Discovery**: Find VMs across multiple ESXi hosts by partial name matching
- **Snapshot-based Backups**: Creates temporary snapshots for consistent backups
- **Smart Compression**: Multiple compression formats (zstd, gzip, bzip2, xz, or none)
- **Integrity Verification**: Automatic manifest generation with configurable hash algorithms
- **Comprehensive Logging**: Structured logging with machine-readable headers for monitoring
- **Multi-disk Support**: Handles complex VM configurations with multiple disks
- **Related File Detection**: Automatically finds and backs up all related VMDK files (flat files, snapshots, etc.)
- **Concurrent Safety**: File locking prevents multiple backups of the same VM

### Report Generator (`backup_report_generator.py`)
- **Interactive Calendar View**: Visual calendar showing backup activity with color-coded status indicators
- **Performance Analytics**: Success rates, trends, and statistics for each VM
- **Modern Web UI**: Beautiful, responsive HTML reports with glassmorphism design
- **Multi-host Support**: Tracks backups across multiple ESXi hosts
- **Historical Analysis**: View backup patterns over time
- **Mobile Friendly**: Responsive design works on all devices

## 📋 Requirements

### System Dependencies
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip sshfs openssh-client

# CentOS/RHEL/Rocky Linux
sudo yum install python3 python3-pip fuse-sshfs openssh-clients

# Or with dnf
sudo dnf install python3 python3-pip fuse-sshfs openssh-clients
```

### Python Dependencies
```bash
pip3 install portalocker
```

### VMware Host Setup
Ensure SSH key authentication is configured for your ESXi hosts:
```bash
# Generate SSH key pair (if not already done)
ssh-keygen -t rsa -b 4096

# Copy public key to ESXi hosts
ssh-copy-id root@your-esxi-host.com
```

## 🛠️ Installation

1. **Clone or download the scripts**:
   ```bash
   curl -O https://path-to-your/backupvm.py
   curl -O https://path-to-your/backup_report_generator.py
   chmod +x backupvm.py backup_report_generator.py
   ```

2. **Create backup directories**:
   ```bash
   sudo mkdir -p /mnt/backup /var/log/backups
   sudo chown $USER:$USER /mnt/backup /var/log/backups
   ```

## 📖 Usage

### BackupVM Script

#### Basic Backup
```bash
./backupvm.py MyVM --out /mnt/backup/MyVM --hosts 192.168.1.100
```

#### Full-featured Backup with Logging
```bash
./backupvm.py WebServer --out /mnt/backup/webserver \
  --hosts 192.168.1.100 192.168.1.101 \
  --compression zstd \
  --compression-level 3 \
  --hash sha256 \
  --log-dir /var/log/backups
```

#### Command Line Options
```bash
./backupvm.py VM_NAME --out OUTPUT_DIR --hosts HOST1 [HOST2 ...] [OPTIONS]

Required Arguments:
  VM_NAME                    VM name to search (partial match supported)
  --out OUTPUT_DIR          Output directory (must exist)
  --hosts HOST1 [HOST2...]  VMware host IPs to search

Optional Arguments:
  --temp TEMP_DIR           Temporary mount point (default: /tmp/vmbackup_temp)
  --username USERNAME       SSH username (default: root)
  --compression FORMAT      Compression: zstd|gzip|bzip2|xz|none (default: zstd)
  --compression-level N     Compression level (1-22 for zstd, 1-9 for others)
  --hash ALGORITHM         Hash algorithm for manifests (default: sha256)
  --log-dir LOG_DIR        Directory for log files (optional)
```

### Report Generator

#### Generate HTML Report
```bash
./backup_report_generator.py /var/log/backups
```

#### Custom Output Location
```bash
./backup_report_generator.py /var/log/backups --output /var/www/html/backup_report.html
```

#### Command Line Options
```bash
./backup_report_generator.py LOG_DIR [OPTIONS]

Required Arguments:
  LOG_DIR                   Directory containing backup log files

Optional Arguments:
  --output FILE, -o FILE    Output HTML file (default: backup_report.html)
```

## 📊 Log File Format

### Structured Header
Each log file starts with a machine-readable header for easy parsing:
```
BACKUP_LOG_V1|2025-08-22T14:30:15.123456|WebServer01|192.168.1.100|SUCCESS|1|0
```

**Format**: `VERSION|TIMESTAMP|VM_NAME|HOST|STATUS|WARNING_COUNT|ERROR_COUNT`

### Status Codes
- **SUCCESS**: Backup completed without errors
- **FAILED**: Backup failed with errors
- **RUNNING**: Initial state (updated on completion)

### Log File Naming
```
vmbackup_{VM_NAME}_{HOST}_{TIMESTAMP}.log

Example: vmbackup_WebServer01_192_168_1_100_20250822_143015.log
```

## 🎨 Report Features

### Interactive Calendar
- **Color-coded dots**: 🟢 Success, 🔴 Failed, 🟡 Warnings
- **Hover tooltips**: VM name, host, status, warning details
- **Multi-month view**: Historical backup activity
- **Responsive design**: Works on desktop and mobile

### Statistics Dashboard
- Overall success rate percentage
- Total successful/failed backups
- Warning and error counts
- Recent activity (last 7 days)
- Unique VM count
- Individual VM performance cards

### VM Performance Cards
- **Green (≥90%)**: Excellent performance
- **Yellow (70-89%)**: Good performance  
- **Red (<70%)**: Needs attention

## 💡 Example Workflows

### Daily Backup Script
```bash
#!/bin/bash
# daily_backup.sh

LOG_DIR="/var/log/backups"
BACKUP_BASE="/mnt/backup"
HOSTS="192.168.1.100 192.168.1.101"

# List of VMs to backup
VMS=("WebServer01" "Database01" "FileServer01")

for vm in "${VMS[@]}"; do
    echo "Backing up $vm..."
    ./backupvm.py "$vm" \
        --out "$BACKUP_BASE/$vm" \
        --hosts $HOSTS \
        --compression zstd \
        --compression-level 3 \
        --log-dir "$LOG_DIR"
done

# Generate report
./backup_report_generator.py "$LOG_DIR" \
    --output "/var/www/html/backup_dashboard.html"

echo "Backup cycle complete. Report available at backup_dashboard.html"
```

### Weekly Report Generation
```bash
#!/bin/bash
# weekly_report.sh

./backup_report_generator.py /var/log/backups \
    --output "/var/www/html/weekly_backup_report_$(date +%Y%m%d).html"

echo "Weekly report generated: weekly_backup_report_$(date +%Y%m%d).html"
```

## 🔧 Advanced Configuration

### Compression Performance Comparison
| Format | Speed | Compression Ratio | CPU Usage | Recommended Use |
|--------|-------|------------------|-----------|-----------------|
| `none` | Fastest | 1.0x | Minimal | Fast networks, CPU-limited |
| `gzip` | Fast | ~3x | Low | General purpose |
| `zstd` | Fast | ~3.5x | Medium | **Recommended default** |
| `bzip2` | Slow | ~4x | High | Maximum compression |
| `xz` | Slowest | ~4.5x | Very High | Archive storage |

### Hash Algorithm Options
- **SHA256** (default): Good balance of security and performance
- **SHA1**: Faster, less secure (legacy compatibility)
- **SHA512**: More secure, slower
- **MD5**: Fastest, least secure (not recommended)

## 🔍 Monitoring Integration

### Parsing Log Headers for Alerting
```python
#!/usr/bin/env python3
# Simple monitoring script

import glob
import sys
from datetime import datetime, timedelta

def check_recent_backups():
    log_files = glob.glob('/var/log/backups/vmbackup_*.log')
    failed_backups = []
    
    # Check backups from last 24 hours
    yesterday = datetime.now() - timedelta(days=1)
    
    for log_file in log_files:
        with open(log_file, 'r') as f:
            header = f.readline().strip()
            
        if header.startswith('BACKUP_LOG_V1|'):
            parts = header.split('|')
            timestamp = datetime.fromisoformat(parts[1])
            vm_name = parts[2]
            status = parts[4]
            
            if timestamp >= yesterday and status == 'FAILED':
                failed_backups.append((vm_name, timestamp))
    
    if failed_backups:
        print("❌ ALERT: Recent backup failures:")
        for vm, time in failed_backups:
            print(f"  - {vm} failed at {time}")
        sys.exit(1)
    else:
        print("✅ All recent backups successful")

if __name__ == "__main__":
    check_recent_backups()
```

### Cron Job Setup
```bash
# Edit crontab
crontab -e

# Daily backup at 2 AM
0 2 * * * /home/user/daily_backup.sh >> /var/log/backup_cron.log 2>&1

# Weekly report on Sunday at 6 AM
0 6 * * 0 /home/user/weekly_report.sh

# Check for failures every hour
0 * * * * /home/user/check_backups.py
```

## 🛡️ Security Considerations

1. **SSH Key Management**: Use dedicated SSH keys for backup operations
2. **File Permissions**: Ensure backup directories have appropriate permissions
3. **Network Security**: Use firewall rules to restrict SSH access
4. **Log Rotation**: Implement log rotation to prevent disk space issues

```bash
# Setup log rotation for backup logs
sudo tee /etc/logrotate.d/vmbackup << EOF
/var/log/backups/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

## 🐛 Troubleshooting

### Common Issues

#### "VM not found"
- Verify VM name spelling (partial matches supported)
- Check SSH connectivity to ESXi hosts
- Ensure VM is registered and visible in vCenter/ESXi

#### "Mount failed"
- Install `sshfs`: `sudo apt install sshfs`
- Check filesystem permissions on temp directory
- Verify ESXi host allows SSH connections

#### "Permission denied"
- Ensure SSH key authentication is working
- Check that backup output directory exists and is writable
- Verify temp directory permissions

#### "Compression program not found"
- Install compression tools: `sudo apt install zstd gzip bzip2 xz-utils`
- Use `--compression none` as fallback

### Debug Mode
Add verbose SSH output for debugging connectivity:
```bash
ssh -vvv root@esxi-host "vim-cmd vmsvc/getallvms"
```

### Log Analysis
```bash
# Check recent backup status
grep "BACKUP_LOG_V1" /var/log/backups/*.log | tail -10

# Find all failed backups
grep "FAILED" /var/log/backups/*.log

# Monitor active backup
tail -f /var/log/backups/vmbackup_*.log
```

## 📈 Performance Tips

1. **Use local temp directories** for better SSHFS performance
2. **Adjust compression levels** based on your network vs. CPU constraints  
3. **Run backups during low-activity periods** to reduce impact
4. **Use dedicated backup network** if possible
5. **Monitor disk space** on both source and destination

## 🤝 Contributing

Feel free to submit issues, feature requests, or pull requests. Some areas for enhancement:

- Incremental backup support
- Email notification integration
- Backup verification and restore testing
- Integration with backup rotation policies
- Support for vCenter API instead of direct ESXi SSH

## 📄 License

This project is released under the MIT License. Feel free to modify and distribute according to your needs.

---

**Happy Backing Up!** 🎉

For questions or support, please check the troubleshooting section or create an issue in the project repository.
