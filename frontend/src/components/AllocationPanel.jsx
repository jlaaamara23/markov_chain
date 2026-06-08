import { useMemo, useState } from 'react'
import { ALLOCATION_SOURCES, pickSource } from '../utils/calculationSources'
import RecommendationBadge from './RecommendationBadge'
import RiskBadge from './RiskBadge'
import TraceableValue from './TraceableValue'
import { computeAllocation } from '../utils/allocation'

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

function formatPercent(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return '—'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

function formatSignedPercent(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return '—'
  const num = Number(value) * 100
  return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`
}

function TopPickCallout({ topPick, amount, currency }) {
  if (!topPick) {
    return (
      <article className="card top-pick-card top-pick-card--empty">
        <p className="top-pick-card__eyebrow">Top pick for big profit</p>
        <h3 className="top-pick-card__title">No buy-rated stocks yet</h3>
        <p className="muted small-print">
          Add some tickers above and refresh — once any of them score above &ldquo;avoid&rdquo;
          we&apos;ll surface the strongest one here.
        </p>
      </article>
    )
  }

  const score = Number(topPick.scoring?.profit_score ?? 0)
  const expectedNext = Number(topPick.markov?.expected_return_next_day ?? 0)
  const horizonProb = Number(topPick.markov?.horizon_positive_probability ?? 0)
  const horizonSteps = topPick.markov?.horizon_steps ?? '?'
  const validAmount = Number.isFinite(Number(amount)) && Number(amount) > 0 ? Number(amount) : 0
  const expectedNextValue = validAmount * (1 + expectedNext)
  const expectedGain = validAmount * expectedNext
  const lastClose = Number(topPick.last_close ?? 0)
  const sharesIfAllIn = lastClose > 0 ? validAmount / lastClose : 0

  return (
    <article className="card top-pick-card">
      <p className="top-pick-card__eyebrow">Top pick for big profit</p>
      <div className="top-pick-card__row">
        <div className="top-pick-card__heading">
          <h3 className="top-pick-card__title">
            {topPick.symbol}
            {topPick.name && (
              <span className="top-pick-card__name"> · {topPick.name}</span>
            )}
          </h3>
          <p className="muted small-print">
            Highest profit score in your watchlist
            {Number.isFinite(score) ? ` (${score.toFixed(1)} / 100)` : ''}.
          </p>
        </div>
        <div className="top-pick-card__badges">
          <RecommendationBadge recommendation={topPick.scoring?.recommendation} />
          <RiskBadge level={topPick.scoring?.risk_level} />
        </div>
      </div>

      <dl className="top-pick-card__stats">
        <div>
          <dt>Profit score</dt>
          <dd>
            <TraceableValue
              value={`${score.toFixed(1)} / 100`}
              source={pickSource(topPick.calculation_sources, 'profit_score')}
            />
          </dd>
        </div>
        <div>
          <dt>Markov expected next day</dt>
          <dd className={expectedNext >= 0 ? 'text-up' : 'text-down'}>
            <TraceableValue
              value={formatSignedPercent(expectedNext, 3)}
              source={pickSource(
                topPick.calculation_sources,
                'expected_return_next_day',
                ALLOCATION_SOURCES.top_pick_expected_next_day,
              )}
            />
          </dd>
        </div>
        <div>
          <dt>P(positive in {horizonSteps}d)</dt>
          <dd>
            <TraceableValue
              value={formatPercent(horizonProb, 1)}
              source={pickSource(
                topPick.calculation_sources,
                'horizon_positive_probability',
                ALLOCATION_SOURCES.top_pick_horizon_positive,
              )}
            />
          </dd>
        </div>
        <div>
          <dt>Last close</dt>
          <dd>
            <TraceableValue
              value={formatMoney(lastClose, currency)}
              source={pickSource(topPick.calculation_sources, 'last_close')}
            />
          </dd>
        </div>
      </dl>

      {validAmount > 0 && (
        <div className="top-pick-card__what-if">
          <p className="muted small-print">
            <strong>If you put all {formatMoney(validAmount, currency)} here:</strong>{' '}
            ≈{' '}
            <TraceableValue
              value={`${sharesIfAllIn.toFixed(2)} shares`}
              source={{
                ...ALLOCATION_SOURCES.shares_estimated,
                inputs: { allocation_dollars: validAmount, last_close: lastClose },
              }}
            />{' '}
            · estimated next-day value{' '}
            <TraceableValue
              value={formatMoney(expectedNextValue, currency)}
              source={{
                ...ALLOCATION_SOURCES.top_pick_what_if_value,
                inputs: {
                  invest_amount: validAmount,
                  expected_return_next_day: expectedNext,
                },
              }}
            />{' '}
            <span className={expectedGain >= 0 ? 'text-up' : 'text-down'}>
              (
              <TraceableValue
                value={`${expectedGain >= 0 ? '+' : ''}${formatMoney(expectedGain, currency)}`}
                source={{
                  method: 'markov_chain_next_day',
                  formula: 'invest_amount × expected_return_next_day',
                  description: 'Expected dollar gain/loss on the next day from the Markov forecast.',
                  inputs: { invest_amount: validAmount, expected_return_next_day: expectedNext },
                }}
              />
              )
            </span>
          </p>
        </div>
      )}
    </article>
  )
}

function BucketHeader({ bucket, currency }) {
  return (
    <div className={`bucket-header bucket-header--${bucket.id}`}>
      <div>
        <p className="bucket-header__title">{bucket.label}</p>
        <p className="bucket-header__desc muted small-print">{bucket.description}</p>
      </div>
      <div className="bucket-header__stats">
        <div>
          <span className="bucket-header__stat-label">Target</span>
          <span className="bucket-header__stat-value">
            <TraceableValue
              value={`${(bucket.weight * 100).toFixed(0)}%`}
              source={{
                ...ALLOCATION_SOURCES.bucket_target_weight,
                inputs: { bucket: bucket.id, nominal_weight: bucket.weight },
              }}
            />
          </span>
        </div>
        <div>
          <span className="bucket-header__stat-label">Allocated</span>
          <span className="bucket-header__stat-value">
            <TraceableValue
              value={formatMoney(bucket.amount, currency)}
              source={{
                ...ALLOCATION_SOURCES.bucket_allocated_amount,
                inputs: {
                  bucket: bucket.id,
                  effective_weight: bucket.effectiveWeight,
                  amount: bucket.amount,
                },
              }}
            />
          </span>
        </div>
      </div>
    </div>
  )
}

function AllocationPanel({ results }) {
  const [amountInput, setAmountInput] = useState('10000')

  const allocation = useMemo(
    () => computeAllocation(results ?? [], amountInput),
    [results, amountInput],
  )

  const currency = useMemo(() => {
    for (const r of results ?? []) {
      if (r?.currency) return r.currency
    }
    return 'USD'
  }, [results])

  const groupedByBucket = useMemo(() => {
    const map = { strong_growth: [], medium_risk: [], stable: [] }
    for (const a of allocation.allocations) {
      if (map[a.bucket]) map[a.bucket].push(a)
    }
    return map
  }, [allocation.allocations])

  const presetAmounts = [1000, 5000, 10000, 25000, 100000]

  return (
    <section className="page-section">
      <div className="card allocation-controls">
        <div className="allocation-controls__row">
          <div>
            <label className="stocks-label" htmlFor="alloc-amount">
              Amount to invest
            </label>
            <div className="allocation-amount-wrap">
              <span className="allocation-amount-symbol">$</span>
              <input
                id="alloc-amount"
                className="stocks-input allocation-amount-input"
                type="number"
                min={0}
                step={100}
                inputMode="decimal"
                value={amountInput}
                onChange={(e) => setAmountInput(e.target.value)}
                placeholder="e.g. 10000"
              />
            </div>
          </div>
          <div className="allocation-presets">
            {presetAmounts.map((p) => (
              <button
                key={p}
                type="button"
                className={
                  Number(amountInput) === p
                    ? 'risk-filter risk-filter--active'
                    : 'risk-filter'
                }
                onClick={() => setAmountInput(String(p))}
              >
                {formatMoney(p, currency).replace(/[.,]00$/, '')}
              </button>
            ))}
          </div>
        </div>
        <p className="muted small-print">
          The amount is split 50% / 30% / 20% across <strong>strong-growth</strong>,{' '}
          <strong>medium-risk</strong>, and <strong>stable</strong> buckets. Within each
          bucket, dollars are weighted by profit score. Stocks rated &ldquo;avoid&rdquo; are
          excluded.
        </p>
      </div>

      <TopPickCallout
        topPick={allocation.topPick}
        amount={allocation.amount}
        currency={currency}
      />

      {allocation.warnings.length > 0 && (
        <div className="card allocation-warning-card">
          <p className="allocation-warning-card__title">Heads up</p>
          <ul className="muted small-print">
            {allocation.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {allocation.allocations.length > 0 ? (
        <div className="card">
          <div className="analysis-header">
            <h2 className="subsection-title">
              Recommended portfolio · {formatMoney(allocation.amount, currency)}
            </h2>
            {allocation.cashRemaining > 0 && (
              <p className="muted small-print">
                Cash remaining:{' '}
                <TraceableValue
                  value={formatMoney(allocation.cashRemaining, currency)}
                  source={{
                    method: 'rounding_remainder',
                    formula: 'total_invest − Σ rounded_stock_allocations',
                    description:
                      'Leftover cash from cent rounding; added to the highest-score stock when possible.',
                    inputs: { cash_remaining: allocation.cashRemaining },
                  }}
                />
              </p>
            )}
          </div>
          <div className="allocation-buckets">
            {allocation.buckets.map((bucket) => {
              const stocks = groupedByBucket[bucket.id] ?? []
              if (bucket.count === 0) {
                return (
                  <div key={bucket.id} className="allocation-bucket allocation-bucket--empty">
                    <BucketHeader bucket={bucket} currency={currency} />
                    <p className="muted small-print">
                      No matching stocks in your watchlist for this bucket.
                    </p>
                  </div>
                )
              }
              return (
                <div key={bucket.id} className="allocation-bucket">
                  <BucketHeader bucket={bucket} currency={currency} />
                  <div className="compare-table-wrap">
                    <table className="compare-table allocation-table">
                      <thead>
                        <tr>
                          <th>Ticker</th>
                          <th>Recommendation</th>
                          <th>Risk</th>
                          <th className="td-right">Score</th>
                          <th className="td-right">Allocation</th>
                          <th className="td-right">% of total</th>
                          <th className="td-right">≈ Shares</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stocks.map((a) => (
                          <tr
                            key={a.symbol}
                            className={`compare-row analysis-row analysis-row--${a.recommendation}`}
                          >
                            <td className="compare-ticker">{a.symbol}</td>
                            <td>
                              <RecommendationBadge recommendation={a.recommendation} />
                            </td>
                            <td>
                              <RiskBadge level={a.riskLevel} />
                            </td>
                            <td className="td-right">
                              <TraceableValue
                                value={a.profitScore.toFixed(1)}
                                source={pickSource(
                                  results.find((r) => r.symbol === a.symbol)?.calculation_sources,
                                  'profit_score',
                                )}
                              />
                            </td>
                            <td className="td-right">
                              <strong>
                                <TraceableValue
                                  value={formatMoney(a.amount, currency)}
                                  source={{
                                    ...ALLOCATION_SOURCES.stock_allocation_amount,
                                    inputs: {
                                      symbol: a.symbol,
                                      bucket: a.bucket,
                                      profit_score: a.profitScore,
                                      amount: a.amount,
                                    },
                                  }}
                                />
                              </strong>
                            </td>
                            <td className="td-right">
                              <TraceableValue
                                value={`${(a.percent * 100).toFixed(2)}%`}
                                source={{
                                  ...ALLOCATION_SOURCES.stock_percent_of_total,
                                  inputs: { symbol: a.symbol, percent: a.percent },
                                }}
                              />
                            </td>
                            <td className="td-right">
                              <TraceableValue
                                value={
                                  a.sharesEstimated > 0 ? a.sharesEstimated.toFixed(2) : '—'
                                }
                                source={{
                                  ...ALLOCATION_SOURCES.shares_estimated,
                                  inputs: {
                                    symbol: a.symbol,
                                    allocation: a.amount,
                                    last_close: a.lastClose,
                                  },
                                }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        allocation.amount > 0 && (
          <div className="card muted-card">
            <p className="muted small-print">
              Nothing to allocate yet — add or refresh tickers above.
            </p>
          </div>
        )
      )}

      {allocation.skipped.length > 0 && (
        <div className="card muted-card">
          <p className="muted small-print">
            <strong>Excluded from allocation:</strong>{' '}
            {allocation.skipped
              .map((s) => `${s.symbol} (${s.reason})`)
              .join(', ')}
          </p>
        </div>
      )}
    </section>
  )
}

export default AllocationPanel
