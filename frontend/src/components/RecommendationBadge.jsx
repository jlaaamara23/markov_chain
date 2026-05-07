const RECOMMENDATION_LABEL = {
  strong_buy: 'Strong buy',
  buy: 'Buy',
  hold: 'Hold',
  avoid: 'Avoid',
}

function RecommendationBadge({ recommendation }) {
  const key = typeof recommendation === 'string' ? recommendation : 'hold'
  const className = `rec-badge rec-badge--${key}`
  return <span className={className}>{RECOMMENDATION_LABEL[key] ?? 'Hold'}</span>
}

export default RecommendationBadge
