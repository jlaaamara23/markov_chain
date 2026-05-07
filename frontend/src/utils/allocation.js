/**
 * Portfolio allocation algorithm.
 *
 * Inputs: the analyzed results array from /analyze, and a money amount.
 * Output: a deterministic split of the amount across the stocks using:
 *
 *   - "avoid"-rated stocks are excluded entirely.
 *   - Each remaining stock is placed into one of three buckets:
 *       * stable        -> low-risk stocks
 *       * strong_growth -> profit_score >= 60 AND risk in (medium, high)
 *       * medium_risk   -> everything else that's not avoided
 *   - Bucket target weights: 50% / 30% / 20% (strong / medium / stable).
 *   - If a bucket is empty, its weight is redistributed across the
 *     non-empty buckets in proportion to their original weights.
 *   - Inside each bucket, dollars are split proportionally to profit_score.
 *   - Per-stock dollar amounts are rounded to cents; any rounding remainder
 *     is added to the highest-score stock so totals always reconcile.
 *
 * The function is pure and synchronous so it can run on every keystroke.
 */

export const BUCKET_WEIGHTS = {
  strong_growth: 0.5,
  medium_risk: 0.3,
  stable: 0.2,
}

export const BUCKET_LABEL = {
  strong_growth: 'Strong-growth stocks',
  medium_risk: 'Medium-risk stocks',
  stable: 'Stable stocks',
}

export const BUCKET_DESCRIPTION = {
  strong_growth: 'High profit-potential picks willing to take volatility.',
  medium_risk: 'Balanced picks with moderate risk.',
  stable: 'Lower-volatility picks for capital preservation.',
}

const STRONG_GROWTH_MIN_SCORE = 60

export function bucketOf(result) {
  const recommendation = result?.scoring?.recommendation
  if (recommendation === 'avoid') return null

  const risk = result?.scoring?.risk_level
  const score = Number(result?.scoring?.profit_score ?? 0)

  if (risk === 'low') return 'stable'
  if (score >= STRONG_GROWTH_MIN_SCORE) return 'strong_growth'
  return 'medium_risk'
}

function effectiveBucketWeights(presentBuckets) {
  const total = presentBuckets.reduce((sum, b) => sum + BUCKET_WEIGHTS[b], 0)
  if (total <= 0) return {}
  const out = {}
  for (const b of presentBuckets) {
    out[b] = BUCKET_WEIGHTS[b] / total
  }
  return out
}

function roundToCents(value) {
  return Math.round(value * 100) / 100
}

function pickTopPick(results) {
  const candidates = (results ?? []).filter(
    (r) => r?.scoring?.recommendation && r.scoring.recommendation !== 'avoid',
  )
  if (candidates.length === 0) return null
  candidates.sort(
    (a, b) =>
      Number(b.scoring?.profit_score ?? 0) - Number(a.scoring?.profit_score ?? 0),
  )
  return candidates[0]
}

export function computeAllocation(results, rawAmount) {
  const amount = Number(rawAmount)
  const validAmount = Number.isFinite(amount) && amount > 0 ? amount : 0
  const list = Array.isArray(results) ? results : []

  // Group eligible stocks by bucket.
  const grouped = { strong_growth: [], medium_risk: [], stable: [] }
  const skipped = []
  for (const r of list) {
    const bucket = bucketOf(r)
    if (!bucket) {
      skipped.push({
        symbol: r.symbol,
        reason: r?.scoring?.recommendation === 'avoid'
          ? 'Recommendation = avoid'
          : 'No scoring data',
      })
      continue
    }
    grouped[bucket].push(r)
  }

  const presentBuckets = Object.keys(grouped).filter((b) => grouped[b].length > 0)
  const warnings = []

  for (const b of Object.keys(BUCKET_WEIGHTS)) {
    if (grouped[b].length === 0) {
      warnings.push(
        `No ${BUCKET_LABEL[b].toLowerCase()} in your watchlist; that ${(BUCKET_WEIGHTS[b] * 100).toFixed(0)}% has been redistributed.`,
      )
    }
  }

  const topPick = pickTopPick(list)

  if (validAmount === 0 || presentBuckets.length === 0) {
    return {
      amount: validAmount,
      buckets: Object.entries(BUCKET_WEIGHTS).map(([id, weight]) => ({
        id,
        label: BUCKET_LABEL[id],
        description: BUCKET_DESCRIPTION[id],
        weight,
        amount: 0,
        count: grouped[id].length,
      })),
      allocations: [],
      topPick,
      skipped,
      cashRemaining: validAmount,
      warnings:
        presentBuckets.length === 0 && validAmount > 0
          ? [
              ...warnings,
              'All watchlist tickers are rated "avoid" — holding the entire amount as cash.',
            ]
          : warnings,
    }
  }

  const effWeights = effectiveBucketWeights(presentBuckets)

  // Compute per-stock raw allocations (still floating-point).
  const allocations = []
  for (const bucket of presentBuckets) {
    const stocks = grouped[bucket]
    const bucketDollars = validAmount * effWeights[bucket]
    const totalScore = stocks.reduce(
      (sum, s) => sum + Math.max(1, Number(s.scoring?.profit_score ?? 0)),
      0,
    )
    for (const s of stocks) {
      const stockScore = Math.max(1, Number(s.scoring?.profit_score ?? 0))
      const ratio = totalScore > 0 ? stockScore / totalScore : 1 / stocks.length
      const dollars = bucketDollars * ratio
      const lastClose = Number(s.last_close ?? 0)
      const sharesEstimated = lastClose > 0 ? dollars / lastClose : 0
      allocations.push({
        symbol: s.symbol,
        name: s.name ?? null,
        bucket,
        amount: roundToCents(dollars),
        rawAmount: dollars,
        percent: validAmount > 0 ? dollars / validAmount : 0,
        sharesEstimated,
        profitScore: Number(s.scoring?.profit_score ?? 0),
        riskLevel: s.scoring?.risk_level ?? 'medium',
        recommendation: s.scoring?.recommendation ?? 'hold',
        recommendationColor: s.scoring?.recommendation_color ?? 'yellow',
        lastClose,
        currency: s.currency ?? null,
        expectedReturnNextDay: Number(s.markov?.expected_return_next_day ?? 0),
        horizonPositiveProbability: Number(
          s.markov?.horizon_positive_probability ?? 0,
        ),
      })
    }
  }

  // Reconcile rounding so the per-stock $ amounts sum exactly to the input.
  const allocatedSum = allocations.reduce((sum, a) => sum + a.amount, 0)
  const drift = roundToCents(validAmount - allocatedSum)
  if (allocations.length > 0 && Math.abs(drift) >= 0.01) {
    allocations.sort((a, b) => b.profitScore - a.profitScore)
    allocations[0].amount = roundToCents(allocations[0].amount + drift)
  }
  // Final display sort: highest score first.
  allocations.sort((a, b) => b.profitScore - a.profitScore)

  const cashRemaining = roundToCents(
    validAmount - allocations.reduce((sum, a) => sum + a.amount, 0),
  )

  const buckets = Object.entries(BUCKET_WEIGHTS).map(([id, weight]) => {
    const present = grouped[id].length > 0
    const effWeight = present ? effWeights[id] : 0
    return {
      id,
      label: BUCKET_LABEL[id],
      description: BUCKET_DESCRIPTION[id],
      weight,
      effectiveWeight: effWeight,
      amount: roundToCents(validAmount * effWeight),
      count: grouped[id].length,
    }
  })

  return {
    amount: validAmount,
    buckets,
    allocations,
    topPick,
    skipped,
    cashRemaining,
    warnings,
  }
}
