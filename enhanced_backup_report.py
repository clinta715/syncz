#!/usr/bin/env python3
"""
Enhanced VM Backup Report Generator
Parses backup log files and generates comprehensive interactive HTML calendar report
"""

import argparse
import os
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import calendar
import glob

def parse_log_file(log_path):
    """Parse a single backup log file and extract comprehensive information"""
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if not lines or not lines[0].strip().startswith('BACKUP_LOG_V1|'):
            return None
            
        first_line = lines[0].strip()
        parts = first_line.split('|')
        if len(parts) < 7:
            return None
            
        # Parse the structured header
        timestamp_str = parts[1]
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
        
        # Enhanced parsing - extract additional metrics from log content
        duration = extract_duration(lines)
        backup_size = extract_backup_size(lines)
        compression_ratio = extract_compression_ratio(lines)
        network_usage = extract_network_usage(lines)
        error_details = extract_error_details(lines)
        warning_details = extract_warning_details(lines)
        performance_metrics = extract_performance_metrics(lines)
        
        return {
            'file_path': log_path,
            'file_name': os.path.basename(log_path),
            'timestamp': timestamp,
            'vm_name': parts[2],
            'host': parts[3],
            'status': parts[4],
            'warnings': int(parts[5]),
            'errors': int(parts[6]),
            'duration': duration,
            'backup_size': backup_size,
            'compression_ratio': compression_ratio,
            'network_usage': network_usage,
            'error_details': error_details,
            'warning_details': warning_details,
            'performance_metrics': performance_metrics,
            'file_size': os.path.getsize(log_path)
        }
    except Exception as e:
        print(f"Error parsing {log_path}: {e}")
        return None

def extract_duration(lines):
    """Extract backup duration from log lines"""
    for line in lines:
        if 'Total backup time:' in line:
            match = re.search(r'(\d+):(\d+):(\d+)', line)
            if match:
                hours, minutes, seconds = map(int, match.groups())
                return hours * 3600 + minutes * 60 + seconds
    return None

def extract_backup_size(lines):
    """Extract backup size in bytes"""
    for line in lines:
        if 'Backup size:' in line or 'Total bytes:' in line:
            match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB|KB|TB|B)', line, re.IGNORECASE)
            if match:
                size, unit = match.groups()
                multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                return int(float(size) * multipliers.get(unit.upper(), 1))
    return None

def extract_compression_ratio(lines):
    """Extract compression ratio percentage"""
    for line in lines:
        if 'compression' in line.lower() and '%' in line:
            match = re.search(r'(\d+(?:\.\d+)?)%', line)
            if match:
                return float(match.group(1))
    return None

def extract_network_usage(lines):
    """Extract network throughput information"""
    for line in lines:
        if 'network throughput' in line.lower() or 'transfer rate' in line.lower():
            match = re.search(r'(\d+(?:\.\d+)?)\s*(Mbps|MB/s|Gbps)', line, re.IGNORECASE)
            if match:
                rate, unit = match.groups()
                # Convert to MB/s for consistency
                if unit.upper() == 'MBPS':
                    return float(rate) / 8  # Convert Mbps to MB/s
                elif unit.upper() == 'GBPS':
                    return float(rate) * 125  # Convert Gbps to MB/s
                else:
                    return float(rate)
    return None

def extract_error_details(lines):
    """Extract detailed error information"""
    errors = []
    for i, line in enumerate(lines):
        if 'ERROR' in line.upper() or 'FAILED' in line.upper():
            # Get some context around the error
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 2)
            context = ' '.join(lines[context_start:context_end]).strip()
            errors.append(context[:200])  # Limit length
    return errors

def extract_warning_details(lines):
    """Extract detailed warning information"""
    warnings = []
    for i, line in enumerate(lines):
        if 'WARNING' in line.upper() or 'WARN' in line.upper():
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 2)
            context = ' '.join(lines[context_start:context_end]).strip()
            warnings.append(context[:200])
    return warnings

def extract_performance_metrics(lines):
    """Extract performance-related metrics"""
    metrics = {}
    for line in lines:
        # CPU usage
        if 'cpu' in line.lower() and '%' in line:
            match = re.search(r'cpu.*?(\d+(?:\.\d+)?)%', line, re.IGNORECASE)
            if match:
                metrics['cpu_usage'] = float(match.group(1))
        
        # Memory usage
        if 'memory' in line.lower() or 'ram' in line.lower():
            match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB)', line, re.IGNORECASE)
            if match:
                size, unit = match.groups()
                multiplier = 1024 if unit.upper() == 'GB' else 1
                metrics['memory_usage'] = float(size) * multiplier
        
        # Disk I/O
        if 'disk' in line.lower() and ('read' in line.lower() or 'write' in line.lower()):
            match = re.search(r'(\d+(?:\.\d+)?)\s*(MB/s|GB/s)', line, re.IGNORECASE)
            if match:
                rate, unit = match.groups()
                multiplier = 1024 if unit.upper() == 'GB/S' else 1
                metrics['disk_io'] = float(rate) * multiplier
    
    return metrics

def find_backup_logs(log_dir):
    """Find all backup log files in the specified directory"""
    logs = []
    
    if not os.path.exists(log_dir):
        raise ValueError(f"Log directory '{log_dir}' does not exist")
    
    # Look for files matching the backup log pattern
    log_pattern = re.compile(r'vmbackup_.*_\d{8}_\d{6}\.log$')
    
    for root, dirs, files in os.walk(log_dir):
        for file in files:
            if log_pattern.match(file):
                log_path = os.path.join(root, file)
                parsed = parse_log_file(log_path)
                if parsed:
                    logs.append(parsed)
    
    return sorted(logs, key=lambda x: x['timestamp'])

def generate_calendar_data(logs):
    """Organize log data by date for calendar display"""
    calendar_data = defaultdict(list)
    
    for log in logs:
        date_key = log['timestamp'].strftime('%Y-%m-%d')
        calendar_data[date_key].append(log)
    
    return dict(calendar_data)

def get_date_range(logs):
    """Get the date range covered by the logs"""
    if not logs:
        today = datetime.now()
        return today.replace(day=1), today
    
    min_date = min(log['timestamp'] for log in logs)
    max_date = max(log['timestamp'] for log in logs)
    
    # Start from the first day of the earliest month
    start_date = min_date.replace(day=1)
    # End at the last day of the latest month or today, whichever is later
    today = datetime.now()
    end_date = max(max_date, today)
    
    return start_date, end_date

def format_size(bytes_value):
    """Format bytes into human readable format"""
    if bytes_value is None:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"

def format_duration(seconds):
    """Format duration in seconds to human readable format"""
    if seconds is None:
        return "N/A"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def generate_statistics(logs):
    """Generate comprehensive summary statistics from the logs"""
    total_jobs = len(logs)
    successful_jobs = len([l for l in logs if l['status'] == 'SUCCESS'])
    failed_jobs = len([l for l in logs if l['status'] == 'FAILED'])
    
    vm_counts = Counter(log['vm_name'] for log in logs)
    host_counts = Counter(log['host'] for log in logs)
    
    # Calculate success rate by VM
    vm_success_rates = {}
    vm_avg_durations = {}
    vm_avg_sizes = {}
    
    for vm_name in vm_counts:
        vm_logs = [l for l in logs if l['vm_name'] == vm_name]
        successful = len([l for l in vm_logs if l['status'] == 'SUCCESS'])
        vm_success_rates[vm_name] = (successful / len(vm_logs)) * 100 if vm_logs else 0
        
        # Average duration for successful backups
        durations = [l['duration'] for l in vm_logs if l['duration'] and l['status'] == 'SUCCESS']
        vm_avg_durations[vm_name] = sum(durations) / len(durations) if durations else None
        
        # Average backup size
        sizes = [l['backup_size'] for l in vm_logs if l['backup_size']]
        vm_avg_sizes[vm_name] = sum(sizes) / len(sizes) if sizes else None
    
    # Recent activity (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_logs = [l for l in logs if l['timestamp'] >= week_ago]
    
    # Performance analytics
    total_backup_size = sum(l['backup_size'] for l in logs if l['backup_size'])
    avg_backup_time = None
    if successful_jobs > 0:
        durations = [l['duration'] for l in logs if l['duration'] and l['status'] == 'SUCCESS']
        avg_backup_time = sum(durations) / len(durations) if durations else None
    
    # Failure patterns
    failure_reasons = Counter()
    for log in logs:
        if log['status'] == 'FAILED' and log['error_details']:
            # Extract common failure patterns
            for error in log['error_details']:
                if 'network' in error.lower():
                    failure_reasons['Network Issues'] += 1
                elif 'disk' in error.lower() or 'space' in error.lower():
                    failure_reasons['Storage Issues'] += 1
                elif 'timeout' in error.lower():
                    failure_reasons['Timeout'] += 1
                else:
                    failure_reasons['Other'] += 1
    
    # Time-based patterns
    hourly_distribution = Counter()
    daily_distribution = Counter()
    for log in logs:
        hourly_distribution[log['timestamp'].hour] += 1
        daily_distribution[log['timestamp'].strftime('%A')] += 1
    
    return {
        'total_jobs': total_jobs,
        'successful_jobs': successful_jobs,
        'failed_jobs': failed_jobs,
        'success_rate': (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0,
        'vm_counts': dict(vm_counts.most_common(10)),
        'host_counts': dict(host_counts),
        'vm_success_rates': vm_success_rates,
        'vm_avg_durations': vm_avg_durations,
        'vm_avg_sizes': vm_avg_sizes,
        'recent_activity': len(recent_logs),
        'total_warnings': sum(log['warnings'] for log in logs),
        'total_errors': sum(log['errors'] for log in logs),
        'total_backup_size': total_backup_size,
        'avg_backup_time': avg_backup_time,
        'failure_reasons': dict(failure_reasons.most_common(5)),
        'hourly_distribution': dict(hourly_distribution),
        'daily_distribution': dict(daily_distribution)
    }

def generate_trend_data(logs):
    """Generate trend data for charts"""
    daily_stats = defaultdict(lambda: {'success': 0, 'failure': 0, 'total_size': 0, 'avg_duration': 0})
    
    for log in logs:
        date_key = log['timestamp'].strftime('%Y-%m-%d')
        if log['status'] == 'SUCCESS':
            daily_stats[date_key]['success'] += 1
        else:
            daily_stats[date_key]['failure'] += 1
        
        if log['backup_size']:
            daily_stats[date_key]['total_size'] += log['backup_size']
        
        if log['duration'] and log['status'] == 'SUCCESS':
            if daily_stats[date_key]['avg_duration'] == 0:
                daily_stats[date_key]['avg_duration'] = log['duration']
            else:
                daily_stats[date_key]['avg_duration'] = (daily_stats[date_key]['avg_duration'] + log['duration']) / 2
    
    return dict(daily_stats)

def generate_html_report(logs, output_path):
    """Generate the enhanced HTML report"""
    calendar_data = generate_calendar_data(logs)
    start_date, end_date = get_date_range(logs)
    stats = generate_statistics(logs)
    trend_data = generate_trend_data(logs)
    
    # Generate calendar months
    calendar_months = []
    current_date = start_date
    
    while current_date <= end_date:
        month_calendar = generate_month_calendar(current_date, calendar_data)
        calendar_months.append(month_calendar)
        
        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced VM Backup Report</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #2196F3 0%, #21CBF3 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }}
        
        .header p {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        
        .nav-tabs {{
            display: flex;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}
        
        .nav-tab {{
            padding: 1rem 2rem;
            background: none;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            color: #666;
            transition: all 0.2s ease;
        }}
        
        .nav-tab.active {{
            background: white;
            color: #2196F3;
            border-bottom: 2px solid #2196F3;
        }}
        
        .nav-tab:hover {{
            background: #e9ecef;
        }}
        
        .tab-content {{
            display: none;
            padding: 2rem;
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            text-align: center;
            transition: transform 0.2s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
        }}
        
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .chart-container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: 2rem;
        }}
        
        .chart-title {{
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: #333;
        }}
        
        .success {{ color: #4CAF50; }}
        .error {{ color: #f44336; }}
        .warning {{ color: #ff9800; }}
        .info {{ color: #2196F3; }}
        
        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 2rem;
        }}
        
        .calendar-month {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }}
        
        .month-header {{
            background: #2196F3;
            color: white;
            padding: 1rem;
            text-align: center;
            font-size: 1.2rem;
            font-weight: 600;
        }}
        
        .calendar-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .calendar-table th {{
            background: #f5f5f5;
            padding: 0.8rem 0.5rem;
            text-align: center;
            font-weight: 600;
            color: #666;
            font-size: 0.9rem;
        }}
        
        .calendar-table td {{
            padding: 0.5rem;
            height: 80px;
            vertical-align: top;
            border: 1px solid #eee;
            position: relative;
        }}
        
        .date-number {{
            font-weight: 600;
            color: #333;
            margin-bottom: 2px;
        }}
        
        .other-month {{
            color: #ccc;
        }}
        
        .backup-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin: 1px;
        }}
        
        .backup-dot.success {{ background: #4CAF50; }}
        .backup-dot.error {{ background: #f44336; }}
        .backup-dot.warning {{ background: #ff9800; }}
        
        .backup-summary {{
            font-size: 0.7rem;
            color: #666;
            margin-top: 2px;
        }}
        
        .tooltip {{
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.8rem;
            pointer-events: none;
            z-index: 1000;
            white-space: nowrap;
            opacity: 0;
            transition: opacity 0.2s ease;
        }}
        
        .vm-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1rem;
        }}
        
        .vm-card {{
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        }}
        
        .vm-name {{
            font-weight: 600;
            margin-bottom: 0.5rem;
            font-size: 1.1rem;
        }}
        
        .vm-stats {{
            font-size: 0.9rem;
            color: #666;
            line-height: 1.4;
        }}
        
        .success-rate {{
            float: right;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .rate-high {{ background: #e8f5e8; color: #2e7d2e; }}
        .rate-medium {{ background: #fff3cd; color: #856404; }}
        .rate-low {{ background: #f8d7da; color: #721c24; }}
        
        .failure-reasons {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            margin-bottom: 2rem;
        }}
        
        .failure-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px solid #eee;
        }}
        
        .failure-item:last-child {{
            border-bottom: none;
        }}
        
        .failure-count {{
            background: #f8d7da;
            color: #721c24;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .footer {{
            text-align: center;
            padding: 1rem;
            color: #666;
            font-size: 0.9rem;
            background: #f8f9fa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔄 Enhanced VM Backup Dashboard</h1>
            <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
        
        <div class="nav-tabs">
            <button class="nav-tab active" onclick="showTab('overview')">Overview</button>
            <button class="nav-tab" onclick="showTab('calendar')">Calendar</button>
            <button class="nav-tab" onclick="showTab('analytics')">Analytics</button>
            <button class="nav-tab" onclick="showTab('vms')">VM Details</button>
        </div>
        
        <div id="overview" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value success">{stats['successful_jobs']}</div>
                    <div class="stat-label">Successful Backups</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value error">{stats['failed_jobs']}</div>
                    <div class="stat-label">Failed Backups</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value info">{stats['success_rate']:.1f}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value info">{format_size(stats['total_backup_size'])}</div>
                    <div class="stat-label">Total Data Backed Up</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value info">{format_duration(stats['avg_backup_time'])}</div>
                    <div class="stat-label">Average Backup Time</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">{stats['total_warnings']}</div>
                    <div class="stat-label">Total Warnings</div>
                </div>
            </div>
            
            {generate_failure_reasons_section(stats['failure_reasons']) if stats['failure_reasons'] else ''}
        </div>
        
        <div id="calendar" class="tab-content">
            <div class="calendar-grid">
                {''.join(calendar_months)}
            </div>
        </div>
        
        <div id="analytics" class="tab-content">
            <div class="chart-container">
                <div class="chart-title">Backup Success Trend</div>
                <canvas id="trendChart" width="800" height="300"></canvas>
            </div>
            
            <div class="chart-container">
                <div class="chart-title">Backup Schedule Distribution</div>
                <canvas id="scheduleChart" width="800" height="300"></canvas>
            </div>
        </div>
        
        <div id="vms" class="tab-content">
            <div class="vm-grid">
                {generate_enhanced_vm_cards(stats['vm_counts'], stats['vm_success_rates'], stats['vm_avg_durations'], stats['vm_avg_sizes'])}
            </div>
        </div>
        
        <div class="footer">
            Report covers {len(logs)} backup jobs from {start_date.strftime('%B %Y')} to {end_date.strftime('%B %Y')}
        </div>
    </div>
    
    <div class="tooltip" id="tooltip"></div>
    
    <script>
        function showTab(tabName) {{
            // Hide all tab contents
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(content => content.classList.remove('active'));
            
            // Remove active class from all tabs
            const tabs = document.querySelectorAll('.nav-tab');
            tabs.forEach(tab => tab.classList.remove('active'));
            
            // Show selected tab content
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
        }}
        
        // Chart data
        const trendData = {json.dumps(list(trend_data.keys()))};
        const successData = {json.dumps([trend_data[date]['success'] for date in trend_data.keys()])};
        const failureData = {json.dumps([trend_data[date]['failure'] for date in trend_data.keys()])};
        
        // Success trend chart
        const trendCtx = document.getElementById('trendChart').getContext('2d');
        new Chart(trendCtx, {{
            type: 'line',
            data: {{
                labels: trendData,
                datasets: [{{
                    label: 'Successful Backups',
                    data: successData,
                    borderColor: '#4CAF50',
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    tension: 0.3
                }}, {{
                    label: 'Failed Backups',
                    data: failureData,
                    borderColor: '#f44336',
                    backgroundColor: 'rgba(244, 67, 54, 0.1)',
                    tension: 0.3
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
        
        // Schedule distribution chart
        const scheduleCtx = document.getElementById('scheduleChart').getContext('2d');
        const hourlyLabels = {json.dumps(list(stats['hourly_distribution'].keys()))};
        const hourlyData = {json.dumps(list(stats['hourly_distribution'].values()))};
        
        new Chart(scheduleCtx, {{
            type: 'bar',
            data: {{
                labels: hourlyLabels.map(h => h + ':00'),
                datasets: [{{
                    label: 'Backup Jobs',
                    data: hourlyData,
                    backgroundColor: '#2196F3',
                    borderColor: '#1976D2',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{
                        beginAtZero: true
                    }}
                }}
            }}
        }});
        
        // Tooltip functionality
        document.addEventListener('mouseover', function(e) {{
            if (e.target.classList.contains('backup-dot')) {{
                const tooltip = document.getElementById('tooltip');
                const rect = e.target.getBoundingClientRect();
                
                tooltip.style.left = rect.left + window.scrollX + 'px';
                tooltip.style.top = rect.top + window.scrollY - 40 + 'px';
                tooltip.textContent = e.target.title;
                tooltip.style.opacity = '1';
            }}
        }});
        
        document.addEventListener('mouseout', function(e) {{
            if (e.target.classList.contains('backup-dot')) {{
                document.getElementById('tooltip').style.opacity = '0';
            }}
        }});
    </script>
</body>
</html>"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Enhanced HTML report generated: {output_path}")
    return output_path

def generate_month_calendar(date, calendar_data):
    """Generate HTML for a single month calendar with enhanced details"""
    month_name = date.strftime('%B %Y')
    cal = calendar.monthcalendar(date.year, date.month)
    
    html = f"""
    <div class="calendar-month">
        <div class="month-header">{month_name}</div>
        <table class="calendar-table">
            <tr>
                <th>Sun</th><th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th>
            </tr>
    """
    
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0:
                html += '<td><div class="date-number other-month"></div></td>'
            else:
                date_key = f"{date.year}-{date.month:02d}-{day:02d}"
                day_logs = calendar_data.get(date_key, [])
                
                # Generate dots for each backup with enhanced info
                dots_html = ""
                summary = ""
                if day_logs:
                    success_count = len([l for l in day_logs if l['status'] == 'SUCCESS'])
                    failed_count = len([l for l in day_logs if l['status'] == 'FAILED'])
                    total_size = sum(l['backup_size'] for l in day_logs if l['backup_size'])
                    avg_duration = None
                    durations = [l['duration'] for l in day_logs if l['duration']]
                    if durations:
                        avg_duration = sum(durations) / len(durations)
                    
                    for log in day_logs[:5]:  # Show max 5 dots
                        dot_class = 'success' if log['status'] == 'SUCCESS' else 'error'
                        if log['warnings'] > 0:
                            dot_class = 'warning'
                        
                        tooltip = f"{log['vm_name']} on {log['host']} - {log['status']}"
                        if log['duration']:
                            tooltip += f" ({format_duration(log['duration'])})"
                        if log['backup_size']:
                            tooltip += f" - {format_size(log['backup_size'])}"
                        if log['warnings'] > 0:
                            tooltip += f" - {log['warnings']} warnings"
                        
                        dots_html += f'<span class="backup-dot {dot_class}" title="{tooltip}"></span>'
                    
                    if len(day_logs) > 5:
                        dots_html += f'<span style="font-size: 0.7rem; color: #666;">+{len(day_logs) - 5}</span>'
                    
                    # Enhanced summary with size and duration info
                    summary = f"✓{success_count}" if success_count > 0 else ""
                    if failed_count > 0:
                        summary += f" ✗{failed_count}"
                    if total_size > 0:
                        summary += f"<br>{format_size(total_size)}"
                    if avg_duration:
                        summary += f"<br>{format_duration(avg_duration)}"
                
                html += f'''
                <td>
                    <div class="date-number">{day}</div>
                    <div>{dots_html}</div>
                    <div class="backup-summary">{summary}</div>
                </td>
                '''
        html += "</tr>"
    
    html += """
        </table>
    </div>
    """
    
    return html

def generate_enhanced_vm_cards(vm_counts, vm_success_rates, vm_avg_durations, vm_avg_sizes):
    """Generate enhanced HTML cards for VM statistics"""
    cards = []
    for vm_name, count in vm_counts.items():
        success_rate = vm_success_rates.get(vm_name, 0)
        avg_duration = vm_avg_durations.get(vm_name)
        avg_size = vm_avg_sizes.get(vm_name)
        
        if success_rate >= 90:
            rate_class = "rate-high"
        elif success_rate >= 70:
            rate_class = "rate-medium"
        else:
            rate_class = "rate-low"
        
        duration_text = format_duration(avg_duration) if avg_duration else "N/A"
        size_text = format_size(avg_size) if avg_size else "N/A"
        
        cards.append(f"""
        <div class="vm-card">
            <div class="vm-name">{vm_name}</div>
            <div class="vm-stats">
                <strong>{count}</strong> total backups
                <span class="success-rate {rate_class}">{success_rate:.0f}%</span>
                <br>
                <strong>Avg Duration:</strong> {duration_text}<br>
                <strong>Avg Size:</strong> {size_text}
            </div>
        </div>
        """)
    
    return ''.join(cards)

def generate_failure_reasons_section(failure_reasons):
    """Generate HTML section for failure reasons analysis"""
    if not failure_reasons:
        return ""
    
    items_html = ""
    for reason, count in failure_reasons.items():
        items_html += f"""
        <div class="failure-item">
            <span>{reason}</span>
            <span class="failure-count">{count}</span>
        </div>
        """
    
    return f"""
    <div class="failure-reasons">
        <h3 style="margin-bottom: 1rem; color: #333;">Common Failure Reasons</h3>
        {items_html}
    </div>
    """

def generate_json_export(logs, output_path):
    """Generate a JSON export of all backup data for external analysis"""
    export_data = {
        'generated_at': datetime.now().isoformat(),
        'total_logs': len(logs),
        'logs': []
    }
    
    for log in logs:
        export_log = {
            'timestamp': log['timestamp'].isoformat(),
            'vm_name': log['vm_name'],
            'host': log['host'],
            'status': log['status'],
            'warnings': log['warnings'],
            'errors': log['errors'],
            'duration': log['duration'],
            'backup_size': log['backup_size'],
            'compression_ratio': log['compression_ratio'],
            'network_usage': log['network_usage'],
            'performance_metrics': log['performance_metrics']
        }
        export_data['logs'].append(export_log)
    
    json_path = output_path.replace('.html', '.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"JSON export generated: {json_path}")
    return json_path

def generate_alerts(logs):
    """Generate alerts for concerning patterns"""
    alerts = []
    
    # Recent failures
    recent_failures = [l for l in logs if l['status'] == 'FAILED' and 
                      l['timestamp'] >= datetime.now() - timedelta(days=7)]
    if len(recent_failures) > 5:
        alerts.append({
            'type': 'high',
            'message': f"{len(recent_failures)} backup failures in the last 7 days"
        })
    
    # VMs with consistently long backup times
    long_backup_vms = []
    vm_durations = {}
    for log in logs:
        if log['duration'] and log['status'] == 'SUCCESS':
            if log['vm_name'] not in vm_durations:
                vm_durations[log['vm_name']] = []
            vm_durations[log['vm_name']].append(log['duration'])
    
    for vm_name, durations in vm_durations.items():
        if len(durations) >= 3:
            avg_duration = sum(durations) / len(durations)
            if avg_duration > 7200:  # More than 2 hours
                long_backup_vms.append(vm_name)
    
    if long_backup_vms:
        alerts.append({
            'type': 'medium',
            'message': f"VMs with long backup times: {', '.join(long_backup_vms)}"
        })
    
    # Check for VMs that haven't been backed up recently
    vm_last_backup = {}
    for log in logs:
        if log['status'] == 'SUCCESS':
            if log['vm_name'] not in vm_last_backup:
                vm_last_backup[log['vm_name']] = log['timestamp']
            else:
                vm_last_backup[log['vm_name']] = max(vm_last_backup[log['vm_name']], log['timestamp'])
    
    stale_vms = []
    threshold = datetime.now() - timedelta(days=7)
    for vm_name, last_backup in vm_last_backup.items():
        if last_backup < threshold:
            stale_vms.append(vm_name)
    
    if stale_vms:
        alerts.append({
            'type': 'high',
            'message': f"VMs not backed up in 7+ days: {', '.join(stale_vms)}"
        })
    
    return alerts

def main():
    parser = argparse.ArgumentParser(description='Generate Enhanced VM Backup HTML Report')
    parser.add_argument('log_dir', help='Directory containing backup log files')
    parser.add_argument('--output', '-o', default='enhanced_backup_report.html', 
                       help='Output HTML file path (default: enhanced_backup_report.html)')
    parser.add_argument('--json-export', action='store_true',
                       help='Also generate a JSON export of all data')
    parser.add_argument('--alerts', action='store_true',
                       help='Generate alerts for concerning patterns')
    
    args = parser.parse_args()
    
    try:
        print(f"Scanning for backup logs in: {args.log_dir}")
        logs = find_backup_logs(args.log_dir)
        
        if not logs:
            print("No backup log files found!")
            print("Looking for files matching pattern: vmbackup_*_YYYYMMDD_HHMMSS.log")
            return 1
        
        print(f"Found {len(logs)} backup log files")
        print(f"Date range: {min(log['timestamp'] for log in logs).strftime('%Y-%m-%d')} to {max(log['timestamp'] for log in logs).strftime('%Y-%m-%d')}")
        
        # Generate main report
        output_path = generate_html_report(logs, args.output)
        
        # Generate JSON export if requested
        if args.json_export:
            generate_json_export(logs, args.output)
        
        # Generate alerts if requested
        if args.alerts:
            alerts = generate_alerts(logs)
            if alerts:
                print("\n⚠️  ALERTS DETECTED:")
                for alert in alerts:
                    icon = "🔴" if alert['type'] == 'high' else "🟡"
                    print(f"  {icon} {alert['message']}")
            else:
                print("\n✅ No alerts detected")
        
        print(f"\n✅ Enhanced report generated successfully!")
        print(f"📊 Open {output_path} in your web browser to view the report")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        return 1

if __name__ == "__main__":
    exit(main())