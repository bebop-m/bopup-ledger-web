import { state, DEFAULT_QUOTES, invalidateComputeCache, getComputeCache, setComputeCache } from './state.js';
import {
  safeNumber, inferQuoteFromMap, resolveQuoteCurrency, resolveFxRate,
  parsePercentOverride, resolveManualDividendPerShareOverride,
  normalizeDividendSource, normalizeDividendStatus
} from './utils.js';
import { COMPANY_COLORS, BUCKET_COLORS, LABELS } from './constants.js';

export function inferQuote(symbol) {
  return inferQuoteFromMap(symbol, state.quotes, DEFAULT_QUOTES);
}

export function computeHoldings() {
  const cached = getComputeCache();
  if (cached) return cached;

  const holdings = state.holdings.map((holding) => {
    const quote = inferQuote(holding.symbol);
    const quantity = Math.max(0, safeNumber(holding.quantity, 0));
    const price = safeNumber(quote.price, 0);
    const currency = resolveQuoteCurrency(quote, holding.symbol);
    const fxRate = resolveFxRate(currency, state.rates);
    const taxOverridePercent = parsePercentOverride(holding.taxRateOverride);
    const dividendPerShareOverride = resolveManualDividendPerShareOverride(
      holding.dividendPerShareTtmOverride, holding.dividendPerShareTtmOverrideTouched === true
    );
    const effectiveTax = taxOverridePercent === null ? 0 : taxOverridePercent / 100;
    const baseDps = Math.max(0, safeNumber(quote.dividendPerShareTtm, 0));
    const effectiveDps = dividendPerShareOverride === null ? baseDps : dividendPerShareOverride;
    const currentYield = price > 0 ? effectiveDps / price : 0;
    const marketValueCny = price * quantity * fxRate;
    const grossDividendCny = effectiveDps * quantity * fxRate;
    const netAnnualDividendCny = grossDividendCny * (1 - effectiveTax);
    const dividendSource = dividendPerShareOverride === null
      ? normalizeDividendSource(quote.dividendSource, 'cache') : 'manual';
    const dividendStatus = dividendPerShareOverride === null
      ? normalizeDividendStatus(quote.dividendStatus, effectiveDps > 0 ? (dividendSource === 'cache' ? 'stale' : 'fresh') : 'missing')
      : 'manual';
    const previousClose = safeNumber(quote.previousClose, 0);
    const dailyPnlCny = previousClose > 0 ? (price - previousClose) * quantity * fxRate : 0;
    return {
      ...holding, ...quote, currency, quantity, fxRate, dividendSource, dividendStatus,
      effectiveDividendPerShareTtm: effectiveDps, currentYield, effectiveYield: currentYield,
      marketValueCny, grossAnnualDividendCny: grossDividendCny, netAnnualDividendCny,
      annualDividendCny: netAnnualDividendCny, dailyPnlCny
    };
  });

  holdings.sort((a, b) => {
    const av = safeNumber(a[state.sortField], 0);
    const bv = safeNumber(b[state.sortField], 0);
    if (av === bv) return safeNumber(b.marketValueCny, 0) - safeNumber(a.marketValueCny, 0);
    return state.sortDirection === 'asc' ? av - bv : bv - av;
  });

  const totalMarketValueCny = holdings.reduce((s, i) => s + safeNumber(i.marketValueCny, 0), 0);
  const totalDividendCny = holdings.reduce((s, i) => s + safeNumber(i.netAnnualDividendCny, 0), 0);
  const totalDailyPnlCny = holdings.reduce((s, i) => s + safeNumber(i.dailyPnlCny, 0), 0);
  const divisor = totalMarketValueCny || 1;
  const result = {
    holdings: holdings.map((i) => ({ ...i, holdingWeight: safeNumber(i.marketValueCny, 0) / divisor })),
    totalMarketValueCny, totalDividendCny, totalDailyPnlCny,
    netMarketValueCny: totalMarketValueCny - state.liabilityCny
  };
  setComputeCache(result);
  return result;
}

export function getCompanySegments(holdings) {
  return holdings.filter((i) => safeNumber(i.marketValueCny, 0) > 0)
    .sort((a, b) => safeNumber(b.marketValueCny, 0) - safeNumber(a.marketValueCny, 0))
    .map((item, index) => ({
      key: String(item.localId), label: item.name,
      value: safeNumber(item.marketValueCny, 0),
      color: COMPANY_COLORS[index % COMPANY_COLORS.length]
    }));
}

export function getBucketSegments(holdings) {
  const totals = { core: 0, income: 0 };
  holdings.forEach((i) => { totals[i.bucket] += safeNumber(i.marketValueCny, 0); });
  const sum = totals.core + totals.income || 1;
  return [
    { key: 'core', label: LABELS.core, value: totals.core, percent: totals.core / sum, color: BUCKET_COLORS.core },
    { key: 'income', label: LABELS.income, value: totals.income, percent: totals.income / sum, color: BUCKET_COLORS.income }
  ].filter((i) => i.value > 0);
}

export function getBucketSummaryItems(holdings) {
  const groups = {
    core: { key: 'core', label: LABELS.core, color: BUCKET_COLORS.core, marketValueCny: 0, totalDividendCny: 0 },
    income: { key: 'income', label: LABELS.income, color: BUCKET_COLORS.income, marketValueCny: 0, totalDividendCny: 0 }
  };
  holdings.forEach((i) => {
    const k = i.bucket === 'income' ? 'income' : 'core';
    groups[k].marketValueCny += safeNumber(i.marketValueCny, 0);
    groups[k].totalDividendCny += safeNumber(i.netAnnualDividendCny, 0);
  });
  return Object.values(groups)
    .map((i) => ({ ...i, averageYield: i.marketValueCny > 0 ? i.totalDividendCny / i.marketValueCny : 0 }))
    .filter((i) => i.marketValueCny > 0);
}
