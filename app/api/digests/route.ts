import { NextResponse } from 'next/server'
import sql from '@/lib/ts/db'

// Reflects live DB state — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

export async function GET() {
  const digests = await sql`
    SELECT id, digest_date, item_count, summary_markdown, summary_json, model, created_at
    FROM digests
    ORDER BY digest_date DESC
    LIMIT 30
  `
  return NextResponse.json({ digests })
}
