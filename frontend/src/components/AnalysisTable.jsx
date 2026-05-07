import { useMemo, useState } from 'react'
import RecommendationBadge from './RecommendationBadge'
import RiskBadge from './RiskBadge'

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

function getSortValue(row, key) {
  switch (key) {
    case 'symbol':
      return row.symbol ?? ''
    case 'recommendation':
      return row.scoring?.recommendation ?? ''
    case 'risk_level':
      return row.scoring?.risk_level ?? ''
    case 'profit_score':
      return Number(row.scoring?.profit_score ?? 0)
    case 'last_close':
      return Number(row.last_close ?? 0)
    case 'change_percent':
      return Number(row.change_percent ?? 0)
    case 'stdev':
      return Number(row.indicators?.stdev_annualized ?? 0)
    case 'rsi':
      return Number(row.indicators?.rsi_14 ?? 0)
    case 'momentum_20d':
      return Number(row.indicators?.momentum_20d ?? 0)
    case 'horizon_positive':
      return Number(row.markov?.horizon_positive_probability ?? 0)
    default:
      return 0
  }
}

const COLUMNS = [
  { key: 'symbol', label: 'Ticker', align: 'left' },
  { key: 'recommendation', label: 'Recommendation', align: 'left' },
  { key: 'risk_level', label: 'Risk', align: 'left' },
  { key: 'profit_score', label: 'Score', align: 'right' },
  { key: 'last_close', label: 'Last close', align: 'right' },
  { key: 'change_percent', label: 'Δ vs prior', align: 'right' },
  { key: 'stdev', label: 'Stdev (ann.)', align: 'right' },
  { key: 'rsi', label: 'RSI(14)', align: 'right' },
  { key: 'momentum_20d', label: 'Momentum 20d', align: 'right' },
  { key: 'horizon_positive', label: 'P(+ in horizon)', align: 'right' },
]

function AnalysisTable({ rows, selectedSymbol, onSelect, horizonSteps }) {
  const [sortKey, setSortKey] = useState('profit_score')
  const [sortDir, setSortDir] = useState('desc')

  const sortedRows = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const av = getSortValue(a, sortKey)
      const bv = getSortValue(b, sortKey)
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      return sortDir === 'asc' ? av - bv : bv - av
    })
    return copy
  }, [rows, sortKey, sortDir])

  function toggleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'symbol' ? 'asc' : 'desc')
    }
  }

  if (sortedRows.length === 0) {
    return (
      <p className="muted small-print">
        No analyzed tickers yet. Add some symbols above and refresh.
      </p>
    )
  }

  return (
    <div className="compare-table-wrap">
      <table className="compare-table analysis-table">
        <thead>
          <tr>
            {COLUMNS.map((col) => {
              const label = col.key === 'horizon_positive' && horizonSteps
                ? `P(+ in ${horizonSteps}d)`
                : col.label
              const isSorted = sortKey === col.key
              const arrow = isSorted ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''
              return (
                <th
                  key={col.key}
                  className={`analysis-th analysis-th--${col.align}${isSorted ? ' analysis-th--sorted' : ''}`}
                  onClick={() => toggleSort(col.key)}
                  scope="col"
                >
                  {label}
                  {arrow}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => {
            const sym = row.symbol
            const isSelected = sym === selectedSymbol
            const recommendation = row.scoring?.recommendation ?? 'hold'
            const change = Number(row.change_percent ?? 0)
            const momentum = Number(row.indicators?.momentum_20d ?? 0)

            return (
              <tr
                key={sym}
                className={`compare-row analysis-row analysis-row--${recommendation}${isSelected ? ' compare-row--active' : ''}`}
                onClick={() => onSelect?.(sym)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect?.(sym)
                  }
                }}
              >
                <td className="compare-ticker">{sym}</td>
                <td>
                  <RecommendationBadge recommendation={recommendation} />
                </td>
                <td>
                  <RiskBadge level={row.scoring?.risk_level} />
                </td>
                <td className="td-right">
                  <strong>{formatNumber(row.scoring?.profit_score, 1)}</strong>
                </td>
                <td className="td-right">{formatNumber(row.last_close, 2)}</td>
                <td className={`td-right ${change >= 0 ? 'text-up' : 'text-down'}`}>
                  {Number.isFinite(change) ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : '—'}
                </td>
                <td className="td-right">
                  {formatPercent(row.indicators?.stdev_annualized, 2)}
                </td>
                <td className="td-right">
                  {formatNumber(row.indicators?.rsi_14, 1)}
                </td>
                <td className={`td-right ${momentum >= 0 ? 'text-up' : 'text-down'}`}>
                  {formatSignedPercent(row.indicators?.momentum_20d, 2)}
                </td>
                <td className="td-right">
                  {formatPercent(row.markov?.horizon_positive_probability, 1)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default AnalysisTable
