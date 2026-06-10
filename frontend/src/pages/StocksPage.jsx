import { useCallback, useEffect, useState } from 'react'
import API_BASE from '../config'

async function apiErrorMessage(res, pathHint) {
  if (res.status === 502 || res.status === 503) {
    return `Cannot reach the API (HTTP ${res.status}). Make sure the server is running.`
  }
  let detail
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) {
    const body = await res.json().catch(() => ({}))
    detail = body.detail
  }
  if (typeof detail === 'string') {
    if (res.status === 404 && detail === 'Not Found') {
      return `${detail}: no matching route. Restart the server and try again.`
    }
    return detail
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg ?? JSON.stringify(d)).join('; ')
  }
  return `Request failed (${res.status})`
}

function StocksPage() {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [symbolInput, setSymbolInput] = useState('')
  const [quote, setQuote] = useState(null)
  const [loadingSearch, setLoadingSearch] = useState(false)
  const [loadingQuote, setLoadingQuote] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const q = query.trim()
    if (q.length < 1) {
      setSuggestions([])
      return
    }

    const t = setTimeout(async () => {
      try {
        setLoadingSearch(true)
        const res = await fetch(
          `${API_BASE}/stocks/search?q=${encodeURIComponent(q)}&limit=25`,
        )
        if (!res.ok) throw new Error(`Search failed (${res.status})`)
        setSuggestions(await res.json())
      } catch (e) {
        setSuggestions([])
        if (import.meta.env.DEV) console.warn(e)
      } finally {
        setLoadingSearch(false)
      }
    }, 250)

    return () => clearTimeout(t)
  }, [query])

  const loadQuote = useCallback(async (sym) => {
    const s = sym.trim().toUpperCase()
    if (!s) return
    setError('')
    setLoadingQuote(true)
    setQuote(null)
    try {
      const path = `${API_BASE}/stocks/quote/${encodeURIComponent(s)}`
      const res = await fetch(path)
      if (!res.ok) {
        throw new Error(await apiErrorMessage(res, path))
      }
      setQuote(await res.json())
      setSymbolInput(s)
    } catch (e) {
      setError(e.message || 'Could not load quote.')
    } finally {
      setLoadingQuote(false)
    }
  }, [])

  return (
    <section className="page">
      <h1 className="page-title">Stocks</h1>
      <p className="muted stocks-lead">
        Search a curated list of symbols, or enter any ticker. Profit / loss compares the{' '}
        <strong>latest close</strong> to the <strong>previous trading session</strong> using live
        Yahoo Finance data.
      </p>

      <div className="card stocks-panel">
        <label className="stocks-label" htmlFor="stock-search">
          Search name or symbol
        </label>
        <input
          id="stock-search"
          className="stocks-input"
          type="search"
          placeholder="e.g. Apple, NVDA, SPY…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
        />
        {loadingSearch && <p className="stocks-hint">Searching…</p>}
        {suggestions.length > 0 && (
          <ul className="stocks-suggest">
            {suggestions.map((item) => (
              <li key={item.symbol}>
                <button
                  type="button"
                  className="stocks-suggest-btn"
                  onClick={() => loadQuote(item.symbol)}
                >
                  <span className="stocks-suggest-symbol">{item.symbol}</span>
                  <span className="stocks-suggest-name">{item.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="stocks-row">
          <div className="stocks-field">
            <label className="stocks-label" htmlFor="stock-symbol">
              Symbol lookup
            </label>
            <input
              id="stock-symbol"
              className="stocks-input"
              placeholder="AAPL"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
              maxLength={12}
            />
          </div>
          <button
            type="button"
            className="primary-btn stocks-lookup-btn"
            disabled={loadingQuote || !symbolInput.trim()}
            onClick={() => loadQuote(symbolInput)}
          >
            {loadingQuote ? 'Loading…' : 'Get quote'}
          </button>
        </div>
      </div>

      {error && (
        <div className="card error-card">
          <h2>Quote error</h2>
          <p>{error}</p>
        </div>
      )}

      {quote && (
        <div className="card stocks-quote">
          <div className="stocks-quote-header">
            <div>
              <h2 className="stocks-quote-title">{quote.symbol}</h2>
              {quote.name && <p className="stocks-quote-sub">{quote.name}</p>}
            </div>
            <span
              className={
                quote.is_profitable ? 'profit-badge' : 'loss-badge'
              }
            >
              {quote.is_profitable ? 'Up vs prior session' : 'Down vs prior session'}
            </span>
          </div>
          <dl className="stocks-stats">
            <div>
              <dt>Last close</dt>
              <dd>
                {quote.last_close}
                {quote.currency ? ` ${quote.currency}` : ''}
              </dd>
            </div>
            <div>
              <dt>Prior close</dt>
              <dd>{quote.previous_close}</dd>
            </div>
            <div>
              <dt>Change</dt>
              <dd className={quote.change_amount >= 0 ? 'text-up' : 'text-down'}>
                {quote.change_amount >= 0 ? '+' : ''}
                {quote.change_amount} ({quote.change_percent >= 0 ? '+' : ''}
                {quote.change_percent}%)
              </dd>
            </div>
            <div>
              <dt>As of</dt>
              <dd>{quote.as_of}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}

export default StocksPage
