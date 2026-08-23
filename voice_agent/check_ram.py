import os
import subprocess

def get_system_ram():
    """Reads system memory from /proc/meminfo (Linux standard)"""
    if not os.path.exists("/proc/meminfo"):
        return None
    
    mem_info = {}
    with open("/proc/meminfo", "r") as f:
        for line in f:
            parts = line.split(":")
            if len(parts) == 2:
                mem_info[parts[0].strip()] = parts[1].strip()
                
    # Convert kB string to float GB
    def to_gb(kb_str):
        if not kb_str:
            return 0.0
        kb = float(kb_str.replace("kB", "").strip())
        return kb / (1024 * 1024)

    total = to_gb(mem_info.get("MemTotal"))
    free = to_gb(mem_info.get("MemFree"))
    available = to_gb(mem_info.get("MemAvailable"))
    used = total - available
    
    return {
        "total": total,
        "free": free,
        "available": available,
        "used": used,
        "percent_used": (used / total) * 100 if total > 0 else 0
    }

def get_service_ram():
    """Checks the memory usage of the systemd voice-agent service if running"""
    try:
        # Run systemctl status to find memory line
        res = subprocess.run(
            ["systemctl", "status", "voice-agent"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        for line in res.stdout.split("\n"):
            if "Memory:" in line:
                # Memory: 674.6M (peak: 674.9M)
                return line.strip()
    except Exception:
        pass
    return "Not running as a systemd service or permission denied"

def get_python_processes_ram():
    """Reads RSS memory of all running python processes in /proc"""
    total_rss = 0.0
    pids = [pid for pid in os.listdir("/proc") if pid.isdigit()]
    
    for pid in pids:
        try:
            # Check cmdline
            with open(f"/proc/{pid}/cmdline", "r") as f:
                cmd = f.read().replace("\x00", " ")
            if "python" in cmd:
                # Read status for RSS (Resident Set Size)
                with open(f"/proc/{pid}/status", "r") as f:
                    for line in f:
                        if "VmRSS:" in line:
                            # VmRSS:     674600 kB
                            kb = float(line.split(":")[1].replace("kB", "").strip())
                            total_rss += kb / (1024 * 1024) # to GB
        except Exception:
            continue
            
    return total_rss

# Run calculations
sys_ram = get_system_ram()
service_ram_str = get_service_ram()
python_ram = get_python_processes_ram()

print("="*60)
print("             💾 SERVER RAM DIAGNOSTICS REPORT")
print("="*60)

if sys_ram:
    print(f"System Total RAM      : {sys_ram['total']:.2f} GB")
    print(f"System Used RAM       : {sys_ram['used']:.2f} GB ({sys_ram['percent_used']:.1f}% used)")
    print(f"System Available RAM  : {sys_ram['available']:.2f} GB ({100 - sys_ram['percent_used']:.1f}% free)")
    print("-"*60)
    print(f"Voice Agent Service RAM (systemd) : {service_ram_str}")
    print(f"Total Python Processes RAM usage  : {python_ram:.2f} GB")
else:
    print("❌ This script must be run on a Linux VPS to read /proc memory statistics.")
print("="*60)
