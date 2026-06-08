import TraceableValue from './TraceableValue'

function StatCard({ label, value, hint, accent, source }) {
  const accentClass = accent ? ` stat-card--${accent}` : ''
  const valueNode =
    source && typeof value === 'string' ? (
      <TraceableValue value={value} source={source} />
    ) : (
      value
    )
  return (
    <article className={`card stat-card${accentClass}`}>
      <p className="stat-card__label">{label}</p>
      <p className="stat-card__value">{valueNode}</p>
      {hint && <p className="stat-card__hint">{hint}</p>}
    </article>
  )
}

export default StatCard
