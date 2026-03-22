"use client";

import { useState } from "react";
import {
  BriefingResult,
  StaleLineAlert,
  OutlierAlert,
  ArbitrageOpportunity,
  ValuePlay,
  SportsbookRanking,
} from "@/lib/api";

/* ── Glossary Definitions ─────────────────────────────── */

const GLOSSARY: Record<string, string> = {
  "vig": "Short for vigorish (or juice). The commission a sportsbook charges on a bet. Lower vig means better value for the bettor. Typically 4-5% on standard markets.",
  "implied probability": "The probability of an outcome as suggested by the betting odds. For example, -200 odds imply a 66.7% chance of winning. Compare to fair probability to find value.",
  "z-score": "A statistical measure of how many standard deviations a value is from the median. A Z-score above 2.0 means the odds are significantly different from the market consensus.",
  "arbitrage": "A risk-free profit opportunity that exists when two sportsbooks disagree enough that you can bet both sides and guarantee a profit regardless of the outcome.",
  "stale line": "Odds that haven't been updated recently compared to other sportsbooks. Stale lines may not reflect the current market and can create false signals or exploitable opportunities.",
  "outlier": "Odds from one sportsbook that deviate significantly from the market consensus. Could indicate a pricing error, different information, or simply a slow update.",
  "edge": "The percentage advantage a bet offers over fair odds. A 3% edge means you're getting 3% better odds than the true probability suggests. Higher edge = more value.",
  "moneyline": "A bet on which team will win the game outright, with no point spread. Expressed as American odds (e.g., -150 favorite, +130 underdog).",
  "spread": "The point handicap applied to level the playing field. A -5.5 spread means the team must win by 6+ points. The odds on each side reflect the vig.",
  "total": "A bet on whether the combined score of both teams will be over or under a set number (e.g., O/U 217.5 points).",
  "combined implied": "The sum of implied probabilities from both sides of a bet. If below 100%, an arbitrage exists. The gap below 100% is your guaranteed profit margin.",
  "confidence": "How certain we are about a finding, based on sample size, statistical strength, and deviation magnitude. HIGH means act now, LOW means monitor only.",
  "composite score": "An overall quality rating combining average vig (50% weight) and data reliability — fewer issues means higher score. Scale of 0-100.",
  "MAD": "Median Absolute Deviation — a robust statistical method for detecting outliers. Unlike standard deviation, MAD isn't thrown off by extreme values, making it ideal for odds analysis.",
  "fair odds": "The true probability of an outcome after removing the sportsbook's vig. Calculated by normalizing implied probabilities across all books to sum to 100%.",
  "grade": "Letter grade (A+ to F) based on composite score. A+/A = top tier, use as primary book. C/D = use with caution. F = avoid tonight.",
};

/* ── Term Tooltip Component ───────────────────────────── */

function Term({ children, term }: { children: React.ReactNode; term?: string }) {
  const [open, setOpen] = useState(false);
  const key = (term || (typeof children === "string" ? children : "")).toLowerCase();
  const definition = GLOSSARY[key];

  if (!definition) return <>{children}</>;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        aria-expanded={open}
        aria-label={`Definition of ${key}`}
        className="border-b border-dashed border-brand/40 text-brand-dark hover:border-brand cursor-help transition-colors"
      >
        {children}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 bg-gray-900 text-white text-xs rounded-lg px-3 py-2.5 shadow-lg leading-relaxed">
            <div className="font-semibold text-brand-light mb-1 capitalize">{key}</div>
            {definition}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
          </div>
        </>
      )}
    </span>
  );
}

/* ── Main Component ───────────────────────────────────── */

export default function BriefingDisplay({ briefing }: { briefing: BriefingResult }) {
  return (
    <div className="space-y-8">
      <OverviewBar briefing={briefing} />
      <NarrativeSummary text={briefing.narrative} />

      {(briefing.stale_lines.length > 0 || briefing.outlier_odds.length > 0) && (
        <Section title="Anomaly Alerts" count={briefing.stale_lines.length + briefing.outlier_odds.length}>
          {briefing.stale_lines.map((s, i) => (
            <StaleLineCard key={`stale-${i}`} alert={s} />
          ))}
          {briefing.outlier_odds.map((o, i) => (
            <OutlierCard key={`outlier-${i}`} alert={o} />
          ))}
        </Section>
      )}

      {briefing.arbitrage.length > 0 && (
        <Section title="Arbitrage Opportunities" count={briefing.arbitrage.length}>
          {briefing.arbitrage.map((arb, i) => (
            <ArbitrageCard key={i} arb={arb} />
          ))}
        </Section>
      )}

      {briefing.value_plays.length > 0 && (
        <Section title="Best Value Plays" count={briefing.value_plays.length}>
          {briefing.value_plays.map((v, i) => (
            <ValuePlayCard key={i} play={v} />
          ))}
        </Section>
      )}

      <Section title="Sportsbook Rankings" count={briefing.sportsbook_rankings.length}>
        <RankingsTable rankings={briefing.sportsbook_rankings} />
      </Section>

      {/* Glossary hint */}
      <div className="text-[11px] text-text-muted text-center pt-2 border-t border-border">
        Click any <span className="border-b border-dashed border-brand/40 text-brand-dark">underlined term</span> for a definition
      </div>
    </div>
  );
}

/* ── Overview Bar ─────────────────────────────────────── */

function OverviewBar({ briefing }: { briefing: BriefingResult }) {
  const o = briefing.overview;
  const q = briefing.quality_metrics;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        <StatPill label="Games" value={o.total_games} />
        <StatPill label="Books" value={o.total_sportsbooks} />
        <StatPill label="Anomalies" value={o.total_anomalies} variant={o.total_anomalies > 0 ? "warn" : "default"} tooltip="anomalies" />
        <StatPill label="Stale" value={o.stale_count} variant={o.stale_count > 0 ? "warn" : "default"} tooltip="stale line" />
        <StatPill label="Outliers" value={o.outlier_count} variant={o.outlier_count > 0 ? "warn" : "default"} tooltip="outlier" />
        <StatPill label="Arbs" value={o.arbitrage_count} variant={o.arbitrage_count > 0 ? "good" : "default"} tooltip="arbitrage" />
      </div>
      {q && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
          <Term term="confidence">
            <span className="flex items-center gap-1">
              <span className={`inline-block w-2 h-2 rounded-full ${q.overall_confidence >= 0.7 ? 'bg-green-500' : q.overall_confidence >= 0.4 ? 'bg-amber-500' : 'bg-red-500'}`} />
              Confidence: {Math.round(q.overall_confidence * 100)}%
            </span>
          </Term>
          <span className="text-border">|</span>
          <span>{q.high_confidence_alerts}/{q.total_alerts} high-confidence alerts ({Math.round(q.high_confidence_pct * 100)}%)</span>
          <span className="text-border">|</span>
          <span>Generated in {briefing.duration_seconds.toFixed(1)}s</span>
          <span className="text-border">|</span>
          <span>{briefing.tools_used_count} tool calls</span>
        </div>
      )}
      {q?.data_warnings && q.data_warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
          <span className="font-semibold">Data Warnings:</span> {q.data_warnings.join(' · ')}
        </div>
      )}
    </div>
  );
}

function StatPill({ label, value, variant = "default", tooltip }: { label: string; value: number; variant?: "default" | "warn" | "good"; tooltip?: string }) {
  const colors = {
    default: "bg-surface-secondary text-text-secondary",
    warn: "bg-red-50 text-red-700",
    good: "bg-green-50 text-green-700",
  };
  const inner = (
    <div className={`rounded-xl px-3 py-2 text-center ${colors[variant]}`}>
      <div className="text-lg font-bold">{value}</div>
      <div className="text-[10px] uppercase tracking-wide opacity-70">{label}</div>
    </div>
  );
  if (tooltip) {
    return <Term term={tooltip}>{inner}</Term>;
  }
  return inner;
}

/* ── Narrative Summary ────────────────────────────────── */

function NarrativeSummary({ text }: { text: string }) {
  if (!text) return null;
  const paragraphs = text.split("\n").filter(p => p.trim());
  return (
    <div className="bg-brand-light/50 border border-brand/20 rounded-xl px-5 py-4">
      <h3 className="text-xs font-semibold text-brand-dark uppercase tracking-wide mb-2">Executive Summary</h3>
      <div className="space-y-2">
        {paragraphs.map((p, i) => (
          <p key={i} className="text-sm text-text-primary leading-relaxed">{p}</p>
        ))}
      </div>
    </div>
  );
}

/* ── Section Wrapper ──────────────────────────────────── */

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-base font-semibold text-text-primary">{title}</h2>
        <span className="text-xs bg-surface-secondary text-text-muted px-2 py-0.5 rounded-full">{count}</span>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

/* ── Badges ───────────────────────────────────────────── */

function ConfidenceBadge({ level, score }: { level: string; score?: number }) {
  const colors: Record<string, string> = {
    high: "bg-green-100 text-green-800",
    medium: "bg-amber-100 text-amber-800",
    low: "bg-gray-100 text-gray-600",
  };
  return (
    <Term term="confidence">
      <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${colors[level] || colors.low}`}>
        {level}{score !== undefined ? ` ${Math.round(score * 100)}%` : ""}
      </span>
    </Term>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: "bg-red-600 text-white",
    high: "bg-red-100 text-red-800",
    medium: "bg-amber-100 text-amber-800",
    low: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${colors[severity] || colors.medium}`}>
      {severity}
    </span>
  );
}

/* ── Stale Line Card ──────────────────────────────────── */

function StaleLineCard({ alert }: { alert: StaleLineAlert }) {
  return (
    <div className="border border-red-200 bg-red-50/50 rounded-xl px-4 py-3 card-hover">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <Term term="stale line"><span className="text-xs text-text-muted">Stale Line</span></Term>
        </div>
        <ConfidenceBadge level={alert.confidence_level} score={alert.confidence_score} />
      </div>
      <div className="text-sm font-semibold text-text-primary">
        {alert.sportsbook} — {alert.away_team} @ {alert.home_team}
      </div>
      <div className="text-xs text-text-secondary mt-1">
        {alert.hours_behind} hours behind freshest line ({Math.round(alert.minutes_behind)} minutes)
      </div>
      <div className="text-xs text-red-700 mt-1.5 font-medium">
        Action: Verify lines before betting at {alert.sportsbook} for this game
      </div>
    </div>
  );
}

/* ── Outlier Card ─────────────────────────────────────── */

function OutlierCard({ alert }: { alert: OutlierAlert }) {
  return (
    <div className="border border-amber-200 bg-amber-50/50 rounded-xl px-4 py-3 card-hover">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <Term term="outlier"><span className="text-xs text-text-muted">Outlier {alert.market}</span></Term>
        </div>
        <ConfidenceBadge level={alert.confidence_level} score={alert.confidence_score} />
      </div>
      <div className="text-sm font-semibold text-text-primary">
        {alert.sportsbook} — {alert.away_team} @ {alert.home_team}
      </div>
      <div className="text-xs text-text-secondary mt-1">
        {alert.explanation}
      </div>
      <div className="flex gap-4 mt-2 text-xs font-mono text-text-muted">
        <Term term="z-score"><span>Z-score: {alert.z_score.toFixed(1)}</span></Term>
        {alert.deviation !== null && <span>Deviation: {typeof alert.deviation === 'number' && alert.deviation < 1 ? (alert.deviation * 100).toFixed(1) + '%' : alert.deviation}</span>}
      </div>
    </div>
  );
}

/* ── Arbitrage Card ───────────────────────────────────── */

function ArbitrageCard({ arb }: { arb: ArbitrageOpportunity }) {
  return (
    <div className="border border-green-200 bg-green-50/30 rounded-xl px-4 py-4 card-hover">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Term term="arbitrage">
            <span className="text-xs font-bold text-green-800 bg-green-100 px-2 py-0.5 rounded-full uppercase">
              {arb.profit_pct.toFixed(2)}% profit
            </span>
          </Term>
          <Term term={arb.market}><span className="text-xs text-text-muted">{arb.market}</span></Term>
        </div>
        <ConfidenceBadge level={arb.confidence_level} score={arb.confidence_score} />
      </div>

      <div className="text-sm font-semibold text-text-primary mb-3">
        {arb.away_team} @ {arb.home_team}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <ArbSideCard side={arb.side_a} label="Side A" />
        <ArbSideCard side={arb.side_b} label="Side B" />
      </div>

      <div className="bg-white/80 rounded-lg px-3 py-2 text-xs space-y-1">
        <div className="flex justify-between">
          <Term term="combined implied"><span className="text-text-muted">Combined implied probability</span></Term>
          <span className="font-mono font-medium">{(arb.combined_implied * 100).toFixed(2)}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Guaranteed profit on $1,000</span>
          <span className="font-mono font-bold text-green-700">${arb.profit_on_1000.toFixed(2)}</span>
        </div>
      </div>

      <div className="mt-3 text-xs text-green-800 bg-green-100/50 rounded-lg px-3 py-2">
        <span className="font-semibold">How to execute:</span> Place ${arb.side_a.stake_on_1000.toFixed(2)} on {arb.side_a.label} at {arb.side_a.sportsbook} ({arb.side_a.odds > 0 ? '+' : ''}{arb.side_a.odds}) and ${arb.side_b.stake_on_1000.toFixed(2)} on {arb.side_b.label} at {arb.side_b.sportsbook} ({arb.side_b.odds > 0 ? '+' : ''}{arb.side_b.odds}). Guaranteed ${arb.profit_on_1000.toFixed(2)} profit regardless of outcome.
      </div>
    </div>
  );
}

function ArbSideCard({ side, label }: { side: ArbitrageOpportunity["side_a"]; label: string }) {
  return (
    <div className="bg-white rounded-lg px-3 py-2 border border-green-100">
      <div className="text-[10px] text-text-muted uppercase mb-1">{label}</div>
      <div className="text-sm font-semibold">{side.sportsbook}</div>
      <div className="text-xs text-text-secondary">{side.label}</div>
      <div className="flex justify-between mt-1.5 text-xs">
        <span className="font-mono font-bold">{side.odds > 0 ? '+' : ''}{side.odds}</span>
        <span className="text-text-muted">${side.stake_on_1000.toFixed(0)} stake</span>
      </div>
      <div className="text-[10px] text-text-muted mt-1">
        <Term term="implied probability"><span>Implied: {(side.implied_probability * 100).toFixed(1)}%</span></Term>
      </div>
    </div>
  );
}

/* ── Value Play Card ──────────────────────────────────── */

function ValuePlayCard({ play }: { play: ValuePlay }) {
  return (
    <div className="border border-purple-200 bg-purple-50/30 rounded-xl px-4 py-3 card-hover">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <Term term="edge">
            <span className="text-xs font-bold text-purple-800 bg-purple-100 px-2 py-0.5 rounded-full">
              {play.edge_pct.toFixed(1)}% edge
            </span>
          </Term>
          <ConfidenceBadge level={play.confidence} />
        </div>
        <Term term={play.market}><span className="text-xs text-text-muted">{play.market}</span></Term>
      </div>
      <div className="text-sm font-semibold text-text-primary">
        {play.away_team} @ {play.home_team}
      </div>
      <div className="flex gap-4 mt-2 text-xs">
        <span><span className="text-text-muted">Book:</span> <span className="font-medium">{play.sportsbook}</span></span>
        <span><span className="text-text-muted">Odds:</span> <span className="font-mono font-medium">{play.odds > 0 ? '+' : ''}{play.odds}</span></span>
        <span><span className="text-text-muted">Payout/$100:</span> <span className="font-mono">${play.payout_on_100.toFixed(0)}</span></span>
      </div>
    </div>
  );
}

/* ── Sportsbook Rankings Table ────────────────────────── */

function RankingsTable({ rankings }: { rankings: SportsbookRanking[] }) {
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-surface-secondary text-text-muted">
            <th className="text-left px-3 py-2 font-medium">#</th>
            <th className="text-left px-3 py-2 font-medium">Sportsbook</th>
            <th className="text-center px-3 py-2 font-medium"><Term term="grade">Grade</Term></th>
            <th className="text-center px-3 py-2 font-medium"><Term term="composite score">Score</Term></th>
            <th className="text-center px-3 py-2 font-medium"><Term term="vig">Avg Vig</Term></th>
            <th className="text-center px-3 py-2 font-medium">Issues</th>
            <th className="text-left px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rankings.map((r) => (
            <RankingRow key={r.sportsbook} ranking={r} isTop={r.rank <= 3} isBottom={r.rank === rankings.length} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RankingRow({ ranking: r, isTop, isBottom }: { ranking: SportsbookRanking; isTop: boolean; isBottom: boolean }) {
  const gradeColors: Record<string, string> = {
    "A+": "bg-green-100 text-green-800",
    "A": "bg-green-100 text-green-800",
    "B+": "bg-blue-100 text-blue-800",
    "B": "bg-blue-100 text-blue-800",
    "C": "bg-amber-100 text-amber-800",
    "D": "bg-orange-100 text-orange-800",
    "F": "bg-red-100 text-red-800",
  };

  const issues = r.stale_flags + r.outlier_flags;
  const issueText = issues === 0
    ? "Clean"
    : [
        r.stale_flags > 0 ? `${r.stale_flags} stale` : "",
        r.outlier_flags > 0 ? `${r.outlier_flags} outlier` : "",
      ].filter(Boolean).join(", ");

  return (
    <tr className={`border-t border-border ${isTop ? "bg-green-50/30" : isBottom ? "bg-red-50/30" : ""}`}>
      <td className="px-3 py-2.5 font-medium text-text-primary">{r.rank}</td>
      <td className="px-3 py-2.5 font-semibold text-text-primary">{r.sportsbook}</td>
      <td className="px-3 py-2.5 text-center">
        <span className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${gradeColors[r.grade] || "bg-gray-100 text-gray-700"}`}>
          {r.grade}
        </span>
      </td>
      <td className="px-3 py-2.5 text-center font-mono">{r.composite_score.toFixed(1)}</td>
      <td className="px-3 py-2.5 text-center font-mono">{r.avg_vig_pct.toFixed(2)}%</td>
      <td className="px-3 py-2.5 text-center">
        {issues === 0 ? (
          <span className="text-green-600 font-medium">0</span>
        ) : (
          <span className="text-red-600 font-medium">{issues}</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        {issues === 0 ? (
          <span className="text-green-700 text-[11px]">{issueText}</span>
        ) : (
          <span className="text-red-600 text-[11px]">{issueText}</span>
        )}
      </td>
    </tr>
  );
}
