import { NextResponse } from 'next/server'
import sql from '@/lib/ts/db'

// Health status is inherently live — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

export async function GET() {
  const [[ingest], [digest]] = await Promise.all([
    sql`SELECT MAX(created_at) AS last_at FROM items`,
    sql`SELECT MAX(created_at) AS last_at FROM digests`,
  ])
  return NextResponse.json({
    ok: true,
    last_ingest: ingest?.last_at ?? null,
    last_digest: digest?.last_at ?? null,
  })
}
