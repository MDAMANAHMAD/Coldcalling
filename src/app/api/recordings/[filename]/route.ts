import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { getRoomServiceClient } from '@/lib/livekit';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';
export const maxDuration = 60;

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ filename: string }> }
) {
  try {
    const { filename } = await context.params;

    const safeFilename = path.basename(filename);
    if (!safeFilename || safeFilename !== filename) {
      return NextResponse.json({ error: 'Invalid file name' }, { status: 400 });
    }

    const cwd = process.cwd();
    const candidatePaths = [
      path.join(/*turbopackIgnore: true*/ cwd, 'bookings', 'recordings', safeFilename),
      path.join(/*turbopackIgnore: true*/ cwd, 'public', 'recordings', safeFilename),
      path.join(/*turbopackIgnore: true*/ cwd, 'recordings', safeFilename),
      path.join('/tmp', 'recordings', safeFilename)
    ];

    let filePath: string | null = null;
    for (const p of candidatePaths) {
      if (fs.existsSync(p)) {
        filePath = p;
        break;
      }
    }

    let audioBuffer: Buffer | null = null;
    let contentType = 'audio/mpeg';
    if (safeFilename.endsWith('.ogg')) contentType = 'audio/ogg';
    else if (safeFilename.endsWith('.wav')) contentType = 'audio/wav';
    else if (safeFilename.endsWith('.m4a')) contentType = 'audio/mp4';

    if (filePath) {
      try {
        const stat = fs.statSync(filePath);
        if (stat.size > 0) {
          audioBuffer = fs.readFileSync(filePath);
        }
      } catch (readErr) {
        console.warn(`[Recordings API] Could not read local file ${filePath}:`, readErr);
      }
    }

    const callSid = safeFilename.replace(/\.(mp3|ogg|wav|m4a)$/i, '');
    let lastCloudError = '';

    // Cloud Fallback: If not found on disk (e.g. running on Vercel), retrieve from LiveKit Cloud room
    if (!audioBuffer) {
      try {
        const roomClient = getRoomServiceClient(30);

        // Fast Cloud Audio Retrieval: Target this call's chunk rooms (up to 100 chunks / ~15 mins)
        const targetNames = [`rec-${callSid}`];
        for (let i = 0; i < 100; i++) {
          targetNames.push(`rec-${callSid}-${i}`);
        }

        let chunkRooms: any[] = [];
        try {
          chunkRooms = await roomClient.listRooms(targetNames);
        } catch (targetedErr: any) {
          console.warn(`[Recordings API] Targeted listRooms note for ${callSid}:`, targetedErr?.message);
        }

        // If targeted lookup didn't find rooms, fall back to listing all rooms
        if (!chunkRooms || chunkRooms.length === 0) {
          try {
            const allRooms = await roomClient.listRooms();
            const prefix = `rec-${callSid}-`;
            chunkRooms = allRooms.filter(r => r.name.startsWith(prefix));
            if (chunkRooms.length === 0) {
              const singleRoom = allRooms.find(r => r.name === `rec-${callSid}`);
              if (singleRoom) chunkRooms = [singleRoom];
            }
          } catch (allErr: any) {
            console.warn(`[Recordings API] Full listRooms fallback note for ${callSid}:`, allErr?.message);
          }
        }

        // 1. Check chunked recording rooms
        if (chunkRooms && chunkRooms.length > 0) {
          try {
            const chunkMap = new Map<number, string>();
            let singleAudio: string | null = null;
            let singleFormat: string = 'mp3';
            let expectedTotal = 0;

            for (const cr of chunkRooms) {
              if (cr.metadata) {
                try {
                  const cp = JSON.parse(cr.metadata);
                  if (typeof cp.chunk === 'number' && cp.audio) {
                    chunkMap.set(cp.chunk, cp.audio);
                    if (typeof cp.total === 'number' && cp.total > expectedTotal) {
                      expectedTotal = cp.total;
                    }
                  } else if (cp.audio && !singleAudio) {
                    singleAudio = cp.audio;
                    if (cp.format) singleFormat = cp.format;
                  }
                } catch {}
              }
            }

            if (chunkMap.size > 0) {
              let fullB64 = '';
              const limit = expectedTotal > 0 ? expectedTotal : chunkMap.size;
              for (let i = 0; i < limit; i++) {
                if (chunkMap.has(i)) {
                  fullB64 += chunkMap.get(i);
                } else {
                  console.warn(`[Recordings API] Warning: chunk ${i} missing for ${callSid}, stopping at ${i}/${limit}`);
                  break;
                }
              }
              if (fullB64) {
                audioBuffer = Buffer.from(fullB64, 'base64');
                contentType = 'audio/mpeg';
                console.log(`[Recordings API] Reassembled ${audioBuffer.length} bytes from ${chunkMap.size} chunks for ${callSid}`);
              }
            } else if (singleAudio) {
              audioBuffer = Buffer.from(singleAudio, 'base64');
              if (singleFormat === 'ogg') contentType = 'audio/ogg';
              console.log(`[Recordings API] Retrieved ${audioBuffer.length} bytes for ${callSid} from single chunk room`);
            }
          } catch (e: any) {
            console.warn(`[Recordings API] Failed reassembling chunked recording for ${callSid}:`, e?.message);
          }
        }

        // 2. Fallback: check gayatri-persistent-storage room for matching callSid with data URL
        if (!audioBuffer) {
          try {
            const storageRooms = await roomClient.listRooms(['gayatri-persistent-storage']);
            if (storageRooms.length > 0 && storageRooms[0].metadata) {
              const parsed = JSON.parse(storageRooms[0].metadata);
              const logs = Array.isArray(parsed.callLogs) ? parsed.callLogs : [];
              const match = logs.find((l: any) => l.callSid === callSid || l.id === callSid);
              if (match) {
                const recUrl = match.recordingUrl || match.recording_url || '';
                if (recUrl.startsWith('data:audio/')) {
                  const b64Data = recUrl.split(',', 2)[1];
                  if (b64Data) {
                    audioBuffer = Buffer.from(b64Data, 'base64');
                    console.log(`[Recordings API] Extracted ${audioBuffer.length} bytes for ${callSid} from persistent-storage data URL`);
                  }
                }
              }
            }
          } catch (e: any) {
            console.warn('[Recordings API] Failed reading gayatri-persistent-storage:', e?.message);
          }
        }

        // Cache to local disk if running in environment where disk is writable
        if (audioBuffer) {
          try {
            const cacheDir = path.join(process.cwd(), 'bookings', 'recordings');
            if (!fs.existsSync(cacheDir)) fs.mkdirSync(cacheDir, { recursive: true });
            fs.writeFileSync(path.join(cacheDir, safeFilename), audioBuffer);
          } catch (cacheErr) {
            // Read-only filesystem on Vercel is fine; audio will stream from memory
          }
        }
      } catch (cloudErr: any) {
        lastCloudError = cloudErr?.message || String(cloudErr);
        console.warn(`[Recordings API] LiveKit Cloud audio lookup error for ${callSid}:`, cloudErr);
      }
    }

    if (!audioBuffer || audioBuffer.length === 0) {
      return NextResponse.json({
        error: 'Recording not found',
        callSid,
        details: lastCloudError || 'Audio chunk rooms not yet synced from voice server'
      }, { status: 404 });
    }

    const fileSize = audioBuffer.length;
    const range = req.headers.get('range');

    if (range) {
      const parts = range.replace(/bytes=/, '').split('-');
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

      if (start >= fileSize || end >= fileSize || start > end) {
        return new NextResponse(null, {
          status: 416,
          headers: {
            'Content-Range': `bytes */${fileSize}`,
          },
        });
      }

      const chunk = audioBuffer.subarray(start, end + 1);
      return new NextResponse(new Uint8Array(chunk), {
        status: 206,
        headers: {
          'Content-Range': `bytes ${start}-${end}/${fileSize}`,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunk.length.toString(),
          'Content-Type': contentType,
          'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
        },
      });
    } else {
      return new NextResponse(new Uint8Array(audioBuffer), {
        status: 200,
        headers: {
          'Content-Length': fileSize.toString(),
          'Content-Type': contentType,
          'Accept-Ranges': 'bytes',
          'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
        },
      });
    }
  } catch (error: any) {
    console.error('Error serving recording:', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
