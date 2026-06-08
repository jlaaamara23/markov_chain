import { useId, useState } from 'react'

function formatInputs(inputs) {
  if (!inputs || typeof inputs !== 'object') return null
  return Object.entries(inputs).map(([key, value]) => {
    const display =
      Array.isArray(value) ? value.join(' → ') : typeof value === 'object' ? JSON.stringify(value) : String(value)
    return (
      <li key={key}>
        <code>{key}</code>: {display}
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
          <p className="traceable-source__method">
            <strong>Method:</strong> {source.method?.replace(/_/g, ' ') ?? '—'}
          </p>
          {source.formula && (
            <p className="traceable-source__formula">
              <strong>Formula:</strong> <code>{source.formula}</code>
            </p>
          )}
          {source.description && <p className="traceable-source__desc">{source.description}</p>}
          {source.inputs && (
            <>
              <p className="traceable-source__inputs-title">
                <strong>Inputs</strong>
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
