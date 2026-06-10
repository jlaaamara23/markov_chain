/** Client-side plain-language notes for values computed in the browser. */

export const ALLOCATION_SOURCES = {
  bucket_target_weight: {
    method: 'portfolio_split',
    formula: 'Strong-growth 50%, medium-risk 30%, stable 20% of your investment.',
    description:
      'Default split across risk buckets. If a bucket is empty, its share goes to the other buckets.',
    inputs: { strong_growth: 0.5, medium_risk: 0.3, stable: 0.2 },
  },
  bucket_allocated_amount: {
    method: 'portfolio_split',
    formula: 'Total investment × this bucket’s share.',
    description: 'How many dollars go to this risk group before splitting between stocks.',
    inputs: {},
  },
  stock_allocation_amount: {
    method: 'profit_score_weighting',
    formula: 'Bucket dollars × (this stock’s score ÷ total scores in the bucket).',
    description:
      'Within each bucket, higher profit-score stocks get a larger slice of the money.',
    inputs: {},
  },
  stock_percent_of_total: {
    method: 'profit_score_weighting',
    formula: 'Stock allocation ÷ total investment × 100.',
    description: 'What percent of your total investment goes to this stock.',
    inputs: {},
  },
  shares_estimated: {
    method: 'share_estimate',
    formula: 'Allocation dollars ÷ last closing price.',
    description: 'Rough number of shares you could buy at the last closing price.',
    inputs: {},
  },
  top_pick_expected_next_day: {
    method: 'markov_forecast',
    formula: 'For each outcome: (chance × average return) — add up.',
    description: 'Expected next-day return for the top-scoring stock.',
    inputs: {},
  },
  top_pick_horizon_positive: {
    method: 'markov_forecast',
    formula: 'Add chances of all flat or positive outcomes over the forecast period.',
    description: 'Chance the top pick ends flat or up over the horizon.',
    inputs: {},
  },
  top_pick_what_if_value: {
    method: 'markov_forecast',
    formula: 'Investment amount × (1 + expected next-day return).',
    description: 'What your money could be worth the next day if all went to the top pick.',
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
