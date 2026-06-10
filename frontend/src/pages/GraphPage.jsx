import { useCallback, useEffect, useState } from 'react'
import API_BASE from '../config'

function GraphPage() {
  const [symbol, setSymbol] = useState('SPY')
  const [period, setPeriod] = useState('2y')
  const [imageUrl, setImageUrl] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const loadGraph = useCallback(async (signal) => {
    const sym = symbol.trim().toUpperCase()
    if (!sym) return
    let objectUrl = ''
    try {
      setIsLoading(true)
      setError('')
      const qs = new URLSearchParams({ symbol: sym, period })
      const response = await fetch(`${API_BASE}/graph?${qs}`, { signal })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        const detail = body.detail
        throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
      }
      const blob = await response.blob()
      objectUrl = URL.createObjectURL(blob)
      setImageUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return objectUrl
      })
    } catch (err) {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      if (err.name !== 'AbortError') {
        setError(err.message || 'Unable to load graph right now.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [symbol, period])

  useEffect(() => {
    const controller = new AbortController()
    loadGraph(controller.signal)
    return () => controller.abort()
  }, [loadGraph])

  return (
    <section className="page">
      <h1 className="page-title">Markov chain</h1>
      <p className="muted dashboard-lead">
        Markov chain graph for the selected symbol.
      </p>

      <div className="card dashboard-controls graph-controls">
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="graph-symbol">
            Symbol
          </label>
          <input
            id="graph-symbol"
            className="stocks-input"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            maxLength={12}
          />
        </div>
        <div className="dashboard-row">
          <label className="stocks-label" htmlFor="graph-period">
            History
          </label>
          <select
            id="graph-period"
            className="stocks-input"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="6mo">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
            <option value="5y">5 years</option>
          </select>
        </div>
        <button type="button" className="primary-btn" onClick={() => loadGraph()}>
          Refresh graph
        </button>
      </div>

      <div className="card graph-card">
        {isLoading && <p className="loading">Loading Markov chain graph…</p>}
        {!isLoading && error && (
          <div className="error-card">
            <h2>Could not load graph</h2>
            <p>{error}</p>
          </div>
        )}
        {!isLoading && !error && imageUrl && (
          <img className="graph-image" src={imageUrl} alt="Markov chain graph" />
        )}
      </div>
    </section>
  )
}

export default GraphPage
