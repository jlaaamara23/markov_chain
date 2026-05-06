import { useNavigate } from 'react-router-dom'

function HomePage() {
  const navigate = useNavigate()

  return (
    <section className="page">
      <div className="card hero-card">
        <p className="eyebrow">AI + Markov Chains</p>
        <h1>TradeMind AI Dashboard</h1>
        <p className="muted">
          Monitor market state transitions and run one-click predictions powered by a
          Markov model.
        </p>
        <button className="primary-btn" onClick={() => navigate('/dashboard')}>
          Run Prediction
        </button>
      </div>
    </section>
  )
}

export default HomePage
