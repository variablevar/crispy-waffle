import { NextRequest, NextResponse } from 'next/server';
import { getAgentEvents } from '@/lib/agent-api';

// Browser clients call this handler; it attaches AGENT_API_KEY server-side so
// the key never reaches the browser. Filesystem routes take precedence over
// the /api/:path* rewrite to the backend.
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const limitParam = Number(sp.get('limit'));
  const result = await getAgentEvents({
    limit: Number.isFinite(limitParam) && limitParam > 0 ? limitParam : 50,
    type: sp.get('type') || undefined,
    asset: sp.get('asset') || undefined,
    severity: sp.get('severity') || undefined,
  });
  return NextResponse.json(result);
}
