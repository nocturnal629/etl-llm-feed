# etl-llm-feed
A production-quality scheduled ETL pipeline that ingests data from `{{DOMAIN}}`, stores it in Postgres with proper deduplication, runs LLM-powered summarization over new records, and serves the results through a Next.js dashboard hosted on Vercel.
