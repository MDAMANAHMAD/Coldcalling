import os
import multiprocessing
import time

def check_cpu():
    print("--- CPU & Hardware Diagnostics ---")
    print(f"Total CPU Cores: {multiprocessing.cpu_count()}")
    
    # Check load average
    try:
        load1, load5, load15 = os.getloadavg()
        print(f"System Load Average (1m, 5m, 15m): {load1:.2f}, {load5:.2f}, {load15:.2f}")
    except Exception as e:
        print(f"Could not get load average: {e}")
        
    # Check CPU frequency/info (Linux only)
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r") as f:
                lines = f.readlines()
            model_name = ""
            cpu_mhz = ""
            for line in lines:
                if "model name" in line:
                    model_name = line.split(":")[1].strip()
                if "cpu MHz" in line:
                    cpu_mhz = line.split(":")[1].strip()
            print(f"CPU Model: {model_name}")
            if cpu_mhz:
                print(f"CPU Speed: {cpu_mhz} MHz")
        except Exception as e:
            print(f"Error reading cpuinfo: {e}")
            
    # Measure active processing speed (simple loop test)
    t0 = time.perf_counter()
    count = 0
    while time.perf_counter() - t0 < 1.0:
        count += 1
    print(f"Single-core ops/sec (benchmark): {count:,}")
    
if __name__ == "__main__":
    check_cpu()
