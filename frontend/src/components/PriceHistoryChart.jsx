import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import API_BASE from '../config'

const PERIOD_OPTIONS = [
  { id: '1mo', label: '1M' },
  { id: '3mo', label: '3M' },
  { id: '6mo', label: '6M' },
  { id: '1y', label: '1Y' },
  { id: '2y', label: '2Y' },
  { id: '5y', label: '5Y' },
]

const COLORS = {
  close: '#4e78f2',
  ma20: '#fbbf24',
  ma50: '#f87171',
  current: '#86efac',
}

function formatMoney(value, currency = 'USD') {
  if (!Number.isFinite(Number(value))) return '—'
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'USD',
      maximumFractionDigits: 2,
    }).format(Number(value))
  } catch {
    return Number(value).toFixed(2)
  }
}

function formatDateTick(date) {
  if (!date) return ''
  const d = new Date(date)
  if (Number.isNaN(d.getTime())) return date
  return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function formatTooltipLabel(label) {
  if (!label) return ''
  const d = new Date(label)
  if (Number.isNaN(d.getTime())) return label
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function PriceHistoryChart({
  symbol,
  currency = 'USD',
  currentPrice = null,
  fallbackLastClose = null,
}) {
  const [period, setPeriod] = useState('1y')
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!symbol) return undefined
    const controller = new AbortController()
    // Defer to a microtask so the synchronous setState calls below don't
    // run inside the effect body (react-hooks/set-state-in-effect).
    Promise.resolve().then(async () => {
      if (controller.signal.aborted) return
      setIsLoading(true)
      setError('')
      try {
        const res = await fetch(
          `${API_BASE}/history/${encodeURIComponent(symbol)}?period=${period}`,
          { signal: controller.signal },
        )
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          const detail = body?.detail
          throw new Error(
            typeof detail === 'string' ? detail : `Request failed (${res.status})`,
          )
        }
        const json = await res.json()
        if (!controller.signal.aborted) {
          setData(json)
        }
      } catch (e) {
        if (!controller.signal.aborted && e.name !== 'AbortError') {
          setError(e.message || 'Failed to load price history.')
          setData(null)
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    })

    return () => controller.abort()
  }, [symbol, period])

  const chartData = useMemo(() => data?.series ?? [], [data])

  const markerPrice = useMemo(() => {
    const candidates = [currentPrice, data?.current_price, data?.last_close, fallbackLastClose]
    for (const c of candidates) {
      const num = Number(c)
      if (Number.isFinite(num) && num > 0) return num
    }
    return null
  }, [currentPrice, data, fallbackLastClose])

  return (
    <div className="card price-chart-card">
      <div className="price-chart-header">
        <div>
          <h2 className="subsection-title">{symbol} price history</h2>
          {data?.name && <p className="muted small-print">{data.name}</p>}
        </div>
        <div className="period-toggle" role="tablist" aria-label="Chart period">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="tab"
              aria-selected={period === opt.id}
              className={
                period === opt.id
                  ? 'period-toggle-btn period-toggle-btn--active'
                  : 'period-toggle-btn'
              }
              onClick={() => setPeriod(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="loading">Loading price history…</p>}

      {!isLoading && error && (
        <div className="error-card">
          <p>{error}</p>
        </div>
      )}

      {!isLoading && !error && chartData.length > 0 && (
        <>
          <div className="price-chart-wrap">
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart
                data={chartData}
                margin={{ top: 10, right: 24, bottom: 0, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(145,170,224,0.15)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#9db5e5', fontSize: 11 }}
                  tickFormatter={formatDateTick}
                  minTickGap={48}
                  axisLine={{ stroke: 'rgba(145,170,224,0.25)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: '#9db5e5', fontSize: 11 }}
                  width={70}
                  domain={['auto', 'auto']}
                  axisLine={{ stroke: 'rgba(145,170,224,0.25)' }}
                  tickLine={false}
                  tickFormatter={(v) => formatMoney(v, currency)}
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(13,19,31,0.95)',
                    border: '1px solid rgba(145,170,224,0.4)',
                    borderRadius: 8,
                    color: '#f5f7ff',
                  }}
                  formatter={(value, name) => [formatMoney(value, currency), name]}
                  labelFormatter={formatTooltipLabel}
                />
                <Line
                  type="monotone"
                  dataKey="close"
                  name="Close"
                  stroke={COLORS.close}
                  strokeWidth={2.2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="ma_20"
                  name="MA20"
                  stroke={COLORS.ma20}
                  strokeWidth={1.6}
                  strokeDasharray="4 4"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="ma_50"
                  name="MA50"
                  stroke={COLORS.ma50}
                  strokeWidth={1.6}
                  strokeDasharray="6 6"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                {Number.isFinite(markerPrice) && (
                  <ReferenceLine
                    y={markerPrice}
                    stroke={COLORS.current}
                    strokeDasharray="2 4"
                    label={{
                      value: `Current ${formatMoney(markerPrice, currency)}`,
                      fill: COLORS.current,
                      fontSize: 11,
                      position: 'right',
                    }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="price-chart-legend">
            <span className="price-chart-legend__item">
              <span
                className="price-chart-legend__swatch"
                style={{ background: COLORS.close }}
              />{' '}
              Close
            </span>
            <span className="price-chart-legend__item">
              <span
                className="price-chart-legend__swatch price-chart-legend__swatch--dashed"
                style={{ background: COLORS.ma20 }}
              />{' '}
              MA20
            </span>
            <span className="price-chart-legend__item">
              <span
                className="price-chart-legend__swatch price-chart-legend__swatch--dashed"
                style={{ background: COLORS.ma50 }}
              />{' '}
              MA50
            </span>
            <span className="price-chart-legend__item">
              <span
                className="price-chart-legend__swatch price-chart-legend__swatch--dashed"
                style={{ background: COLORS.current }}
              />{' '}
              Current
            </span>
          </div>
        </>
      )}

      {!isLoading && !error && data && chartData.length === 0 && (
        <p className="muted small-print">No price history available for this period.</p>
      )}
    </div>
  )
}

export default PriceHistoryChart
