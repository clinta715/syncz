backupvm.py
This application assumes that the machine on which it is running, has access via pre-shared SSH keys, to all the VMWare hosts it accesses.  You will need to manually set this up yourself.

A Python-based utility to back up VMware virtual machines (VMs) directly over SSH/SSHFS.
It creates compressed archives of VM configuration files and virtual disk (.vmdk) files, along with integrity manifests containing file sizes and cryptographic hashes.
Features

    Connects to one or more VMware ESXi hosts via SSH

    Finds and backs up VM configuration (.vmx, .vmxf, .vmsd, .nvram) and disk files (.vmdk)

    Creates compressed archives with your choice of algorithm (zstd, gzip, bzip2, xz, or none)

    Handles multiple related VMDK split/flat files automatically

    Takes and removes VM snapshots for consistency

    Generates per-archive manifest files including:

        Archive name

        Archive size (bytes)

        Cryptographic hash (SHA-256 by default, configurable)

        Archive contents listing

Requirements

    Python 3.7+

    Installed tools on the backup host:

        ssh and sshfs

        tar and the chosen compression program (zstd, gzip, bzip2, or xz)

    Python packages: portalocker

Install requirements with:

pip install portalocker

Usage

Basic example:

./backupvm.py MyVM \
  --out /backups/vms \
  --hosts 10.0.0.10 10.0.0.11 \
  --username root

This will:

    Locate MyVM across the provided ESXi hosts

    Take a snapshot

    Back up VM configuration and VMDK files to /backups/vms

    Write integrity manifests (.manifest.txt) for each archive

    Remove the snapshot

Options
Option	Description
vm_name	Name (or partial name) of the VM to back up
--out DIR	Output directory for backups (must exist)
--hosts HOST [HOST ...]	One or more VMware host IPs
--username USER	SSH username (default: root)
--temp DIR	Temporary mount directory (default: /tmp/vmbackup_temp)
--compression {zstd,gzip,bzip2,xz,none}	Compression method (default: zstd)
--compression-level N	Compression level (depends on compressor)
--hash ALGO	Hash algorithm for manifests (default: sha256) — choices include: md5, sha1, sha256, sha512, blake2b, etc.
Example with custom options

./backupvm.py WebServer01 \
  --out /mnt/backup/vms \
  --hosts 192.168.1.10 \
  --compression gzip \
  --compression-level 9 \
  --hash sha512

This will create .tar.gz archives of the VM files, compressed at level 9, and generate .sha512.manifest.txt files with SHA-512 hashes.
Output

For each archive, a manifest file is written in the same directory. Example:

Archive: /backups/vms/WebServer01_disk1.tar.zst
Size: 1234567890 bytes
SHA256: 8a1f7a7b9c6e...

Contents:
-rw------- root/root 12345678 2025-08-21 10:00 disk1-flat.vmdk
-rw------- root/root   867530 2025-08-21 10:00 disk1.vmdk

Notes

    Make sure you have SSH key access set up to your VMware hosts.

    Backups require sufficient space in the --out directory.

    sshfs mounts are cleaned up automatically after backup.

Would you like me to also add a "Verify backup integrity" section in the README, showing how a user could re-check the manifests against the archives later?


ChatGPT can make mistakes. Check important info.
Generate hash and manifest

Sure thing 👍 — here’s a README.md you could ship alongside backupvm.py to explain what it does, how to use it, and the new manifest/hash features:
VMware VM Backup Tool (backupvm.py)

A Python-based utility to back up VMware virtual machines (VMs) directly over SSH/SSHFS.
It creates compressed archives of VM configuration files and virtual disk (.vmdk) files, along with integrity manifests containing file sizes and cryptographic hashes.
Features

    Connects to one or more VMware ESXi hosts via SSH

    Finds and backs up VM configuration (.vmx, .vmxf, .vmsd, .nvram) and disk files (.vmdk)

    Creates compressed archives with your choice of algorithm (zstd, gzip, bzip2, xz, or none)

    Handles multiple related VMDK split/flat files automatically

    Takes and removes VM snapshots for consistency

    Generates per-archive manifest files including:

        Archive name

        Archive size (bytes)

        Cryptographic hash (SHA-256 by default, configurable)

        Archive contents listing

Requirements

    Python 3.7+

    Installed tools on the backup host:

        ssh and sshfs

        tar and the chosen compression program (zstd, gzip, bzip2, or xz)

    Python packages: portalocker

Install requirements with:

pip install portalocker

Usage

Basic example:

./backupvm.py MyVM \
  --out /backups/vms \
  --hosts 10.0.0.10 10.0.0.11 \
  --username root

This will:

    Locate MyVM across the provided ESXi hosts

    Take a snapshot

    Back up VM configuration and VMDK files to /backups/vms

    Write integrity manifests (.manifest.txt) for each archive

    Remove the snapshot

Options
Option	Description
vm_name	Name (or partial name) of the VM to back up
--out DIR	Output directory for backups (must exist)
--hosts HOST [HOST ...]	One or more VMware host IPs
--username USER	SSH username (default: root)
--temp DIR	Temporary mount directory (default: /tmp/vmbackup_temp)
--compression {zstd,gzip,bzip2,xz,none}	Compression method (default: zstd)
--compression-level N	Compression level (depends on compressor)
--hash ALGO	Hash algorithm for manifests (default: sha256) — choices include: md5, sha1, sha256, sha512, blake2b, etc.
Example with custom options

./backupvm.py WebServer01 \
  --out /mnt/backup/vms \
  --hosts 192.168.1.10 \
  --compression gzip \
  --compression-level 9 \
  --hash sha512

This will create .tar.gz archives of the VM files, compressed at level 9, and generate .sha512.manifest.txt files with SHA-512 hashes.
Output

For each archive, a manifest file is written in the same directory. Example:

Archive: /backups/vms/WebServer01_disk1.tar.zst
Size: 1234567890 bytes
SHA256: 8a1f7a7b9c6e...

Contents:
-rw------- root/root 12345678 2025-08-21 10:00 disk1-flat.vmdk
-rw------- root/root   867530 2025-08-21 10:00 disk1.vmdk

Notes

    Make sure you have SSH key access set up to your VMware hosts.

    Backups require sufficient space in the --out directory.

    sshfs mounts are cleaned up automatically after backup.

Would you like me to also add a "Verify backup integrity" section in the README, showing how a user could re-check the manifests against the archives later?
