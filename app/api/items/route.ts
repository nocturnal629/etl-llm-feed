import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/ts/db'

// Reflects live DB state — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const page = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10))
  const date = searchParams.get('date') ?? ''
  const limit = 20
  const offset = (page - 1) * limit

  const [items, [{ count }]] = await Promise.all([
    date
      ? sql`SELECT id, external_id, title, url, published_at, extracted, created_at
             FROM items WHERE DATE(published_at) = ${date}
             ORDER BY published_at DESC LIMIT ${limit} OFFSET ${offset}`
      : sql`SELECT id, external_id, title, url, published_at, extracted, created_at
             FROM items ORDER BY published_at DESC LIMIT ${limit} OFFSET ${offset}`,
    date
      ? sql`SELECT COUNT(*)::int AS count FROM items WHERE DATE(published_at) = ${date}`
      : sql`SELECT COUNT(*)::int AS count FROM items`,
  ])

  return NextResponse.json({ items, total: count, page, limit })
}
