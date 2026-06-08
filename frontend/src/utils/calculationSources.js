/** Client-side formulas for values computed in the browser (e.g. portfolio allocation). */

export const ALLOCATION_SOURCES = {
  bucket_target_weight: {
    method: 'portfolio_bucket_weight',
    formula: 'strong_growth 50% · medium_risk 30% · stable 20% (redistributed if a bucket is empty)',
    description:
      'Default bucket targets. If a bucket has no eligible stocks, its weight is split across the remaining buckets.',
    inputs: { strong_growth: 0.5, medium_risk: 0.3, stable: 0.2 },
  },
  bucket_allocated_amount: {
    method: 'portfolio_bucket_weight',
    formula: 'total_invest × effective_bucket_weight',
    description: 'Dollar amount assigned to this risk bucket before splitting across stocks inside it.',
    inputs: {},
  },
  stock_allocation_amount: {
    method: 'profit_score_weighting',
    formula: 'bucket_dollars × (stock_profit_score / Σ scores in bucket)',
    description:
      'Within each bucket, dollars are split in proportion to each stock’s Markov profit score (minimum weight 1).',
    inputs: {},
  },
  stock_percent_of_total: {
    method: 'profit_score_weighting',
    formula: 'stock_allocation / total_invest × 100',
    description: 'Share of the total investment amount allocated to this ticker.',
    inputs: {},
  },
  shares_estimated: {
    method: 'share_estimate',
    formula: 'allocation_dollars / last_close',
    description: 'Approximate whole-share count if the full allocation were used at the last close.',
    inputs: {},
  },
  top_pick_expected_next_day: {
    method: 'markov_chain_next_day',
    formula: 'Σ P(next_state) × mean_return(state)',
    description: 'Markov expected next-day return for the highest-scoring non-avoid ticker.',
    inputs: {},
  },
  top_pick_horizon_positive: {
    method: 'markov_chain_matrix_power',
    formula: 'one_hot(current_state) @ P^n, sum bins ≥ 0%',
    description: 'Horizon P(+) for the top pick from deterministic Markov matrix power.',
    inputs: {},
  },
  top_pick_what_if_value: {
    method: 'markov_chain_next_day',
    formula: 'invest_amount × (1 + expected_return_next_day)',
    description: 'Hypothetical next-day portfolio value if the entire amount were in the top pick.',
    inputs: {},
  },
}

export function pickSource(sources, key, fallback = null) {
  if (sources?.[key]) return sources[key]
  if (ALLOCATION_SOURCES[key]) return ALLOCATION_SOURCES[key]
  return fallback
}

/** Table column key → calculation_sources key */
export const TABLE_COLUMN_SOURCES = {
  profit_score: 'profit_score',
  last_close: 'last_close',
  change_percent: 'change_percent',
  stdev: 'stdev_annualized',
  rsi: 'rsi_14',
  momentum_20d: 'momentum_20d',
  horizon_positive: 'horizon_positive_probability',
}
