import os
import socket
import time

def main():
    print("=" * 60)
    print("RESOLV.CONF CONTENTS:")
    print("=" * 60)
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r") as f:
                print(f.read())
        else:
            print("/etc/resolv.conf does not exist!")
    except Exception as e:
        print("Error reading resolv.conf:", e)
        
    print("\n" + "=" * 60)
    print("DNS RESOLUTION BENCHMARK:")
    print("=" * 60)
    hosts = [
        "cold-calling-j7qhnkas.livekit.cloud",
        "api.deepgram.com",
        "api.elevenlabs.io",
        "api.groq.com"
    ]
    for host in hosts:
        t0 = time.perf_counter()
        try:
            socket.getaddrinfo(host, 443)
            t_res = (time.perf_counter() - t0) * 1000
            print(f"  {host} resolved in {t_res:.1f}ms")
        except Exception as e:
            t_res = (time.perf_counter() - t0) * 1000
            print(f"  FAILED resolving {host} in {t_res:.1f}ms: {e}")
            
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
