function StatCard({ label, value, hint, accent }) {
  const accentClass = accent ? ` stat-card--${accent}` : ''
  return (
    <article className={`card stat-card${accentClass}`}>
      <p className="stat-card__label">{label}</p>
      <p className="stat-card__value">{value}</p>
      {hint && <p className="stat-card__hint">{hint}</p>}
    </article>
  )
}

export default StatCard
