import { useCallback, useEffect, useMemo, useState } from 'react'
import API_BASE from '../config'
import AllocationPanel from '../components/AllocationPanel'
import AnalysisTable from '../components/AnalysisTable'
import PriceHistoryChart from '../components/PriceHistoryChart'
import RecommendationBadge from '../components/RecommendationBadge'
import RiskBadge from '../components/RiskBadge'
import StatCard from '../components/StatCard'

const ANALYZE_SCHEMA = 1
const RISK_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'low', label: 'Low risk' },
  { id: 'medium', label: 'Medium risk' },
  { id: 'high', label: 'High risk' },
]

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

function formatNumber(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return '—'
  return Number(value).toFixed(digits)
}

function formatPercent(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

function formatSignedPercent(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return '—'
  const num = Number(value) * 100
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(digits)}%`
}

function trendCopy(direction) {
  if (direction === 'up') return 'Uptrend (SMA20 > SMA50)'
  if (direction === 'down') return 'Downtrend (SMA20 < SMA50)'
  return 'Sideways (SMAs converging)'
}

function rsiHint(rsi) {
  if (!Number.isFinite(Number(rsi))) return ''
  const v = Number(rsi)
  if (v >= 70) return 'Overbought'
  if (v <= 30) return 'Oversold'
  if (v >= 55) return 'Mild momentum up'
  if (v <= 45) return 'Mild momentum down'
  return 'Neutral'
}

function DashboardPage() {
  const [symbols, setSymbols] = useState(['SPY', 'AAPL', 'MSFT', 'NVDA'])
  const [symbolInput, setSymbolInput] = useState('')
  const [period, setPeriod] = useState('2y')
  const [steps, setSteps] = useState(5)
  const [contextLen, setContextLen] = useState(5)
  const [selectedSymbol, setSelectedSymbol] = useState('SPY')
  const [riskFilter, setRiskFilter] = useState('all')

  const [analysis, setAnalysis] = useState(null)
  const [errorsBySymbol, setErrorsBySymbol] = useState({})
  const [isLoading, setIsLoading] = useState(true)
  const [globalError, setGlobalError] = useState('')

  const loadAnalysis = useCallback(
    async (signal) => {
      const list = symbols.filter(Boolean)
      if (list.length === 0) {
        setAnalysis(null)
        setIsLoading(false)
        return
      }

      try {
        setIsLoading(true)
        setGlobalError('')

        const qs = new URLSearchParams({
          symbols: list.join(','),
          period,
          steps: String(steps),
          context_len: String(contextLen),
        }).toString()

        const response = await fetch(`${API_BASE}/analyze?${qs}`, { signal })
        if (!response.ok) {
          const body = await response.json().catch(() => ({}))
          const detail = body.detail
          throw new Error(
            typeof detail === 'string' ? detail : `Request failed (${response.status})`,
          )
        }
        const json = await response.json()
        setAnalysis(json)
        setErrorsBySymbol(json.errors ?? {})

        if (Array.isArray(json.results) && json.results.length > 0) {
          const stillThere = json.results.find((r) => r.symbol === selectedSymbol)
          if (!stillThere) {
            setSelectedSymbol(json.results[0].symbol)
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          setGlobalError(err.message || 'Unable to load analysis right now.')
        }
      } finally {
        setIsLoading(false)
      }
    },
    [contextLen, period, selectedSymbol, steps, symbols],
  )

  useEffect(() => {
    const controller = new AbortController()
    // Defer to a microtask so synchronous setState calls inside loadAnalysis
    // run after the effect body, satisfying react-hooks/set-state-in-effect.
    Promise.resolve().then(() => {
      if (!controller.signal.aborted) loadAnalysis(controller.signal)
    })
    return () => controller.abort()
  }, [loadAnalysis])

  const allRows = useMemo(() => analysis?.results ?? [], [analysis])

  const filteredRows = useMemo(() => {
    if (riskFilter === 'all') return allRows
    return allRows.filter((r) => r.scoring?.risk_level === riskFilter)
  }, [allRows, riskFilter])

  const selectedRow = useMemo(
    () => allRows.find((r) => r.symbol === selectedSymbol) ?? null,
    [allRows, selectedSymbol],
  )

  const addSymbols = useCallback(() => {
    const toAdd = normalizeTickerList(symbolInput)
    if (toAdd.length === 0) return
    setSymbols((prev) => Array.from(new Set([...prev, ...toAdd])).slice(0, 12))
    setSelectedSymbol((prev) => prev || toAdd[0])
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
    },
    [selectedSymbol],
  )

  const horizonSteps = analysis?.horizon_steps ?? steps
  const errorEntries = Object.entries(errorsBySymbol)
  const schemaMismatch =
    analysis !== null && analysis.schema_version !== ANALYZE_SCHEMA

  return (
    <section className="page">
      <h1 className="page-title">Investment analysis</h1>
      <p className="muted dashboard-lead">
        Combines technical indicators (stdev, moving averages, RSI, momentum, volume) with the
        Markov chain to produce a profit-potential score, a risk level, and a recommendation per
        ticker. Higher score = stronger forward setup.
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
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="pred-context">
            Context days
          </label>
          <input
            id="pred-context"
            className="stocks-input"
            type="number"
            min={1}
            max={10}
            value={contextLen}
            onChange={(e) => setContextLen(Number(e.target.value) || 1)}
          />
        </div>
        <div className="dashboard-actions">
          <button type="button" className="primary-btn" onClick={addSymbols}>
            Add symbols
          </button>
          <button type="button" className="primary-btn" onClick={() => loadAnalysis()}>
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
          <p className="loading">Running analysis…</p>
        </div>
      )}

      {!isLoading && globalError && (
        <div className="card error-card">
          <h2>Could not run analysis</h2>
          <p>{globalError}</p>
        </div>
      )}

      {!isLoading && schemaMismatch && (
        <div className="card error-card">
          <h2>Backend is running old code</h2>
          <p>
            This dashboard needs the analysis API (
            <code>schema_version: {ANALYZE_SCHEMA}</code>). Restart the backend with{' '}
            <code className="inline-code">
              python -m uvicorn app.main:app --reload --port 8001
            </code>
            .
          </p>
        </div>
      )}

      {!isLoading && analysis && analysis.schema_version === ANALYZE_SCHEMA && (
        <>
          <div className="card">
            <div className="analysis-header">
              <h2 className="subsection-title">
                Ranked stocks ({filteredRows.length} of {allRows.length})
              </h2>
              <div className="risk-filter-row" role="tablist" aria-label="Filter by risk">
                {RISK_FILTERS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    role="tab"
                    aria-selected={riskFilter === f.id}
                    className={
                      riskFilter === f.id
                        ? 'risk-filter risk-filter--active'
                        : 'risk-filter'
                    }
                    onClick={() => setRiskFilter(f.id)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            <AnalysisTable
              rows={filteredRows}
              selectedSymbol={selectedSymbol}
              onSelect={setSelectedSymbol}
              horizonSteps={horizonSteps}
            />
          </div>

          {errorEntries.length > 0 && (
            <div className="card error-card">
              <h2>Some tickers failed</h2>
              <ul className="muted">
                {errorEntries.map(([sym, msg]) => (
                  <li key={sym}>
                    <strong>{sym}</strong>: {msg}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <AllocationPanel results={allRows} />

          {selectedRow && <SelectedTickerDetail row={selectedRow} />}
        </>
      )}
    </section>
  )
}

function SelectedTickerDetail({ row }) {
  const { symbol, name, currency, last_close, current_price, change_percent } = row
  const ind = row.indicators ?? {}
  const mk = row.markov ?? {}
  const detail = row.markov_detail ?? null
  const scoring = row.scoring ?? {}

  const change = Number(change_percent ?? 0)
  const priceText = `${formatNumber(current_price ?? last_close, 2)}${currency ? ` ${currency}` : ''}`
  const trendDir = ind.trend_direction ?? 'sideways'

  return (
    <>
      <div className="card selected-summary">
        <div className="selected-summary__top">
          <div>
            <h2 className="selected-summary__title">
              {symbol} <span className="selected-summary__name">{name ?? ''}</span>
            </h2>
            <p className="muted small-print">
              {priceText} · last close {formatNumber(last_close, 2)} · change{' '}
              <span className={change >= 0 ? 'text-up' : 'text-down'}>
                {change >= 0 ? '+' : ''}
                {change.toFixed(2)}%
              </span>
            </p>
          </div>
          <div className="selected-summary__badges">
            <RecommendationBadge recommendation={scoring.recommendation} />
            <RiskBadge level={scoring.risk_level} />
          </div>
        </div>
      </div>

      <PriceHistoryChart
        symbol={symbol}
        currency={currency ?? 'USD'}
        currentPrice={current_price}
        fallbackLastClose={last_close}
      />

      <div className="card-grid">
        <StatCard
          label="Profit score"
          value={`${formatNumber(scoring.profit_score, 1)} / 100`}
          accent={scoring.recommendation_color}
          hint="Weighted blend of momentum, trend, RSI, volume, Markov P(+), volatility penalty."
        />
        <StatCard
          label="Volatility score"
          value={`${formatNumber(ind.volatility_score, 1)} / 100`}
          hint={
            (ind.volatility_score ?? 0) < 30
              ? 'Low standard deviation — relatively stable stock.'
              : (ind.volatility_score ?? 0) < 60
                ? 'Moderate volatility.'
                : 'High standard deviation — risky / volatile stock.'
          }
        />
        <StatCard
          label="Stdev (annualized)"
          value={formatPercent(ind.stdev_annualized, 2)}
          hint={`Daily stdev: ${formatPercent(ind.stdev_daily, 3)}`}
        />
        <StatCard
          label="RSI(14)"
          value={formatNumber(ind.rsi_14, 1)}
          hint={rsiHint(ind.rsi_14)}
        />
        <StatCard
          label="Moving averages"
          value={`MA20 ${formatNumber(ind.ma_20, 2)} · MA50 ${formatNumber(ind.ma_50, 2)}`}
          hint={trendCopy(trendDir)}
        />
        <StatCard
          label="Momentum"
          value={`20d ${formatSignedPercent(ind.momentum_20d, 2)} · 60d ${formatSignedPercent(ind.momentum_60d, 2)}`}
          hint={`Period growth: ${formatSignedPercent(ind.historical_growth, 2)}`}
        />
        <StatCard
          label="Volume change"
          value={formatSignedPercent(ind.volume_change, 1)}
          hint="Last 5 sessions vs prior 20-session baseline."
        />
        <StatCard
          label={`P(positive in ${detail?.horizon_steps ?? mk.horizon_steps ?? '?'}d)`}
          value={formatPercent(mk.horizon_positive_probability, 1)}
          hint={`Next-day P(+): ${formatPercent(mk.next_positive_probability, 1)}`}
        />
        <StatCard
          label="Estimated next close"
          value={formatNumber(mk.estimated_next_close, 2)}
          hint={`Markov expected next-day return: ${formatSignedPercent(mk.expected_return_next_day, 3)}`}
        />
      </div>

      <div className="card">
        <h2 className="subsection-title">Score breakdown</h2>
        <ul className="prob-list">
          {Object.entries(scoring.score_breakdown ?? {}).map(([name, info]) => (
            <li key={name}>
              <span>
                {name.replace(/_/g, ' ')}
                <small className="muted"> (weight {(info.weight * 100).toFixed(0)}%)</small>
              </span>
              <span>+{Number(info.contribution ?? 0).toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>

      {detail && (
        <>
          <div className="card">
            <h2 className="subsection-title">Next-day Markov probabilities</h2>
            <ul className="prob-list">
              {Object.entries(detail.next_state_probabilities || {}).map(([k, v]) => {
                const contribution = Number(detail.next_state_expected_contributions?.[k] ?? 0)
                return (
                  <li key={k}>
                    <span>
                      {k}
                      <small className="muted">
                        {' '}(expected contribution: {(contribution * 100).toFixed(3)}%)
                      </small>
                    </span>
                    <span>{(Number(v) * 100).toFixed(2)}%</span>
                  </li>
                )
              })}
            </ul>
            <p className="muted small-print">
              Total expected next-day return:{' '}
              {(Number(detail.expected_return_next_day ?? 0) * 100).toFixed(3)}%
            </p>
          </div>

          <div className="card">
            <h2 className="subsection-title">
              After {detail.horizon_steps} day{detail.horizon_steps === 1 ? '' : 's'} (Monte Carlo)
            </h2>
            <ul className="prob-list">
              {Object.entries(detail.distribution_after_horizon || {}).map(([k, v]) => (
                <li key={k}>
                  <span>{k}</span>
                  <span>{(Number(v) * 100).toFixed(2)}%</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="card muted-card">
            <p className="muted small-print">
              Model: {detail.model ?? 'empirical'} · Data: {detail.return_observations} return days ·
              Context: last {detail.context_len} day(s). Matrix uses Laplace smoothing + backoff.
            </p>
          </div>
        </>
      )}
    </>
  )
}

export default DashboardPage
