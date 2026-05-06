import { useCallback, useEffect, useMemo, useState } from 'react'
import API_BASE from '../config'

const PREDICT_SCHEMA = 2

function normalizeTickerList(raw) {
  return Array.from(
    new Set(
      raw
        .split(/[,\s]+/g)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean),
    ),
  ).slice(0, 12)
}

function computeInvestScore(pred) {
  const upNext = Number(pred?.next_state_probabilities?.up ?? 0)
  const upHorizon = Number(pred?.distribution_after_horizon?.up ?? 0)
  // Heuristic: emphasize multi-day "up" probability, lightly include next-day.
  const score = 0.7 * upHorizon + 0.3 * upNext
  return Number.isFinite(score) ? score : 0
}

function formatPrice(value) {
  if (!Number.isFinite(Number(value))) return '—'
  return Number(value).toFixed(2)
}

function DashboardPage() {
  const [symbols, setSymbols] = useState(['SPY', 'AAPL'])
  const [symbolInput, setSymbolInput] = useState('NVDA, MSFT')
  const [period, setPeriod] = useState('2y')
  const [steps, setSteps] = useState(5)
  const [selectedSymbol, setSelectedSymbol] = useState('SPY')
  const [dataBySymbol, setDataBySymbol] = useState({})
  const [errorsBySymbol, setErrorsBySymbol] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [globalError, setGlobalError] = useState('')

  const loadPredictions = useCallback(
    async (signal) => {
      const list = symbols.filter(Boolean)
      if (list.length === 0) return
      if (!list.includes(selectedSymbol)) setSelectedSymbol(list[0])

      const qsBase = new URLSearchParams({
        period,
        steps: String(steps),
      }).toString()

    try {
      setIsLoading(true)
        setGlobalError('')

        const settled = await Promise.allSettled(
          list.map(async (sym) => {
            try {
              const qs = new URLSearchParams(qsBase)
              qs.set('symbol', sym)
              const response = await fetch(`${API_BASE}/predict?${qs}`, { signal })
              if (!response.ok) {
                const body = await response.json().catch(() => ({}))
                const detail = body.detail
                throw new Error(
                  typeof detail === 'string' ? detail : `Request failed (${response.status})`,
                )
              }
              const json = await response.json()
              return { sym, ok: true, json }
            } catch (e) {
              return { sym, ok: false, error: e?.message || 'Unable to load prediction.' }
            }
          }),
        )

        const nextData = {}
        const nextErrors = {}
        for (const item of settled) {
          if (item.status === 'fulfilled') {
            if (item.value.ok) {
              nextData[item.value.sym] = item.value.json
            } else {
              nextErrors[item.value.sym] = item.value.error
            }
          } else {
            // Should be rare since we catch inside, but keep a fallback.
            const msg = item.reason?.message || 'Unable to load prediction.'
            nextErrors.unknown = msg
          }
        }

        // Keep prior good data if a refresh fails for a subset
        setDataBySymbol((prev) => ({ ...prev, ...nextData }))
        setErrorsBySymbol(nextErrors)
    } catch (err) {
      if (err.name !== 'AbortError') {
          setGlobalError(err.message || 'Unable to load predictions right now.')
      }
    } finally {
      setIsLoading(false)
    }
    },
    [period, selectedSymbol, steps, symbols],
  )

  useEffect(() => {
    const controller = new AbortController()
    loadPredictions(controller.signal)
    return () => controller.abort()
  }, [loadPredictions])

  const selectedData = dataBySymbol[selectedSymbol] ?? null

  const rows = useMemo(() => {
    const list = symbols
      .map((sym) => {
        const pred = dataBySymbol[sym]
        const score = pred ? computeInvestScore(pred) : 0
        return { sym, pred, score }
      })
      .filter((r) => r.sym)

    list.sort((a, b) => b.score - a.score)
    return list
  }, [dataBySymbol, symbols])

  const addSymbols = useCallback(() => {
    const toAdd = normalizeTickerList(symbolInput)
    if (toAdd.length === 0) return
    setSymbols((prev) => {
      const merged = Array.from(new Set([...prev, ...toAdd])).slice(0, 12)
      return merged
    })
    setSelectedSymbol((prevSelected) => prevSelected || toAdd[0])
    setSymbolInput('')
  }, [symbolInput])

  const removeSymbol = useCallback(
    (sym) => {
      setSymbols((prev) => {
        const next = prev.filter((s) => s !== sym)
        if (selectedSymbol === sym) {
          setSelectedSymbol(next[0] ?? '')
        }
        return next
      })
      setDataBySymbol((prev) => {
        const copy = { ...prev }
        delete copy[sym]
        return copy
      })
    },
    [selectedSymbol],
  )

  return (
    <section className="page">
      <h1 className="page-title">Markov prediction (yfinance)</h1>
      <p className="muted dashboard-lead">
        Daily returns are bucketed into <strong>down</strong>, <strong>flat</strong>, and{' '}
        <strong>up</strong>. Transition probabilities are learned from history; the chart uses the
        last known state and powers of the transition matrix for multi-day distributions. This is a
        simple model—not investment advice.
      </p>

      <div className="card dashboard-controls">
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="pred-symbols">
            Symbols (watchlist)
          </label>
          <input
            id="pred-symbols"
            className="stocks-input"
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
            placeholder="Add tickers (comma or space separated), e.g. NVDA, MSFT, SPY"
          />
        </div>
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="pred-period">
            History window
          </label>
          <select
            id="pred-period"
            className="stocks-input"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="3mo">3 months</option>
            <option value="6mo">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
            <option value="5y">5 years</option>
            <option value="max">Max</option>
          </select>
        </div>
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="pred-steps">
            Horizon (trading days)
          </label>
          <input
            id="pred-steps"
            className="stocks-input"
            type="number"
            min={1}
            max={60}
            value={steps}
            onChange={(e) => setSteps(Number(e.target.value) || 1)}
          />
        </div>
        <div className="dashboard-actions">
          <button type="button" className="primary-btn" onClick={addSymbols}>
            Add symbols
          </button>
          <button type="button" className="primary-btn" onClick={() => loadPredictions()}>
            Refresh
          </button>
        </div>
        <div className="ticker-chip-row" role="list" aria-label="Selected tickers">
          {symbols.map((s) => (
            <button
              key={s}
              type="button"
              className={s === selectedSymbol ? 'ticker-chip ticker-chip--active' : 'ticker-chip'}
              onClick={() => setSelectedSymbol(s)}
              title="Click to select; remove with ×"
            >
              <span className="ticker-chip__sym">{s}</span>
              <span
                className="ticker-chip__remove"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation()
                  removeSymbol(s)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    e.stopPropagation()
                    removeSymbol(s)
                  }
                }}
                aria-label={`Remove ${s}`}
              >
                ×
              </span>
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="card">
          <p className="loading">Loading prediction…</p>
        </div>
      )}

      {!isLoading && (globalError || Object.keys(errorsBySymbol).length > 0) && (
        <div className="card error-card">
          <h2>Could not load prediction(s)</h2>
          {globalError && <p>{globalError}</p>}
          {!globalError && Object.keys(errorsBySymbol).length > 0 && (
            <>
              <p>Some tickers failed to load:</p>
              <ul className="muted">
                {Object.entries(errorsBySymbol).map(([sym, msg]) => (
                  <li key={sym}>
                    <strong>{sym}</strong>: {msg}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {!isLoading && !globalError && selectedData && selectedData.schema_version !== PREDICT_SCHEMA && (
        <div className="card error-card">
          <h2>Backend is running old code</h2>
          <p>
            This dashboard needs the yfinance Markov API (<code>schema_version: {PREDICT_SCHEMA}</code>
            ). Your response has no symbol and still uses the old random 5-asset model. Stop the server,
            open the <strong>backend</strong> folder that contains the current <code>markov.py</code>, then
            run:{' '}
            <code className="inline-code">
              python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
            </code>
          </p>
        </div>
      )}

      {!isLoading && !globalError && rows.length > 0 && (
        <>
          <div className="card">
            <h2 className="subsection-title">Compare tickers (sorted by “up” likelihood)</h2>
            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Current</th>
                    <th>Next (argmax)</th>
                    <th>P(next)</th>
                    <th>P(up in {steps}d)</th>
                    <th>Current price</th>
                    <th>Est. price +1d</th>
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ sym, pred, score }) => {
                    const pNext = Number(pred?.confidence ?? 0)
                    const pUpH = Number(pred?.distribution_after_horizon?.up ?? 0)
                    const isSelected = sym === selectedSymbol
                    const currentPx = pred?.current_price ?? pred?.last_close
                    return (
                      <tr
                        key={sym}
                        className={isSelected ? 'compare-row compare-row--active' : 'compare-row'}
                        onClick={() => setSelectedSymbol(sym)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setSelectedSymbol(sym)
                          }
                        }}
                      >
                        <td className="compare-ticker">{sym}</td>
                        <td className="compare-cap">{pred?.current_state ?? '—'}</td>
                        <td className="compare-cap">{pred?.predicted_state ?? '—'}</td>
                        <td>{pred ? `${(pNext * 100).toFixed(2)}%` : '—'}</td>
                        <td>{pred ? `${(pUpH * 100).toFixed(2)}%` : '—'}</td>
                        <td>{pred ? formatPrice(currentPx) : '—'}</td>
                        <td>{pred ? formatPrice(pred.estimated_next_close) : '—'}</td>
                        <td>{pred ? (score * 100).toFixed(2) : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {selectedData && selectedData.schema_version === PREDICT_SCHEMA && (
            <>
              <div className="card-grid">
                <article className="card metric-card">
                  <p className="metric-label">Selected ticker</p>
                  <p className="metric-value">{selectedData.symbol ?? selectedSymbol ?? '—'}</p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">Last state (from last return)</p>
                  <p className="metric-value">{selectedData.current_state}</p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">Most likely next day</p>
                  <p className="metric-value">{selectedData.predicted_state}</p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">P(next day | today)</p>
                  <p className="metric-value">{(selectedData.confidence * 100).toFixed(2)}%</p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">Last close</p>
                  <p className="metric-value">{formatPrice(selectedData.last_close)}</p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">Current price</p>
                  <p className="metric-value">
                    {formatPrice(selectedData.current_price ?? selectedData.last_close)}
                  </p>
                </article>
                <article className="card metric-card">
                  <p className="metric-label">Estimated close (+1d)</p>
                  <p className="metric-value">{formatPrice(selectedData.estimated_next_close)}</p>
                </article>
              </div>

              <div className="card">
                <h2 className="subsection-title">Next-day probabilities</h2>
                <ul className="prob-list">
                  {Object.entries(selectedData.next_state_probabilities || {}).map(([k, v]) => (
                    <li key={k}>
                      <span>{k}</span>
                      <span>{(Number(v) * 100).toFixed(2)}%</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="card">
                <h2 className="subsection-title">
                  After {selectedData.horizon_steps} day{selectedData.horizon_steps === 1 ? '' : 's'} (π
                  P<sup>{selectedData.horizon_steps}</sup>)
                </h2>
                <ul className="prob-list">
                  {Object.entries(selectedData.distribution_after_horizon || {}).map(([k, v]) => (
                    <li key={k}>
                      <span>{k}</span>
                      <span>{(Number(v) * 100).toFixed(2)}%</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="card muted-card">
                <p className="muted small-print">
                  Model: {selectedData.model ?? 'empirical'} · Data: {selectedData.return_observations}{' '}
                  return days · flat if |r| ≤ {selectedData.threshold}. Matrix uses Laplace smoothing.
                </p>
              </div>
            </>
          )}
        </>
      )}
    </section>
  )
}

export default DashboardPage
