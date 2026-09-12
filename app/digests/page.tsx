import Link from 'next/link'
import sql from '@/lib/ts/db'

// Archive reflects live DB state — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

async function getDigests() {
  return sql`
    SELECT id, digest_date, item_count, summary_markdown, summary_json, model, created_at
    FROM digests ORDER BY digest_date DESC LIMIT 30
  `
}

export default async function DigestsPage() {
  const digests = await getDigests()

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Digest Archive</h1>
        <Link href="/" className="text-sm text-gray-500 hover:underline">← Home</Link>
      </div>

      {digests.length === 0 && (
        <p className="text-gray-500 text-sm">No digests yet — run the summarize cron to generate one.</p>
      )}

      <div className="space-y-8">
        {digests.map((d) => {
          const dateStr = String(d.digest_date).slice(0, 10)
          const json = d.summary_json as {
            themes?: string[]
            top_items?: { title: string; reason: string }[]
          }
          return (
            <article key={String(d.id)} className="border rounded-lg p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{dateStr}</h2>
                <span className="text-xs text-gray-400">{d.item_count} items &middot; {d.model}</span>
              </div>

              {json.themes && json.themes.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Themes</p>
                  <div className="flex flex-wrap gap-2">
                    {json.themes.map((t: string) => (
                      <span key={t} className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {json.top_items && json.top_items.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Top Items</p>
                  <ul className="space-y-2">
                    {json.top_items.map((p: { title: string; reason: string }) => (
                      <li key={p.title} className="text-sm">
                        <span className="font-medium">{p.title}</span>
                        <span className="text-gray-500"> — {p.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <details className="text-sm">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                  Full digest
                </summary>
                <pre className="mt-3 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded p-4 overflow-auto text-xs">
                  {d.summary_markdown}
                </pre>
              </details>
            </article>
          )
        })}
      </div>
    </main>
  )
}
