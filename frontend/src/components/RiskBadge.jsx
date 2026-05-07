const RISK_LABEL = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
}

function RiskBadge({ level }) {
  const normalized = typeof level === 'string' ? level.toLowerCase() : 'medium'
  const className = `risk-badge risk-badge--${normalized}`
  return <span className={className}>{RISK_LABEL[normalized] ?? 'Medium risk'}</span>
}

export default RiskBadge
