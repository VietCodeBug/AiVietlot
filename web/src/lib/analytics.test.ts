import { describe, expect, it } from 'vitest';
import {
  EXPECTED_MATCHES, TOTAL_COMBINATIONS, expectedMatches, generateTickets, numbers,
  summarize, theoreticalProbabilities, ticketJackpotProbability,
  type Algorithm, type Draw,
} from './analytics';

function draw(id: number, date: string, values: number[]): Draw {
  return {
    draw_id: id, draw_date: date,
    n1: values[0], n2: values[1], n3: values[2], n4: values[3], n5: values[4], n6: values[5],
    source_name: 'fixture', source_url: 'https://example.test/draw',
    fetched_at: '2026-10-15T00:00:00Z', verification_status: 'secondary',
  };
}

const older = draw(1, '2016-07-20', [2, 17, 33, 37, 38, 45]);
const newer = draw(2, '2016-07-22', [1, 2, 3, 4, 5, 6]);

describe('theoretical Mega 6/45 probabilities', () => {
  it('covers every outcome, with the exact jackpot odds and 0.8 expected matches', () => {
    const outcomes = theoreticalProbabilities();
    expect(outcomes.map(row => row.matches)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(outcomes.reduce((sum, row) => sum + row.probability, 0)).toBeCloseTo(1, 14);
    expect(outcomes[6].probability).toBe(1 / 8_145_060);
    expect(outcomes[6].oneIn).toBe(8_145_060);
    expect(outcomes[5].probability).toBe(234 / TOTAL_COMBINATIONS);
    expect(outcomes.reduce((sum, row) => sum + row.matches * row.probability, 0)).toBeCloseTo(0.8, 14);
    expect(EXPECTED_MATCHES).toBe(0.8);
    expect(expectedMatches()).toBe(0.8);
  });

  it('adds mutually exclusive jackpot outcomes for distinct tickets in one draw', () => {
    expect(ticketJackpotProbability(0)).toBe(0);
    expect(ticketJackpotProbability(100)).toBe(100 / TOTAL_COMBINATIONS);
    expect(ticketJackpotProbability(TOTAL_COMBINATIONS)).toBe(1);
    for (const invalid of [-1, 1.5, Infinity, NaN, TOTAL_COMBINATIONS + 1]) {
      expect(() => ticketJackpotProbability(invalid)).toThrow();
    }
  });
});

describe('statistics within the selected scope', () => {
  it('uses only supplied draws and measures gaps from the latest supplied draw', () => {
    const both = summarize([older, newer]);
    const onlyOlder = summarize([older]);
    const two = both.numberStats.find(row => row.number === 2)!;
    const seventeen = both.numberStats.find(row => row.number === 17)!;
    expect(both.totalDraws).toBe(2);
    expect(both.firstDate).toBe('2016-07-20');
    expect(both.lastDate).toBe('2016-07-22');
    expect(two).toMatchObject({ count: 2, rate: 1, gap: 0 });
    expect(seventeen).toMatchObject({ count: 1, rate: 0.5, gap: 1 });
    expect(both.numberStats.find(row => row.number === 44)).toMatchObject({ count: 0, rate: 0, gap: 2 });
    expect(onlyOlder.numberStats.find(row => row.number === 17)).toMatchObject({ count: 1, rate: 1, gap: 0 });
    expect(onlyOlder.numberStats.find(row => row.number === 1)).toMatchObject({ count: 0, rate: 0, gap: 1 });
  });

  it('preserves counts across sum, parity, pair and ball-band distributions', () => {
    const summary = summarize([newer, older]);
    expect(summary.numberStats.reduce((sum, row) => sum + row.count, 0)).toBe(12);
    expect(summary.numberStats.reduce((sum, row) => sum + row.rate, 0)).toBe(6);
    expect(summary.sumDistribution).toEqual([{ sum: 21, count: 1 }, { sum: 172, count: 1 }]);
    expect(summary.parityDistribution.reduce((sum, row) => sum + row.count, 0)).toBe(2);
    expect(summary.parityDistribution.find(row => row.odd === 3)?.count).toBe(1);
    expect(summary.parityDistribution.find(row => row.odd === 4)?.count).toBe(1);
    expect(summary.rangeDistribution).toEqual([
      { label: '01–09', count: 7 }, { label: '10–19', count: 1 }, { label: '20–29', count: 0 },
      { label: '30–39', count: 3 }, { label: '40–45', count: 1 },
    ]);
    const repeated = summarize([older, draw(2, '2016-07-22', [2, 17, 3, 4, 5, 6])]);
    expect(repeated.pairStats[0]).toEqual({ pair: [2, 17], count: 2 });
    expect(repeated.pairStats).toHaveLength(20);
  });

  it('uses the explicit Beta(6,39) prior and marks bounded normal intervals as approximate', () => {
    const empty = summarize([]);
    expect(empty.totalDraws).toBe(0);
    expect(empty.firstDate).toBeNull();
    expect(empty.lastDate).toBeNull();
    expect(empty.pairStats).toEqual([]);
    expect(empty.intervalApproximation).toBe('normal-95%');
    expect(empty.numberStats).toHaveLength(45);
    for (const row of empty.numberStats) {
      expect(row.posteriorMean).toBe(6 / 45);
      expect(row).toMatchObject({ count: 0, rate: 0, gap: 0 });
      expect(row.lower).toBeGreaterThanOrEqual(0);
      expect(row.upper).toBeLessThanOrEqual(1);
      expect(row.lower).toBeLessThan(row.posteriorMean);
      expect(row.upper).toBeGreaterThan(row.posteriorMean);
    }
    const scoped = summarize([older, newer]);
    expect(scoped.numberStats.find(row => row.number === 2)?.posteriorMean).toBe(8 / 47);
    expect(scoped.numberStats.find(row => row.number === 44)?.posteriorMean).toBe(6 / 47);
  });

  it('deduplicates identical draw IDs, rejects conflicts, and does not mutate inputs', () => {
    const input = [newer, older];
    const snapshot = JSON.stringify(input);
    expect(summarize([older, older, newer]).totalDraws).toBe(2);
    expect(() => summarize([older, { ...older, n1: 1 }])).toThrow('mâu thuẫn');
    expect(() => summarize([{ ...older, n6: 46 }])).toThrow();
    expect(() => summarize([{ ...older, n6: 2 }])).toThrow();
    expect(() => summarize([{ ...older, draw_date: '2016-02-30' }])).toThrow();
    summarize(input);
    expect(JSON.stringify(input)).toBe(snapshot);
    expect(numbers(older)).toEqual([2, 17, 33, 37, 38, 45]);
  });
});

describe('reproducible, distinct tickets', () => {
  const options = { count: 100, seed: 'mega-lab-test', halfLife: 20, smoothing: 1 };

  it.each<Algorithm>(['uniform', 'frequency', 'recency'])('%s produces valid unique tickets from a stable seed', algorithm => {
    const tickets = generateTickets([older, newer], { ...options, algorithm });
    expect(tickets).toHaveLength(100);
    expect(new Set(tickets.map(ticket => ticket.join(','))).size).toBe(100);
    expect(generateTickets([newer, older], { ...options, algorithm })).toEqual(tickets);
    expect(generateTickets([older, newer], { ...options, algorithm, seed: 'different' })).not.toEqual(tickets);
    for (const ticket of tickets) {
      expect(ticket).toHaveLength(6);
      expect(new Set(ticket).size).toBe(6);
      expect(ticket).toEqual([...ticket].sort((a, b) => a - b));
      expect(ticket.every(value => Number.isInteger(value) && value >= 1 && value <= 45)).toBe(true);
    }
  });

  it('uniform sampling does not learn from the supplied results', () => {
    expect(generateTickets([older], { ...options, algorithm: 'uniform' }))
      .toEqual(generateTickets([newer], { ...options, algorithm: 'uniform' }));
    expect(generateTickets([], { ...options, algorithm: 'frequency' }))
      .toEqual(generateTickets([], { ...options, algorithm: 'uniform' }));
  });

  it('frequency and recency depend on the selected history without global state', () => {
    expect(generateTickets([older], { ...options, algorithm: 'frequency' }))
      .not.toEqual(generateTickets([newer], { ...options, algorithm: 'frequency' }));
    expect(generateTickets([older, newer], { ...options, algorithm: 'recency', halfLife: 0.1 }))
      .not.toEqual(generateTickets([older, newer], { ...options, algorithm: 'recency', halfLife: 100 }));
    expect(generateTickets([older], { ...options, algorithm: 'frequency', count: 0 })).toEqual([]);
  });

  it('rejects invalid generator options instead of emitting malformed tickets', () => {
    for (const change of [{ count: -1 }, { count: 1.2 }, { count: 1001 }, { smoothing: 0 },
      { smoothing: NaN }, { halfLife: 0 }, { halfLife: Infinity }, { seed: NaN }]) {
      expect(() => generateTickets([older], { ...options, algorithm: 'uniform', ...change })).toThrow();
    }
  });
});
