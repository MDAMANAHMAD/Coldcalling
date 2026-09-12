import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

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

    const candidatePaths = [
      path.join(process.cwd(), 'bookings', 'recordings', safeFilename),
      path.join(process.cwd(), 'public', 'recordings', safeFilename),
      path.join(process.cwd(), 'recordings', safeFilename),
      path.join('/tmp', 'recordings', safeFilename)
    ];

    let filePath: string | null = null;
    for (const p of candidatePaths) {
      if (fs.existsSync(p)) {
        filePath = p;
        break;
      }
    }

    if (!filePath) {
      return NextResponse.json({ error: 'Recording not found' }, { status: 404 });
    }

    const stat = fs.statSync(filePath);
    const fileSize = stat.size;
    const range = req.headers.get('range');

    let contentType = 'audio/ogg';
    if (safeFilename.endsWith('.mp3')) contentType = 'audio/mpeg';
    else if (safeFilename.endsWith('.wav')) contentType = 'audio/wav';
    else if (safeFilename.endsWith('.m4a')) contentType = 'audio/mp4';

    if (range) {
      const parts = range.replace(/bytes=/, '').split('-');
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;

      if (start >= fileSize || end >= fileSize || start > end) {
        return new NextResponse(null, {
          status: 416,
          headers: {
            'Content-Range': 'bytes */' + fileSize,
          },
        });
      }

      const chunkSize = end - start + 1;
      const fileStream = fs.createReadStream(filePath, { start, end });
      const webStream = new ReadableStream({
        start(controller) {
          fileStream.on('data', (chunk) => controller.enqueue(chunk));
          fileStream.on('end', () => controller.close());
          fileStream.on('error', (err) => controller.error(err));
        },
        cancel() {
          fileStream.destroy();
        },
      });

      return new NextResponse(webStream as any, {
        status: 206,
        headers: {
          'Content-Range': 'bytes ' + start + '-' + end + '/' + fileSize,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunkSize.toString(),
          'Content-Type': contentType,
          'Cache-Control': 'public, max-age=3600',
        },
      });
    } else {
      const fileStream = fs.createReadStream(filePath);
      const webStream = new ReadableStream({
        start(controller) {
          fileStream.on('data', (chunk) => controller.enqueue(chunk));
          fileStream.on('end', () => controller.close());
          fileStream.on('error', (err) => controller.error(err));
        },
        cancel() {
          fileStream.destroy();
        },
      });

      return new NextResponse(webStream as any, {
        status: 200,
        headers: {
          'Content-Length': fileSize.toString(),
          'Content-Type': contentType,
          'Accept-Ranges': 'bytes',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }
  } catch (error: any) {
    console.error('Error serving recording:', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
