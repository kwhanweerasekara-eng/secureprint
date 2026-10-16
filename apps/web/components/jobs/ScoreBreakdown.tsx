import { categoryLabel } from "@/lib/utils";
import type { JobDetail } from "@/types";

// One colour per category position, readable in both themes.
const COLOURS = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"];

function metadata(job: JobDetail, eventType: string): Record<string, unknown> {
  return job.events.find((e) => e.event_type === eventType)?.event_metadata ?? {};
}

/**
 * "Why this score?": the points each kind of sensitive data added, the total,
 * and, when a category floor raised the level, which data did it. Values are
 * never shown, only categories and counts.
 */
export function ScoreBreakdown({ job }: { job: JobDetail }) {
  const scored = metadata(job, "RISK_SCORED");
  const classified = metadata(job, "CLASSIFIED");
  const contributions = (scored.contributions ?? null) as Record<string, number> | null;

  if (job.risk_score === null) {
    return <p className="text-sm text-muted-foreground">This job has not been scored yet.</p>;
  }
  if (!contributions) {
    return (
      <p className="text-sm text-muted-foreground">
        This job was scored before SecurePrint kept score breakdowns. Jobs printed from now on show one here.
      </p>
    );
  }

  const counts = Object.fromEntries(job.detections.map((d) => [d.category, d.count]));
  const rows = Object.entries(contributions)
    .map(([category, points], i) => ({ category, points, count: counts[category] ?? 0, colour: COLOURS[i % COLOURS.length] }))
    .sort((a, b) => b.points - a.points);
  const uncapped = typeof scored.uncapped_score === "number" ? scored.uncapped_score : rows.reduce((s, r) => s + r.points, 0);
  const scale = Math.max(100, uncapped);
  const scoreLevel = typeof classified.score_classification === "string" ? classified.score_classification : null;
  const raisedBy = Array.isArray(classified.raised_by) ? (classified.raised_by as string[]) : [];

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No sensitive data was found, so the score is 0.</p>;
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex h-4 w-full overflow-hidden rounded-full bg-muted">
          {rows.map((r) =>
            r.points > 0 ? (
              <div
                key={r.category}
                title={`${categoryLabel(r.category)}: +${r.points}`}
                style={{ width: `${(r.points / scale) * 100}%`, backgroundColor: r.colour }}
              />
            ) : null
          )}
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-muted-foreground tabular-nums">
          <span>0</span>
          <span>{scale}</span>
        </div>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="pb-2 font-normal">Sensitive data found</th>
            <th className="pb-2 text-right font-normal">Times found</th>
            <th className="pb-2 text-right font-normal">Points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.category} className="border-t">
              <td className="py-1.5">
                <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ backgroundColor: r.colour }} />
                {categoryLabel(r.category)}
              </td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground">{r.count}</td>
              <td className="py-1.5 text-right font-semibold tabular-nums">+{r.points}</td>
            </tr>
          ))}
          <tr className="border-t-2">
            <td className="pt-2 font-medium" colSpan={2}>
              Risk score{uncapped > 100 ? ` (${uncapped} points, capped at 100)` : ""}
            </td>
            <td className="pt-2 text-right font-semibold tabular-nums">{job.risk_score}</td>
          </tr>
        </tbody>
      </table>

      <p className="text-sm text-muted-foreground">
        Each kind of data counts once, however many times it appears.
        {scoreLevel && (
          <>
            {" "}A score of {job.risk_score} places the document in <span className="font-medium text-foreground">{scoreLevel}</span>.
          </>
        )}
        {raisedBy.length > 0 && job.classification && (
          <>
            {" "}It was raised to <span className="font-medium text-foreground">{job.classification}</span> because{" "}
            {raisedBy.map(categoryLabel).join(" and ")} on its own always requires that level.
          </>
        )}
      </p>
    </div>
  );
}
