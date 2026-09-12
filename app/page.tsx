import Link from 'next/link'
import sql from '@/lib/ts/db'
import ActivityChart from './components/ActivityChart'

// Dashboard shows live ingestion/digest data — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

async function getLatestDigest() {
  const rows = await sql`
    SELECT digest_date, item_count, summary_markdown, model
    FROM digests ORDER BY digest_date DESC LIMIT 1
  `
  return rows[0] ?? null
}

async function getDailyStats() {
  const rows = await sql`
    SELECT DATE(published_at)::text AS day, COUNT(*)::int AS count
    FROM items
    WHERE published_at >= now() - INTERVAL '7 days'
    GROUP BY day ORDER BY day
  `
  return rows as unknown as { day: string; count: number }[]
}

async function getRecentItems() {
  return sql`
    SELECT external_id, title, url, published_at,
           extracted->>'interest_score' AS interest_score
    FROM items ORDER BY published_at DESC LIMIT 10
  `
}

export default async function Home() {
  const [digest, stats, recent] = await Promise.all([
    getLatestDigest(),
    getDailyStats(),
    getRecentItems(),
  ])

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">ETL LLM Feed</h1>
        <nav className="flex gap-4 text-sm text-gray-600">
          <Link href="/items" className="hover:underline">All items</Link>
          <Link href="/digests" className="hover:underline">Digests</Link>
        </nav>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-3">Items ingested (last 7 days)</h2>
        {stats.length > 0 ? (
          <ActivityChart data={stats} />
        ) : (
          <p className="text-gray-500 text-sm">No data yet — run the ingest cron to populate.</p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Latest Digest</h2>
        {digest ? (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">
              {String(digest.digest_date).slice(0, 10)} &middot; {digest.item_count} items &middot; {digest.model}
            </p>
            <pre className="whitespace-pre-wrap text-sm leading-relaxed bg-gray-50 rounded p-4 overflow-auto">
              {digest.summary_markdown}
            </pre>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No digest yet — run the summarize cron to generate one.</p>
        )}
      </section>

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Recent Items</h2>
          <Link href="/items" className="text-sm text-indigo-600 hover:underline">View all →</Link>
        </div>
        <ul className="space-y-2">
          {recent.map((item) => (
            <li key={String(item.external_id)} className="flex items-start gap-3 text-sm">
              {item.interest_score && (
                <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold flex items-center justify-center">
                  {item.interest_score}
                </span>
              )}
              <div>
                <a
                  href={String(item.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium hover:underline"
                >
                  {item.title}
                </a>
                <p className="text-gray-400 text-xs">
                  {String(item.published_at).slice(0, 10)}
                </p>
              </div>
            </li>
          ))}
          {recent.length === 0 && (
            <li className="text-gray-500 text-sm">No items yet.</li>
          )}
        </ul>
      </section>
    </main>
  )
}
