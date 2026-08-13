import socket
import time
import urllib.request
import ssl

SERVICES = {
    "LiveKit Cloud": "cold-calling-j7qhnkas.livekit.cloud",
    "Deepgram API": "api.deepgram.com",
    "ElevenLabs API": "api.elevenlabs.io",
    "Groq API": "api.groq.com"
}

def test_dns(host):
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        t_dns = (time.perf_counter() - t0) * 1000
        print(f"  [DNS OK] Resolved {host} to {ip} in {t_dns:.1f}ms")
        return ip
    except Exception as e:
        t_dns = (time.perf_counter() - t0) * 1000
        print(f"  [DNS FAILED] Failed to resolve {host} in {t_dns:.1f}ms: {e}")
        return None

def test_tcp(host, ip, port=443):
    if not ip:
        return
    t0 = time.perf_counter()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((ip, port))
        t_tcp = (time.perf_counter() - t0) * 1000
        print(f"  [TCP OK] Connected to {host} ({ip}:{port}) in {t_tcp:.1f}ms")
        s.close()
    except Exception as e:
        t_tcp = (time.perf_counter() - t0) * 1000
        print(f"  [TCP FAILED] Connection to {host} failed in {t_tcp:.1f}ms: {e}")

def main():
    print("=" * 60)
    print("VPS NETWORK & DNS DIAGNOSTICS")
    print("=" * 60)
    
    for name, host in SERVICES.items():
        print(f"\nTesting {name} ({host})...")
        ip = test_dns(host)
        test_tcp(host, ip)
        
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
