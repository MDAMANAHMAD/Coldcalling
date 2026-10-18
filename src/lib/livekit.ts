import { RoomServiceClient, SipClient } from 'livekit-server-sdk';

export const VERIFIED_LIVEKIT_HOST = 'https://cold-calling-j7qhnkas.livekit.cloud';
export const VERIFIED_LIVEKIT_KEY = 'APIAkEXqBNfS2LP';
export const VERIFIED_LIVEKIT_SECRET = 'dtfb0ghSFBTudiAtRkckjaCrHnAuIhQpF2JJCRDtYlT';
export const VERIFIED_SIP_TRUNK = 'ST_TEGVYguUkfe9';

/**
 * Sanitizes and validates LiveKit credentials, falling back safely
 * to verified production credentials if environment variables are missing,
 * empty strings, or invalid schemes like "wss://" on Vercel.
 */
export function getCleanLiveKitConfig() {
  let host = (process.env.LIVEKIT_URL || '').replace(/['"]/g, '').trim();
  try {
    if (!host || host === 'wss://' || host === 'https://' || !host.includes('.')) {
      host = VERIFIED_LIVEKIT_HOST;
    } else {
      host = host.replace(/^wss:\/\//i, 'https://').replace(/^ws:\/\//i, 'http://');
      if (!host.includes('://')) host = `https://${host}`;
      const parsed = new URL(host);
      if (!parsed.hostname || !parsed.hostname.includes('.')) {
        host = VERIFIED_LIVEKIT_HOST;
      } else {
        host = `https://${parsed.host}`;
      }
    }
  } catch {
    host = VERIFIED_LIVEKIT_HOST;
  }

  let apiKey = (process.env.LIVEKIT_API_KEY || '').replace(/['"]/g, '').trim();
  if (!apiKey || apiKey.length < 5) {
    apiKey = VERIFIED_LIVEKIT_KEY;
  }

  let apiSecret = (process.env.LIVEKIT_API_SECRET || '').replace(/['"]/g, '').trim();
  if (!apiSecret || apiSecret.length < 5) {
    apiSecret = VERIFIED_LIVEKIT_SECRET;
  }

  return { host, apiKey, apiSecret };
}

/**
 * Returns a configured RoomServiceClient instance with explicit request timeout.
 */
export function getRoomServiceClient(requestTimeoutSeconds = 30): RoomServiceClient {
  const { host, apiKey, apiSecret } = getCleanLiveKitConfig();
  return new RoomServiceClient(host, apiKey, apiSecret, { requestTimeout: requestTimeoutSeconds });
}

/**
 * Returns a configured SipClient instance.
 */
export function getSipClient(): { client: SipClient; trunkId: string } {
  const { host, apiKey, apiSecret } = getCleanLiveKitConfig();
  const trunkId = (process.env.SIP_OUTBOUND_TRUNK_ID || VERIFIED_SIP_TRUNK).replace(/['"]/g, '').trim() || VERIFIED_SIP_TRUNK;
  return {
    client: new SipClient(host, apiKey, apiSecret),
    trunkId,
  };
}

/**
 * In-memory cache for LiveKit Cloud persistent storage metadata to keep
 * dashboard polling latency < 50ms instead of waiting for cloud network roundtrips.
 */
let cachedCloudLogs: any[] = [];
let lastCloudFetchTime = 0;
const CLOUD_CACHE_TTL_MS = 20000; // 20 seconds cache

export async function getCachedPersistentCloudLogs(): Promise<any[]> {
  const now = Date.now();
  if (now - lastCloudFetchTime < CLOUD_CACHE_TTL_MS && cachedCloudLogs.length > 0) {
    return cachedCloudLogs;
  }
  try {
    const roomClient = getRoomServiceClient(3);
    const rooms = await Promise.race([
      roomClient.listRooms(['gayatri-persistent-storage']),
      new Promise<any[]>((_, reject) => setTimeout(() => reject(new Error('timeout')), 2500))
    ]);
    if (rooms && rooms.length > 0 && rooms[0].metadata) {
      const parsed = JSON.parse(rooms[0].metadata);
      if (Array.isArray(parsed.callLogs)) {
        cachedCloudLogs = parsed.callLogs;
        lastCloudFetchTime = now;
      }
    }
  } catch {
    // Return stale cache on network blips or timeout
  }
  return cachedCloudLogs;
}

export function updateCachedPersistentCloudLogs(log: any) {
  if (!log) return;
  const key = log.callSid || log.id;
  cachedCloudLogs = [log, ...cachedCloudLogs.filter(l => (l.callSid || l.id) !== key)].slice(0, 50);
  lastCloudFetchTime = Date.now();
}
