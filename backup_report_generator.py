#!/usr/bin/env python3
"""
VM Backup Report Generator
Parses backup log files and generates an interactive HTML calendar report
"""

import argparse
import os
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import calendar

def parse_log_file(log_path):
    """Parse a single backup log file and extract key information"""
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            
        if not first_line.startswith('BACKUP_LOG_V1|'):
            return None
            
        parts = first_line.split('|')
        if len(parts) < 7:
            return None
            
        # Parse the structured header
        timestamp_str = parts[1]
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            return None
            
        return {
            'file_path': log_path,
            'file_name': os.path.basename(log_path),
            'timestamp': timestamp,
            'vm_name': parts[2],
            'host': parts[3],
            'status': parts[4],
            'warnings': int(parts[5]),
            'errors': int(parts[6])
        }
    except Exception as e:
        print(f"Error parsing {log_path}: {e}")
        return None

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

def generate_statistics(logs):
    """Generate summary statistics from the logs"""
    total_jobs = len(logs)
    successful_jobs = len([l for l in logs if l['status'] == 'SUCCESS'])
    failed_jobs = len([l for l in logs if l['status'] == 'FAILED'])
    
    vm_counts = Counter(log['vm_name'] for log in logs)
    host_counts = Counter(log['host'] for log in logs)
    
    # Calculate success rate by VM
    vm_success_rates = {}
    for vm_name in vm_counts:
        vm_logs = [l for l in logs if l['vm_name'] == vm_name]
        successful = len([l for l in vm_logs if l['status'] == 'SUCCESS'])
        vm_success_rates[vm_name] = (successful / len(vm_logs)) * 100 if vm_logs else 0
    
    # Recent activity (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_logs = [l for l in logs if l['timestamp'] >= week_ago]
    
    return {
        'total_jobs': total_jobs,
        'successful_jobs': successful_jobs,
        'failed_jobs': failed_jobs,
        'success_rate': (successful_jobs / total_jobs * 100) if total_jobs > 0 else 0,
        'vm_counts': dict(vm_counts.most_common(10)),
        'host_counts': dict(host_counts),
        'vm_success_rates': vm_success_rates,
        'recent_activity': len(recent_logs),
        'total_warnings': sum(log['warnings'] for log in logs),
        'total_errors': sum(log['errors'] for log in logs)
    }

def generate_html_report(logs, output_path):
    """Generate the HTML report"""
    calendar_data = generate_calendar_data(logs)
    start_date, end_date = get_date_range(logs)
    stats = generate_statistics(logs)
    
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
    <title>VM Backup Report</title>
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
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            padding: 2rem;
            background: #f8f9fa;
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
        
        .success {{ color: #4CAF50; }}
        .error {{ color: #f44336; }}
        .warning {{ color: #ff9800; }}
        .info {{ color: #2196F3; }}
        
        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 2rem;
            padding: 2rem;
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
        
        .vm-list {{
            padding: 2rem;
            background: #f8f9fa;
        }}
        
        .vm-list h3 {{
            margin-bottom: 1rem;
            color: #333;
        }}
        
        .vm-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1rem;
        }}
        
        .vm-card {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        }}
        
        .vm-name {{
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}
        
        .vm-stats {{
            font-size: 0.9rem;
            color: #666;
        }}
        
        .success-rate {{
            float: right;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        
        .rate-high {{ background: #e8f5e8; color: #2e7d2e; }}
        .rate-medium {{ background: #fff3cd; color: #856404; }}
        .rate-low {{ background: #f8d7da; color: #721c24; }}
        
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
            <h1>🔄 VM Backup Dashboard</h1>
            <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        </div>
        
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
                <div class="stat-value warning">{stats['total_warnings']}</div>
                <div class="stat-label">Total Warnings</div>
            </div>
            <div class="stat-card">
                <div class="stat-value info">{stats['recent_activity']}</div>
                <div class="stat-label">Jobs Last 7 Days</div>
            </div>
            <div class="stat-card">
                <div class="stat-value info">{len(stats['vm_counts'])}</div>
                <div class="stat-label">Unique VMs</div>
            </div>
        </div>
        
        <div class="calendar-grid">
            {''.join(calendar_months)}
        </div>
        
        <div class="vm-list">
            <h3>VM Success Rates</h3>
            <div class="vm-grid">
                {generate_vm_cards(stats['vm_counts'], stats['vm_success_rates'])}
            </div>
        </div>
        
        <div class="footer">
            Report covers {len(logs)} backup jobs from {start_date.strftime('%B %Y')} to {end_date.strftime('%B %Y')}
        </div>
    </div>
    
    <div class="tooltip" id="tooltip"></div>
    
    <script>
        // Add interactivity for tooltips
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
    
    print(f"HTML report generated: {output_path}")
    return output_path

def generate_month_calendar(date, calendar_data):
    """Generate HTML for a single month calendar"""
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
                
                # Generate dots for each backup
                dots_html = ""
                summary = ""
                if day_logs:
                    success_count = len([l for l in day_logs if l['status'] == 'SUCCESS'])
                    failed_count = len([l for l in day_logs if l['status'] == 'FAILED'])
                    warning_count = sum(l['warnings'] for l in day_logs if l['warnings'] > 0)
                    
                    for log in day_logs[:5]:  # Show max 5 dots
                        dot_class = 'success' if log['status'] == 'SUCCESS' else 'error'
                        if log['warnings'] > 0:
                            dot_class = 'warning'
                        
                        tooltip = f"{log['vm_name']} on {log['host']} - {log['status']}"
                        if log['warnings'] > 0:
                            tooltip += f" ({log['warnings']} warnings)"
                        
                        dots_html += f'<span class="backup-dot {dot_class}" title="{tooltip}"></span>'
                    
                    if len(day_logs) > 5:
                        dots_html += f'<span style="font-size: 0.7rem; color: #666;">+{len(day_logs) - 5}</span>'
                    
                    summary = f"✓{success_count}" if success_count > 0 else ""
                    if failed_count > 0:
                        summary += f" ✗{failed_count}"
                
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

def generate_vm_cards(vm_counts, vm_success_rates):
    """Generate HTML cards for VM statistics"""
    cards = []
    for vm_name, count in vm_counts.items():
        success_rate = vm_success_rates.get(vm_name, 0)
        
        if success_rate >= 90:
            rate_class = "rate-high"
        elif success_rate >= 70:
            rate_class = "rate-medium"
        else:
            rate_class = "rate-low"
        
        cards.append(f"""
        <div class="vm-card">
            <div class="vm-name">{vm_name}</div>
            <div class="vm-stats">
                {count} backups
                <span class="success-rate {rate_class}">{success_rate:.0f}%</span>
            </div>
        </div>
        """)
    
    return ''.join(cards)

def main():
    parser = argparse.ArgumentParser(description='Generate VM Backup HTML Report')
    parser.add_argument('log_dir', help='Directory containing backup log files')
    parser.add_argument('--output', '-o', default='backup_report.html', 
                       help='Output HTML file path (default: backup_report.html)')
    
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
        
        output_path = generate_html_report(logs, args.output)
        print(f"✅ Report generated successfully!")
        print(f"📁 Open {output_path} in your web browser to view the report")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
