import Link from 'next/link'
import sql from '@/lib/ts/db'

// Reflects live DB state — must never be cached as a static build artifact.
export const dynamic = 'force-dynamic'

const PAGE_SIZE = 20

async function getItems(page: number, date: string) {
  const offset = (page - 1) * PAGE_SIZE
  const [items, [{ count }]] = await Promise.all([
    date
      ? sql`SELECT external_id, title, url, published_at,
                   extracted->>'interest_score' AS interest_score,
                   extracted->'topics' AS topics
             FROM items WHERE DATE(published_at) = ${date}
             ORDER BY published_at DESC LIMIT ${PAGE_SIZE} OFFSET ${offset}`
      : sql`SELECT external_id, title, url, published_at,
                   extracted->>'interest_score' AS interest_score,
                   extracted->'topics' AS topics
             FROM items ORDER BY published_at DESC LIMIT ${PAGE_SIZE} OFFSET ${offset}`,
    date
      ? sql`SELECT COUNT(*)::int AS count FROM items WHERE DATE(published_at) = ${date}`
      : sql`SELECT COUNT(*)::int AS count FROM items`,
  ])
  return { items, total: count as number }
}

export default async function ItemsPage({
  searchParams,
}: {
  searchParams: { page?: string; date?: string }
}) {
  const page = Math.max(1, parseInt(searchParams.page ?? '1', 10))
  const date = searchParams.date ?? ''
  const { items, total } = await getItems(page, date)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <main className="max-w-5xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">All Items</h1>
        <Link href="/" className="text-sm text-gray-500 hover:underline">← Home</Link>
      </div>

      <form method="GET" className="flex items-center gap-3">
        <label htmlFor="date" className="text-sm font-medium">Filter by date:</label>
        <input
          id="date"
          name="date"
          type="date"
          defaultValue={date}
          className="border rounded px-2 py-1 text-sm"
        />
        <button type="submit" className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700">
          Apply
        </button>
        {date && (
          <Link href="/items" className="text-sm text-gray-500 hover:underline">Clear</Link>
        )}
      </form>

      <p className="text-sm text-gray-500">{total} item{total !== 1 ? 's' : ''}{date ? ` on ${date}` : ''}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="pb-2 pr-4 font-medium w-8">Score</th>
              <th className="pb-2 pr-4 font-medium">Title</th>
              <th className="pb-2 pr-4 font-medium">Topics</th>
              <th className="pb-2 font-medium whitespace-nowrap">Published</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const topics: string[] = Array.isArray(item.topics) ? item.topics : []
              return (
                <tr key={String(item.external_id)} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="py-2 pr-4">
                    {item.interest_score ? (
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold">
                        {item.interest_score}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 max-w-sm">
                    <a
                      href={String(item.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline font-medium leading-snug"
                    >
                      {item.title}
                    </a>
                  </td>
                  <td className="py-2 pr-4">
                    <div className="flex flex-wrap gap-1">
                      {topics.slice(0, 3).map((t: string) => (
                        <span key={t} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-2 text-gray-400 whitespace-nowrap">
                    {String(item.published_at).slice(0, 10)}
                  </td>
                </tr>
              )
            })}
            {items.length === 0 && (
              <tr>
                <td colSpan={4} className="py-6 text-center text-gray-400">No items found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-3 text-sm">
        {page > 1 && (
          <Link
            href={`/items?page=${page - 1}${date ? `&date=${date}` : ''}`}
            className="px-3 py-1 border rounded hover:bg-gray-50"
          >
            ← Prev
          </Link>
        )}
        <span className="text-gray-500">Page {page} of {totalPages}</span>
        {page < totalPages && (
          <Link
            href={`/items?page=${page + 1}${date ? `&date=${date}` : ''}`}
            className="px-3 py-1 border rounded hover:bg-gray-50"
          >
            Next →
          </Link>
        )}
      </div>
    </main>
  )
}
