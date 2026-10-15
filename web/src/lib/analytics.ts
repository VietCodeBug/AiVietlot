export interface Draw {
  draw_id: number;
  draw_date: string;
  n1: number;
  n2: number;
  n3: number;
  n4: number;
  n5: number;
  n6: number;
  source_name: string;
  source_url: string;
  fetched_at: string;
  verification_status: string;
}

export type Ticket = number[];
export type Algorithm = 'uniform' | 'frequency' | 'recency';

export interface NumberStat {
  number: number;
  count: number;
  /** Share of draws containing this number, rather than share of all balls. */
  rate: number;
  /** Number of consecutive absent draws, counting back from the newest draw. */
  gap: number;
  posteriorMean: number;
  lower: number;
  upper: number;
}

export interface Summary {
  numberStats: NumberStat[];
  pairStats: { pair: [number, number]; count: number }[];
  sumDistribution: { sum: number; count: number }[];
  parityDistribution: { odd: number; count: number }[];
  /** Counts of individual balls in each numerical band; sums to six per draw. */
  rangeDistribution: { label: string; count: number }[];
  totalDraws: number;
  firstDate: string | null;
  lastDate: string | null;
  intervalApproximation: 'normal-95%';
}

export interface GenerateOptions {
  algorithm: Algorithm;
  count: number;
  seed: string | number;
  /** Decay half life measured in draws, not calendar days. Default: 30. */
  halfLife?: number;
  /** Positive pseudocount for every number, including unseen numbers. Default: 1. */
  smoothing?: number;
}

const BALLS = 45;
const TICKET_SIZE = 6;
const PRIOR_STRENGTH = 45;
const PRIOR_SUCCESSES = 6;
const Z_95 = 1.959963984540054;
export const TOTAL_COMBINATIONS = 8_145_060;
export const EXPECTED_MATCHES = TICKET_SIZE * TICKET_SIZE / BALLS;

export function numbers(draw: Draw): number[] {
  return [draw.n1, draw.n2, draw.n3, draw.n4, draw.n5, draw.n6];
}

function scopedDraws(draws: readonly Draw[]): Draw[] {
  const unique = new Map<number, Draw>();
  for (const draw of draws) {
    const values = numbers(draw);
    const day = new Date(`${draw.draw_date}T00:00:00Z`);
    if (!Number.isSafeInteger(draw.draw_id) || draw.draw_id < 1
      || !/^\d{4}-\d{2}-\d{2}$/.test(draw.draw_date)
      || !Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== draw.draw_date
      || values.some(n => !Number.isInteger(n) || n < 1 || n > BALLS)
      || new Set(values).size !== TICKET_SIZE) {
      throw new Error('Dữ liệu kỳ quay không hợp lệ.');
    }
    const previous = unique.get(draw.draw_id);
    if (previous && (previous.draw_date !== draw.draw_date
      || numbers(previous).sort((a, b) => a - b).join(',') !== [...values].sort((a, b) => a - b).join(','))) {
      throw new Error(`Kết quả mâu thuẫn cho kỳ #${draw.draw_id}.`);
    }
    if (!previous) unique.set(draw.draw_id, draw);
  }
  return [...unique.values()].sort((a, b) => b.draw_date.localeCompare(a.draw_date) || b.draw_id - a.draw_id);
}

/** All calculations use only the supplied scope; no cached or global draw data. */
export function summarize(draws: readonly Draw[]): Summary {
  const scope = scopedDraws(draws);
  const totalDraws = scope.length;
  const counts = Array<number>(BALLS).fill(0);
  const gaps = Array<number>(BALLS).fill(totalDraws);
  const pairs = new Map<string, { pair: [number, number]; count: number }>();
  const sums = new Map<number, number>();
  const parity = Array<number>(TICKET_SIZE + 1).fill(0);
  const ranges = ['01–09', '10–19', '20–29', '30–39', '40–45'].map(label => ({ label, count: 0 }));
  scope.forEach((draw, age) => {
    const values = numbers(draw).sort((a, b) => a - b);
    for (const value of values) {
      counts[value - 1] += 1;
      if (gaps[value - 1] === totalDraws) gaps[value - 1] = age;
      ranges[value < 10 ? 0 : Math.floor(value / 10)].count += 1;
    }
    for (let i = 0; i < values.length; i += 1) {
      for (let j = i + 1; j < values.length; j += 1) {
        const key = `${values[i]},${values[j]}`;
        const previous = pairs.get(key);
        if (previous) previous.count += 1;
        else pairs.set(key, { pair: [values[i], values[j]], count: 1 });
      }
    }
    const sum = values.reduce((a, b) => a + b, 0);
    sums.set(sum, (sums.get(sum) ?? 0) + 1);
    parity[values.filter(n => n % 2 === 1).length] += 1;
  });
  const numberStats = counts.map((count, index): NumberStat => {
    // Per-number inclusion is a Bernoulli event with prior Beta(6,39).
    const alpha = PRIOR_SUCCESSES + count;
    const beta = PRIOR_STRENGTH - PRIOR_SUCCESSES + totalDraws - count;
    const strength = alpha + beta;
    const posteriorMean = alpha / strength;
    const standardDeviation = Math.sqrt(alpha * beta / (strength * strength * (strength + 1)));
    return {
      number: index + 1,
      count,
      rate: totalDraws ? count / totalDraws : 0,
      gap: gaps[index],
      posteriorMean,
      lower: Math.max(0, posteriorMean - Z_95 * standardDeviation),
      upper: Math.min(1, posteriorMean + Z_95 * standardDeviation),
    };
  });
  return {
    numberStats,
    pairStats: [...pairs.values()].sort((a, b) => b.count - a.count || a.pair[0] - b.pair[0] || a.pair[1] - b.pair[1]).slice(0, 20),
    sumDistribution: [...sums].sort((a, b) => a[0] - b[0]).map(([sum, count]) => ({ sum, count })),
    parityDistribution: parity.map((count, odd) => ({ odd, count })),
    rangeDistribution: ranges,
    totalDraws,
    firstDate: scope.at(-1)?.draw_date ?? null,
    lastDate: scope[0]?.draw_date ?? null,
    intervalApproximation: 'normal-95%',
  };
}

function choose(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  let result = 1;
  for (let i = 1; i <= Math.min(k, n - k); i += 1) result = result * (n - i + 1) / i;
  return Math.round(result);
}

/** Hypergeometric probabilities for one fixed six-number ticket. */
export function theoreticalProbabilities(): { matches: number; probability: number; oneIn: number }[] {
  return Array.from({ length: TICKET_SIZE + 1 }, (_, matches) => {
    const probability = choose(TICKET_SIZE, matches) * choose(BALLS - TICKET_SIZE, TICKET_SIZE - matches) / TOTAL_COMBINATIONS;
    return { matches, probability, oneIn: 1 / probability };
  });
}

/** Distinct tickets in the same draw cover mutually exclusive jackpot outcomes. */
export function ticketJackpotProbability(uniqueTickets: number): number {
  if (!Number.isSafeInteger(uniqueTickets) || uniqueTickets < 0 || uniqueTickets > TOTAL_COMBINATIONS) {
    throw new Error(`Số vé khác nhau phải nằm trong 0–${TOTAL_COMBINATIONS}.`);
  }
  return uniqueTickets / TOTAL_COMBINATIONS;
}

export function expectedMatches(): number {
  return EXPECTED_MATCHES;
}

function seededRandom(seed: string | number): () => number {
  let state = 2166136261;
  for (const character of `${typeof seed}:${seed}`) {
    state = Math.imul(state ^ character.charCodeAt(0), 16777619);
  }
  return () => {
    state = (state + 0x6D2B79F5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/** Weighted draws without replacement within a ticket; duplicate tickets are rejected. */
export function generateTickets(draws: readonly Draw[], options: GenerateOptions): Ticket[] {
  const { algorithm, count, seed, halfLife = 30, smoothing = 1 } = options;
  if (!['uniform', 'frequency', 'recency'].includes(algorithm)
    || !Number.isInteger(count) || count < 0 || count > 1000
    || !Number.isFinite(halfLife) || halfLife <= 0
    || !Number.isFinite(smoothing) || smoothing <= 0
    || (typeof seed !== 'string' && (typeof seed !== 'number' || !Number.isFinite(seed)))) {
    throw new Error('Tham số sinh vé không hợp lệ (0–1.000 vé, smoothing và half life dương).');
  }
  const scope = scopedDraws(draws);
  const weights = Array<number>(BALLS).fill(algorithm === 'uniform' ? 1 : smoothing);
  if (algorithm !== 'uniform') {
    scope.forEach((draw, age) => {
      const weight = algorithm === 'recency' ? Math.exp(-Math.LN2 * age / halfLife) : 1;
      for (const value of numbers(draw)) weights[value - 1] += weight;
    });
  }
  const maxWeight = Math.max(...weights);
  const scaledWeights = weights.map(weight => weight / maxWeight);
  const random = seededRandom(seed);
  const tickets: Ticket[] = [];
  const seen = new Set<string>();
  const maxAttempts = Math.max(1000, count * 500);
  for (let attempt = 0; tickets.length < count && attempt < maxAttempts; attempt += 1) {
    const remaining = scaledWeights.map((weight, index) => ({ weight, number: index + 1 }));
    const ticket: Ticket = [];
    for (let position = 0; position < TICKET_SIZE; position += 1) {
      let target = random() * remaining.reduce((total, item) => total + item.weight, 0);
      let selected = remaining.length - 1;
      for (let i = 0; i < remaining.length; i += 1) {
        target -= remaining[i].weight;
        if (target < 0) { selected = i; break; }
      }
      ticket.push(remaining[selected].number);
      remaining.splice(selected, 1);
    }
    ticket.sort((a, b) => a - b);
    const key = ticket.join(',');
    if (!seen.has(key)) {
      seen.add(key);
      tickets.push(ticket);
    }
  }
  if (tickets.length !== count) {
    throw new Error('Trọng số quá tập trung để tạo đủ vé khác nhau. Hãy tăng smoothing hoặc giảm số vé.');
  }
  return tickets;
}
