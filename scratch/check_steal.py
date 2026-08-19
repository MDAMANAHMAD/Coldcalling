import time

def read_proc_stat():
    with open("/proc/stat", "r") as f:
        line = f.readline()
    parts = line.split()
    # cpu user nice system idle iowait irq softirq steal
    user = float(parts[1])
    nice = float(parts[2])
    system = float(parts[3])
    idle = float(parts[4])
    iowait = float(parts[5])
    irq = float(parts[6])
    softirq = float(parts[7])
    steal = float(parts[8])
    total = user + nice + system + idle + iowait + irq + softirq + steal
    return total, steal, idle

def benchmark_steal():
    print("--- Throttling & Steal Time Diagnostic ---")
    t0_tot, t0_st, t0_id = read_proc_stat()
    
    # Run a high-CPU load for 2 seconds to trigger throttling metrics
    t_end = time.perf_counter() + 2.0
    count = 0
    while time.perf_counter() < t_end:
        count += 1
        
    t1_tot, t1_st, t1_id = read_proc_stat()
    
    total_diff = t1_tot - t0_tot
    steal_diff = t1_st - t0_st
    idle_diff = t1_id - t0_id
    
    steal_pct = (steal_diff / total_diff) * 100 if total_diff > 0 else 0
    idle_pct = (idle_diff / total_diff) * 100 if total_diff > 0 else 0
    
    print(f"CPU Steal Time during load: {steal_pct:.1f}%")
    print(f"CPU Idle Time during load: {idle_pct:.1f}%")
    
    if steal_pct > 10:
        print("\nWARNING: Your CPU has significant STEAL TIME. AWS is actively throttling your VPS CPU!")
    else:
        print("\nSUCCESS: CPU Steal Time is low. AWS is not currently throttling your CPU.")

if __name__ == "__main__":
    benchmark_steal()
