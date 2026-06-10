import { useId, useState } from 'react'

const INPUT_LABELS = {
  last_close: 'Last closing price',
  previous_close: 'Previous closing price',
  expected_return_next_day: 'Expected next-day return',
  expected_return_horizon: 'Expected horizon return',
  profit_score: 'Profit score',
  volatility_score: 'Volatility score',
  stdev_daily: 'Daily volatility',
  stdev_annualized: 'Yearly volatility',
  horizon_steps: 'Forecast days',
  context_len: 'Context length',
  context: 'Recent return ranges',
  weights: 'Score weights',
  component: 'Part value',
  weight: 'Weight',
  contribution: 'Points added',
  cash_remaining: 'Cash left over',
  invest_amount: 'Investment amount',
  allocation_dollars: 'Dollars allocated',
}

function humanizeKey(key) {
  return INPUT_LABELS[key] ?? key.replace(/_/g, ' ')
}

function formatInputs(inputs) {
  if (!inputs || typeof inputs !== 'object') return null
  return Object.entries(inputs).map(([key, value]) => {
    let display
    if (Array.isArray(value)) {
      display = value.join(' → ')
    } else if (typeof value === 'object') {
      display = JSON.stringify(value)
    } else {
      display = String(value)
    }
    return (
      <li key={key}>
        <strong>{humanizeKey(key)}:</strong> {display}
      </li>
    )
  })
}

function TraceableValue({ value, source, className = '' }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()

  if (!source) {
    return <span className={className}>{value}</span>
  }

  return (
    <span className={`traceable-wrap${className ? ` ${className}` : ''}`}>
      <button
        type="button"
        className="traceable-value"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        aria-expanded={open}
        aria-controls={panelId}
        title="Click to see how this number was calculated"
      >
        {value}
        <span className="traceable-value__icon" aria-hidden="true">
          ⓘ
        </span>
      </button>
      {open && (
        <div id={panelId} className="traceable-source" role="region" aria-label="Calculation source">
          {source.formula && (
            <p className="traceable-source__formula">
              <strong>How we calculate it:</strong> {source.formula}
            </p>
          )}
          {source.description && (
            <p className="traceable-source__desc">
              <strong>What it means:</strong> {source.description}
            </p>
          )}
          {source.inputs && Object.keys(source.inputs).length > 0 && (
            <>
              <p className="traceable-source__inputs-title">
                <strong>Numbers used</strong>
              </p>
              <ul className="traceable-source__inputs">{formatInputs(source.inputs)}</ul>
            </>
          )}
        </div>
      )}
    </span>
  )
}

export default TraceableValue
