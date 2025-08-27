#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import portalocker
import hashlib
import configparser
import tempfile
import json
import tempfile
from datetime import datetime
from pathlib import Path

# Supported compression programs and their extensions
COMPRESSION_FORMATS = {
    'zstd': {'ext': '.sql.zst', 'cmd': 'zstd', 'decompress_flag': '-d'},
    'gzip': {'ext': '.sql.gz', 'cmd': 'gzip', 'decompress_flag': '-d'},
    'bzip2': {'ext': '.sql.bz2', 'cmd': 'bzip2', 'decompress_flag': '-d'},
    'xz': {'ext': '.sql.xz', 'cmd': 'xz', 'decompress_flag': '-d'},
    'none': {'ext': '.sql', 'cmd': 'cat', 'decompress_flag': ''},
}

class BackupLogger:
    def __init__(self, log_dir=None, db_name="unknown", host="unknown"):
        self.log_dir = log_dir
        self.db_name = db_name
        self.host = host
        self.start_time = datetime.now()
        self.log_file = None
        self.log_path = None
        self.errors = []
        self.warnings = []
        
        if log_dir:
            self._create_log_file()
    
    def _create_log_file(self):
        """Create log file with timestamp and database info in filename"""
        
        if not self.log_dir:
            return  # nothing to do if no log dir
        
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
                
        # Sanitize names for filename
        safe_db_name = re.sub(r'[^\w\-_.]', '_', self.db_name)
        safe_host = re.sub(r'[^\w\-_.]', '_', self.host)
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        filename = f"mysqlbackup_{safe_db_name}_{safe_host}_{timestamp}.log"
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
        header = f"MYSQL_BACKUP_LOG_V1|{self.start_time.isoformat()}|{self.db_name}|{self.host}|RUNNING|0|0"
        self.log_file.write(f"{header}\n")
        self.log_file.write("="*80 + "\n")
        
        # Human readable header
        self.log_file.write(f"MySQL Database Backup Log\n")
        self.log_file.write(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write(f"Database: {self.db_name}\n")
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
        
        if self.log_file:
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
            # Only do this if we have a log_path (not None)
            if self.log_path:
                try:
                    with open(self.log_path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                    
                    # Replace the first line with updated status
                    lines = current_content.split('\n')
                    if lines and lines[0].startswith("MYSQL_BACKUP_LOG_V1|"):
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
            
            if self.log_path:
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

def generate_manifest(backup_path, output_dir, algo='sha256', db_info=None):
    """Generate manifest file with backup metadata"""
    manifest_path = os.path.join(
        output_dir,
        os.path.basename(backup_path) + f".{algo}.manifest.txt"
    )
    
    with open(manifest_path, 'w') as mf:
        size = os.path.getsize(backup_path)
        digest = compute_hash(backup_path, algo)
        
        mf.write(f"MySQL Backup Manifest\n")
        mf.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        mf.write(f"="*50 + "\n\n")
        
        mf.write(f"Backup File: {backup_path}\n")
        mf.write(f"Size: {size:,} bytes ({size / (1024**3):.2f} GB)\n")
        mf.write(f"{algo.upper()}: {digest}\n\n")
        
        if db_info:
            mf.write(f"Database Information:\n")
            mf.write(f"Host: {db_info.get('host', 'N/A')}\n")
            mf.write(f"Port: {db_info.get('port', 'N/A')}\n")
            mf.write(f"Database: {db_info.get('database', 'N/A')}\n")
            mf.write(f"MySQL Version: {db_info.get('version', 'N/A')}\n")
            mf.write(f"Backup Type: {db_info.get('backup_type', 'N/A')}\n")
            mf.write(f"Character Set: {db_info.get('charset', 'N/A')}\n\n")
        
        # Try to get basic info about the SQL dump
        try:
            if backup_path.endswith(('.gz', '.bz2', '.xz', '.zst')):
                # For compressed files, just note it's compressed
                mf.write(f"Content: Compressed SQL dump\n")
            else:
                # For uncompressed files, get line count
                with open(backup_path, 'r') as f:
                    line_count = sum(1 for _ in f)
                mf.write(f"SQL Lines: {line_count:,}\n")
        except Exception as e:
            mf.write(f"Content Analysis: Failed - {e}\n")

    # Only log if logger is initialized
    if logger:
        logger.log(f"Manifest written to {manifest_path}")
    else:
        print(f"Manifest written to: {manifest_path}")
    return manifest_path

def parse_args():
    parser = argparse.ArgumentParser(description='MySQL Database Backup Tool')
    parser.add_argument('database', nargs='?', help='Database name to backup (optional for --all)')
    parser.add_argument('--out', required=True, help='Output directory (must exist)')
    parser.add_argument('--host', default='localhost', help='MySQL host (default: localhost)')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port (default: 3306)')
    parser.add_argument('--user', help='MySQL username')
    parser.add_argument('--password', help='MySQL password (use --password-file for security)')
    parser.add_argument('--password-file', help='File containing MySQL password')
    parser.add_argument('--defaults-file', help='MySQL defaults file (recommended)')
    parser.add_argument('--compression', choices=COMPRESSION_FORMATS.keys(), default='zstd',
                        help='Compression method to use (default: zstd)')
    parser.add_argument('--compression-level', type=int, help='Compression level (optional, program-specific)')
    parser.add_argument('--hash', dest='hash_algo', default='sha256',
                    choices=hashlib.algorithms_available,
                    help='Hash algorithm to use for manifests (default: sha256)')
    parser.add_argument('--log-dir', help='Directory to write log files (optional)')
    parser.add_argument('--all', action='store_true', help='Backup all databases (except system DBs)')
    parser.add_argument('--include-routines', action='store_true', help='Include stored procedures and functions')
    parser.add_argument('--include-triggers', action='store_true', help='Include triggers')
    parser.add_argument('--single-transaction', action='store_true', help='Use single transaction for consistency')
    parser.add_argument('--lock-tables', action='store_true', help='Lock all tables during backup')
    parser.add_argument('--flush-logs', action='store_true', help='Flush logs before backup')
    parser.add_argument('--parallel', type=int, default=1, help='Number of parallel backups (for --all)')
    parser.add_argument('--exclude', nargs='*', default=['information_schema', 'performance_schema', 'mysql', 'sys'],
                        help='Databases to exclude when using --all')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be backed up without doing it')
    
    args = parser.parse_args()
    
    # Validation
    if not args.all and not args.database:
        parser.error("Either specify a database name or use --all flag")
    
    if args.password and args.password_file:
        parser.error("Cannot specify both --password and --password-file")
    
    return args

def get_mysql_connection_args(args):
    """Build MySQL connection arguments"""
    conn_args = []
    
    if args.defaults_file:
        conn_args.extend(['--defaults-file', args.defaults_file])
    else:
        conn_args.extend(['--host', args.host, '--port', str(args.port)])
        
        if args.user:
            conn_args.extend(['--user', args.user])
        
        if args.password:
            conn_args.append(f'--password={args.password}')
        elif args.password_file:
            try:
                with open(args.password_file, 'r') as f:
                    password = f.read().strip()
                conn_args.append(f'--password={password}')
            except Exception as e:
                raise ValueError(f"Could not read password file {args.password_file}: {e}")
    
    return conn_args

def test_mysql_connection(conn_args):
    """Test MySQL connection and get server info"""
    try:
        cmd = ['mysql'] + conn_args + ['--execute', 'SELECT VERSION(), @@character_set_server;']
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2:
            data_line = lines[1].split('\t')
            if len(data_line) >= 2:
                return {
                    'version': data_line[0],
                    'charset': data_line[1]
                }
        
        return {'version': 'Unknown', 'charset': 'Unknown'}
        
    except subprocess.CalledProcessError as e:
        raise ValueError(f"MySQL connection failed: {e.stderr.strip()}")

def get_database_list(conn_args, exclude_dbs=None):
    """Get list of all databases"""
    exclude_dbs = exclude_dbs or []
    
    try:
        cmd = ['mysql'] + conn_args + ['--execute', 'SHOW DATABASES;']
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        databases = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            db_name = line.strip()
            if db_name and db_name not in exclude_dbs:
                databases.append(db_name)
        
        return databases
        
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to get database list: {e.stderr.strip()}")

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

def backup_database(db_name, conn_args, output_dir, compression_format, compression_level=None, 
                   include_routines=False, include_triggers=False, single_transaction=False,
                   lock_tables=False, flush_logs=False, hash_algo='sha256', server_info=None):
    """Backup a single database"""
    
    # Build output filename
    compress_info = COMPRESSION_FORMATS[compression_format]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"{db_name}_{timestamp}{compress_info['ext']}")
    
    # Only log if logger is initialized
    if logger:
        logger.log(f"Starting backup of database '{db_name}' to {output_file}")
    else:
        print(f"Starting backup of database '{db_name}' to {output_file}")
    
    # Build mysqldump command
    dump_cmd = ['mysqldump'] + conn_args
    
    # Add mysqldump options
    dump_cmd.extend([
        '--no-autocommit',
        '--default-character-set=utf8mb4',
        '--hex-blob',  # Use hex notation for binary data
        '--column-statistics=0'  # Avoid issues with MySQL 8.0
    ])
    
    if single_transaction:
        dump_cmd.append('--single-transaction')
    
    if lock_tables:
        dump_cmd.append('--lock-tables')
    else:
        dump_cmd.append('--skip-lock-tables')
    
    if flush_logs:
        dump_cmd.append('--flush-logs')
    
    if include_routines:
        dump_cmd.append('--routines')
    
    if include_triggers:
        dump_cmd.append('--triggers')
    else:
        dump_cmd.append('--skip-triggers')
    
    # Add database name
    dump_cmd.append(db_name)
    
    # Set up compression
    if compression_format == 'none':
        # Direct output to file
        try:
            with open(output_file, 'w') as f:
                result = subprocess.run(dump_cmd, check=True, stdout=f, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"mysqldump failed for {db_name}: {e.stderr.strip()}")
    else:
        # Pipe through compression
        try:
            compress_cmd = get_compression_command(compression_format, compression_level)
            
            # Run mysqldump | compress > file
            dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            compress_proc = subprocess.Popen(compress_cmd.split(), stdin=dump_proc.stdout, 
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Allow dump_proc to receive SIGPIPE if compress_proc exits
            if dump_proc.stdout:
                dump_proc.stdout.close()
            
            with open(output_file, 'wb') as f:
                # Check if compress_proc.stdout is not None before reading
                if compress_proc.stdout:
                    while True:
                        chunk = compress_proc.stdout.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            
            # Wait for processes to complete
            dump_returncode = dump_proc.wait()
            compress_returncode = compress_proc.wait()
            
            if dump_returncode != 0:
                _, dump_stderr = dump_proc.communicate()
                raise ValueError(f"mysqldump failed for {db_name}: {dump_stderr.strip()}")
            
            if compress_returncode != 0:
                _, compress_stderr = compress_proc.communicate()
                raise ValueError(f"Compression failed for {db_name}: {compress_stderr.strip()}")
                
        except Exception as e:
            # Clean up partial file on error
            if os.path.exists(output_file):
                os.remove(output_file)
            raise
    
    # Get file size for logging
    file_size = os.path.getsize(output_file)
    # Only log if logger is initialized
    if logger:
        logger.log(f"Database '{db_name}' backed up successfully ({file_size:,} bytes)")
    else:
        print(f"Database '{db_name}' backed up successfully ({file_size:,} bytes)")
    
    # Generate manifest
    db_info = {
        'host': conn_args[conn_args.index('--host') + 1] if '--host' in conn_args else 'localhost',
        'port': conn_args[conn_args.index('--port') + 1] if '--port' in conn_args else '3306',
        'database': db_name,
        'backup_type': f"mysqldump ({'compressed' if compression_format != 'none' else 'uncompressed'})",
        'version': server_info.get('version', 'Unknown') if server_info else 'Unknown',
        'charset': server_info.get('charset', 'Unknown') if server_info else 'Unknown'
    }
    
    manifest_path = generate_manifest(output_file, output_dir, hash_algo, db_info)
    
    return {
        'database': db_name,
        'backup_file': output_file,
        'manifest_file': manifest_path,
        'size': file_size
    }

import shutil

def check_required_programs(args):
    """Ensure mysql, mysqldump, and compression tools are available in PATH"""
    required = ['mysql', 'mysqldump']

    # Add compression tool unless using "none"
    if args.compression != 'none':
        required.append(COMPRESSION_FORMATS[args.compression]['cmd'])

    missing = []
    for prog in required:
        if shutil.which(prog) is None:
            missing.append(prog)

    if missing:
        raise EnvironmentError(
            f"Missing required external programs: {', '.join(missing)}\n"
            "Please install them and ensure they are available in your PATH."
        )

def main():
    global logger
    args = parse_args()

    try:
        check_required_programs(args)
    except EnvironmentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize logger early
    logger = BackupLogger(args.log_dir, args.database or "all_databases", args.host)

    # Lock based on database name or "all" for --all flag
    db_identifier = args.database if args.database else "all_databases"
    safe_db_name = re.sub(r'\W+', '_', db_identifier)
    # lockfile_path = f'/tmp/mysqlbackup_{safe_db_name}_{args.host}.lock'

    lockfile_path = os.path.join(
        tempfile.gettempdir(),
        f"mysqlbackup_{safe_db_name}_{args.host}.lock"
    )

    try:
        lock_file = open(lockfile_path, 'w')
        portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.exceptions.LockException:
        error_msg = f"Another backup of database '{db_identifier}' on {args.host} is already in progress. Exiting."
        if logger:
            logger.log(error_msg, "ERROR")
            logger.finalize("FAILED", error_msg)
        else:
            print(error_msg, file=sys.stderr)
        sys.exit(1)

    try:
        if logger:
            logger.log("Starting MySQL database backup process")
            logger.log(f"Target: {args.database if args.database else 'All databases'}")
            logger.log(f"Host: {args.host}:{args.port}")
            logger.log(f"Output directory: {args.out}")
            logger.log(f"Compression: {args.compression}" + 
                      (f" (level {args.compression_level})" if args.compression_level else ""))
            logger.log(f"Hash algorithm: {args.hash_algo}")
        else:
            print("Starting MySQL database backup process")
            print(f"Target: {args.database if args.database else 'All databases'}")
            print(f"Host: {args.host}:{args.port}")
            print(f"Output directory: {args.out}")
            print(f"Compression: {args.compression}" + 
                  (f" (level {args.compression_level})" if args.compression_level else ""))
            print(f"Hash algorithm: {args.hash_algo}")
        
        # Verify output directory exists
        if not os.path.exists(args.out):
            raise ValueError(f"Output directory {args.out} does not exist")

        # Test MySQL connection and get server info
        conn_args = get_mysql_connection_args(args)
        if logger:
            logger.log("Testing MySQL connection...")
        else:
            print("Testing MySQL connection...")
        server_info = test_mysql_connection(conn_args)
        if logger:
            logger.log(f"Connected to MySQL {server_info['version']} (charset: {server_info['charset']})")
        else:
            print(f"Connected to MySQL {server_info['version']} (charset: {server_info['charset']})")

        # Determine which databases to backup
        if args.all:
            databases = get_database_list(conn_args, args.exclude)
            if logger:
                logger.log(f"Found {len(databases)} databases to backup: {', '.join(databases)}")
            else:
                print(f"Found {len(databases)} databases to backup: {', '.join(databases)}")
        else:
            databases = [args.database]
            if logger:
                logger.log(f"Backing up single database: {args.database}")
            else:
                print(f"Backing up single database: {args.database}")

        if args.dry_run:
            if logger:
                logger.log("DRY RUN - Would backup the following databases:")
                for db in databases:
                    logger.log(f"  - {db}")
                logger.finalize("SUCCESS", "Dry run completed successfully")
            else:
                print("DRY RUN - Would backup the following databases:")
                for db in databases:
                    print(f"  - {db}")
                # Create a temporary logger just for finalizing in dry run
                temp_logger = BackupLogger(args.log_dir, args.database or "all_databases", args.host)
                temp_logger.finalize("SUCCESS", "Dry run completed successfully")
            return

        # Perform backups
        backup_results = []
        total_size = 0
        
        if args.parallel > 1 and len(databases) > 1:
            if logger:
                logger.log(f"Starting parallel backup with {args.parallel} workers")
            else:
                print(f"Starting parallel backup with {args.parallel} workers")
            
            with ThreadPoolExecutor(max_workers=args.parallel) as executor:
                # Submit all backup tasks
                future_to_db = {
                    executor.submit(
                        backup_database, db, conn_args, args.out, args.compression,
                        args.compression_level, args.include_routines, args.include_triggers,
                        args.single_transaction, args.lock_tables, args.flush_logs,
                        args.hash_algo, server_info
                    ): db for db in databases
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_db):
                    db = future_to_db[future]
                    try:
                        result = future.result()
                        backup_results.append(result)
                        total_size += result['size']
                        if logger:
                            logger.log(f"Completed backup of {db}")
                        else:
                            print(f"Completed backup of {db}")
                    except Exception as e:
                        if logger:
                            logger.log(f"Failed to backup {db}: {e}", "ERROR")
                        else:
                            print(f"Failed to backup {db}: {e}", file=sys.stderr)
        else:
            # Sequential backup
            for db in databases:
                try:
                    result = backup_database(
                        db, conn_args, args.out, args.compression,
                        args.compression_level, args.include_routines, args.include_triggers,
                        args.single_transaction, args.lock_tables, args.flush_logs,
                        args.hash_algo, server_info
                    )
                    backup_results.append(result)
                    total_size += result['size']
                except Exception as e:
                    if logger:
                        logger.log(f"Failed to backup {db}: {e}", "ERROR")
                    else:
                        print(f"Failed to backup {db}: {e}", file=sys.stderr)

        # Generate summary
        if backup_results:
            if logger:
                logger.log(f"\nBackup Summary:")
                logger.log(f"Successfully backed up {len(backup_results)} database(s)")
                logger.log(f"Total backup size: {total_size:,} bytes ({total_size / (1024**3):.2f} GB)")
                logger.log(f"Files written to: {args.out}")
                
                for result in backup_results:
                    logger.log(f"  - {result['database']}: {result['size']:,} bytes")
            else:
                print(f"\nBackup Summary:")
                print(f"Successfully backed up {len(backup_results)} database(s)")
                print(f"Total backup size: {total_size:,} bytes ({total_size / (1024**3):.2f} GB)")
                print(f"Files written to: {args.out}")
                
                for result in backup_results:
                    print(f"  - {result['database']}: {result['size']:,} bytes")

            success_msg = f"Backup completed successfully! {len(backup_results)} database(s) backed up to: {args.out}"
            if logger:
                logger.finalize("SUCCESS", success_msg)
            else:
                # Create a temporary logger just for finalizing if needed
                temp_logger = BackupLogger(args.log_dir, args.database or "all_databases", args.host)
                temp_logger.finalize("SUCCESS", success_msg)
        else:
            error_msg = "No databases were successfully backed up"
            if logger:
                logger.finalize("FAILED", error_msg)
            else:
                # Create a temporary logger just for finalizing if needed
                temp_logger = BackupLogger(args.log_dir, args.database or "all_databases", args.host)
                temp_logger.finalize("FAILED", error_msg)
            sys.exit(1)

    except Exception as e:
        error_msg = f"Backup failed: {str(e)}"
        if logger:
            logger.log(error_msg, "ERROR")
            logger.finalize("FAILED", error_msg)
        else:
            print(error_msg, file=sys.stderr)
            # Create a temporary logger just for finalizing if needed
            temp_logger = BackupLogger(args.log_dir, args.database or "all_databases", args.host)
            temp_logger.finalize("FAILED", error_msg)
        sys.exit(1)
    finally:
        if 'lock_file' in locals():
            lock_file.close()
            
if __name__ == "__main__":
    main()