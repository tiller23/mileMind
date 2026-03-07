"""Report generation for evaluation harness results.

Produces markdown reports for:
1. Single-run results (all 5 plans for human review)
2. Sonnet-vs-Opus comparison (side-by-side metrics)
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.evaluation.personas import get_persona
from src.evaluation.results import HarnessMetrics, PersonaResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_summary_table(metrics: HarnessMetrics) -> list[str]:
    """Build the summary metrics table rows.

    Args:
        metrics: Aggregate harness metrics.

    Returns:
        List of markdown lines for the summary table.
    """
    if metrics.total_personas == 0:
        return [
            "## Summary",
            "",
            "*(No personas were evaluated)*",
            "",
        ]

    return [
        "## Summary",
        "",
        "| Metric | Value | Target |",
        "|--------|-------|--------|",
        f"| Personas evaluated | {metrics.total_personas} | 5 |",
        f"| Plans approved | {metrics.total_approved}/{metrics.total_personas} | 5/5 |",
        f"| Constraint violation rate | {metrics.violation_rate:.1%} | < 5% |",
        f"| Avg retries to convergence | {metrics.avg_retry_count:.1f} | < 3 |",
        f"| Avg safety score | {metrics.avg_safety_score:.1f} | > 85 |",
        f"| Min safety score | {metrics.min_safety_score:.0f} | > 75 |",
        f"| Avg overall score | {metrics.avg_overall_score:.1f} | > 85 |",
        f"| Avg tokens/persona | {metrics.avg_tokens:,.0f} | — |",
        f"| Avg cost/persona | ${metrics.avg_cost_usd:.4f} | — |",
        f"| Total cost | ${metrics.total_cost_usd:.4f} | — |",
        f"| Total time | {metrics.total_elapsed_seconds:.1f}s | — |",
        f"| Total constraint violations | {metrics.total_with_violations} | 0 |",
        "",
    ]


def _format_persona_section(r: PersonaResult) -> list[str]:
    """Build the per-persona detail section.

    Args:
        r: A single persona's result.

    Returns:
        List of markdown lines for this persona's section.
    """
    lines: list[str] = []
    lines.append(f"## Persona: {r.persona_id}")
    lines.append("")

    # Athlete profile summary
    try:
        persona = get_persona(r.persona_id)
        profile = persona.profile
        lines.append("### Athlete Profile")
        lines.append("")
        lines.append(f"- **Name:** {profile.name}")
        lines.append(f"- **VDOT:** {profile.vdot}")
        lines.append(f"- **Goal:** {profile.goal_distance}")
        lines.append(f"- **Weekly base:** {profile.weekly_mileage_base} km/week")
        lines.append(f"- **Risk tolerance:** {profile.risk_tolerance.value}")
        if profile.injury_history:
            lines.append(f"- **Injury history:** {profile.injury_history}")
        lines.append("")
    except KeyError:
        pass

    # Expected behavior
    try:
        persona = get_persona(r.persona_id)
        lines.append("### Expected Behavior")
        lines.append("")
        lines.append(f"> {persona.expected_behavior.description}")
        lines.append("")
        if persona.expected_behavior.must_include:
            lines.append(f"**Must include:** {', '.join(persona.expected_behavior.must_include)}")
        if persona.expected_behavior.must_not_include:
            lines.append(f"**Must NOT include:** {', '.join(persona.expected_behavior.must_not_include)}")
        if persona.expected_behavior.notes:
            lines.append(f"**Notes:** {persona.expected_behavior.notes}")
        lines.append("")
    except KeyError:
        lines.append("### Expected Behavior")
        lines.append("")
        lines.append("*(Persona definition not found)*")
        lines.append("")

    # Result metadata
    lines.append("### Result")
    lines.append("")
    status = "APPROVED" if r.approved else "REJECTED"
    lines.append(f"- **Status:** {status}")
    lines.append(f"- **Retries:** {r.retry_count}")
    if r.final_scores:
        lines.append(
            f"- **Scores:** safety={r.final_scores.safety}, "
            f"progression={r.final_scores.progression}, "
            f"specificity={r.final_scores.specificity}, "
            f"feasibility={r.final_scores.feasibility} "
            f"(overall={r.final_scores.overall:.1f})"
        )
    else:
        lines.append("- **Scores:** *(not available)*")
    if r.warning:
        lines.append(f"- **Warning:** {r.warning}")
    if r.error:
        lines.append(f"- **Error:** {r.error}")
    if r.constraint_violations:
        lines.append(f"- **Violations:** {'; '.join(r.constraint_violations)}")
    lines.append("")

    # Token usage breakdown
    planner_total = r.planner_input_tokens + r.planner_output_tokens
    reviewer_total = r.reviewer_input_tokens + r.reviewer_output_tokens
    lines.append("### Token Usage")
    lines.append("")
    lines.append(
        f"- **Planner tokens:** {planner_total:,} "
        f"(in={r.planner_input_tokens:,}, out={r.planner_output_tokens:,})"
    )
    lines.append(
        f"- **Reviewer tokens:** {reviewer_total:,} "
        f"(in={r.reviewer_input_tokens:,}, out={r.reviewer_output_tokens:,})"
    )
    lines.append(f"- **Total tokens:** {r.total_tokens:,}")
    lines.append(f"- **Estimated cost:** ${r.estimated_cost_usd:.4f}")
    lines.append("")

    # The actual plan (fenced to prevent markdown collision)
    lines.append("### Generated Plan")
    lines.append("")
    if r.plan_text:
        lines.append("<details>")
        lines.append("<summary>Click to expand plan</summary>")
        lines.append("")
        lines.append("```")
        lines.append(r.plan_text)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("*(No plan generated)*")
    lines.append("")

    # Decision log
    if r.decision_log:
        lines.append("### Decision Log")
        lines.append("")
        for entry in r.decision_log:
            lines.append(
                f"- **Iteration {entry.iteration}:** {entry.outcome.value}"
            )
            if entry.scores:
                lines.append(
                    f"  - Scores: safety={entry.scores.safety}, "
                    f"progression={entry.scores.progression}, "
                    f"specificity={entry.scores.specificity}, "
                    f"feasibility={entry.scores.feasibility}"
                )
            if entry.critique:
                critique_preview = entry.critique[:200]
                if len(entry.critique) > 200:
                    critique_preview += "..."
                lines.append(f"  - Critique: {critique_preview}")
            if entry.issues:
                for issue in entry.issues[:5]:
                    lines.append(f"  - Issue: {issue}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def _format_comparison_persona(
    pid: str,
    comparison_results: dict[str, list[PersonaResult]],
) -> list[str]:
    """Build a per-persona comparison table.

    Args:
        pid: Persona ID to compare.
        comparison_results: Full comparison results dict.

    Returns:
        List of markdown lines for this persona's comparison.
    """
    lines: list[str] = []
    lines.append(f"### {pid}")
    lines.append("")
    header = "| Metric |"
    separator = "|--------|"
    for model in comparison_results:
        short_name = model.split("-")[1] if "-" in model else model
        header += f" {short_name} |"
        separator += "--------|"
    lines.append(header)
    lines.append(separator)

    # Find this persona's result for each model
    persona_results: dict[str, PersonaResult | None] = {}
    for model, results in comparison_results.items():
        match = next((r for r in results if r.persona_id == pid), None)
        persona_results[model] = match

    rows = [
        ("Approved", lambda r: "Yes" if r and r.approved else "**No**"),
        ("Safety", lambda r: str(r.final_scores.safety) if r and r.final_scores else "—"),
        ("Overall", lambda r: f"{r.final_scores.overall:.1f}" if r and r.final_scores else "—"),
        ("Retries", lambda r: str(r.retry_count) if r else "—"),
        ("Violations", lambda r: str(len(r.constraint_violations)) if r else "—"),
        ("Tokens", lambda r: f"{r.total_tokens:,}" if r else "—"),
        ("Cost", lambda r: f"${r.estimated_cost_usd:.4f}" if r else "—"),
        ("Time", lambda r: f"{r.elapsed_seconds:.1f}s" if r else "—"),
    ]

    for label, fmt in rows:
        row = f"| {label} |"
        for model in comparison_results:
            row += f" {fmt(persona_results[model])} |"
        lines.append(row)
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_plan_review_report(
    results: list[PersonaResult],
    metrics: HarnessMetrics,
) -> str:
    """Generate a markdown report with all plans for human review.

    This is the primary artifact for manual review. Each persona gets
    a section with the full plan text, scores, and expected behavior
    for comparison.

    Args:
        results: List of PersonaResult from the harness run.
        metrics: Aggregate metrics for the run.

    Returns:
        Complete markdown report string.
    """
    lines: list[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# MileMind Evaluation Harness — Plan Review Report")
    lines.append("")
    lines.append(f"**Generated:** {timestamp}")
    lines.append(f"**Planner:** {metrics.planner_model or '(default)'}")
    lines.append(f"**Reviewer:** {metrics.reviewer_model or '(default)'}")
    lines.append("")

    lines.extend(_format_summary_table(metrics))

    if not results:
        lines.append("*(No results to display)*")
        lines.append("")
        return "\n".join(lines)

    # Per-persona results table
    lines.append("## Per-Persona Results")
    lines.append("")
    lines.append("| Persona | Approved | Safety | Overall | Retries | Tokens | Cost | Time |")
    lines.append("|---------|----------|--------|---------|---------|--------|------|------|")
    for r in results:
        safety = f"{r.final_scores.safety}" if r.final_scores else "—"
        overall = f"{r.final_scores.overall:.1f}" if r.final_scores else "—"
        status = "Yes" if r.approved else "**No**"
        lines.append(
            f"| {r.persona_id} | {status} | {safety} | {overall} "
            f"| {r.retry_count} | {r.total_tokens:,} | ${r.estimated_cost_usd:.4f} "
            f"| {r.elapsed_seconds:.1f}s |"
        )
    lines.append("")

    # Individual plan sections
    lines.append("---")
    lines.append("")

    for r in results:
        lines.extend(_format_persona_section(r))

    # Review instructions
    lines.append("## Review Instructions")
    lines.append("")
    lines.append("For each persona above, evaluate:")
    lines.append("")
    lines.append("1. Does the plan match the **Expected Behavior** description?")
    lines.append("2. Are the **must include** items present in the plan?")
    lines.append("3. Are the **must NOT include** items absent from the plan?")
    lines.append("4. Is the plan physiologically reasonable for this athlete?")
    lines.append("5. Would you trust this plan for a real athlete?")
    lines.append("")
    lines.append("Note any prompt tuning suggestions as comments for the next iteration.")

    return "\n".join(lines)


def generate_comparison_report(
    comparison_results: dict[str, list[PersonaResult]],
) -> str:
    """Generate a markdown report comparing reviewer models side-by-side.

    This is the key artifact for the Sonnet-vs-Opus decision.

    Args:
        comparison_results: Dict mapping reviewer model ID to PersonaResult list.

    Returns:
        Complete markdown comparison report.
    """
    lines: list[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# MileMind Evaluation Harness — Reviewer Model Comparison")
    lines.append("")
    lines.append(f"**Generated:** {timestamp}")
    lines.append("")

    # Compute metrics for each model
    model_metrics: dict[str, HarnessMetrics] = {}
    for model, results in comparison_results.items():
        model_metrics[model] = HarnessMetrics.from_results(
            results, reviewer_model=model,
        )

    # Summary comparison table
    lines.append("## Summary Comparison")
    lines.append("")
    header = "| Metric |"
    separator = "|--------|"
    for model in comparison_results:
        short_name = model.split("-")[1] if "-" in model else model
        header += f" {short_name} |"
        separator += "--------|"
    lines.append(header)
    lines.append(separator)

    metrics_rows = [
        ("Approved", lambda m: f"{m.total_approved}/{m.total_personas}"),
        ("Violation rate", lambda m: f"{m.violation_rate:.1%}"),
        ("Avg retries", lambda m: f"{m.avg_retry_count:.1f}"),
        ("Avg safety score", lambda m: f"{m.avg_safety_score:.1f}"),
        ("Avg overall score", lambda m: f"{m.avg_overall_score:.1f}"),
        ("Avg tokens", lambda m: f"{m.avg_tokens:,.0f}"),
        ("Avg cost/persona", lambda m: f"${m.avg_cost_usd:.4f}"),
        ("Total cost", lambda m: f"${m.total_cost_usd:.4f}"),
        ("Avg time", lambda m: f"{m.avg_elapsed_seconds:.1f}s"),
        ("Max time", lambda m: f"{m.max_elapsed_seconds:.1f}s"),
    ]

    for label, fmt in metrics_rows:
        row = f"| {label} |"
        for model in comparison_results:
            row += f" {fmt(model_metrics[model])} |"
        lines.append(row)
    lines.append("")

    # Per-persona comparison
    lines.append("## Per-Persona Comparison")
    lines.append("")

    # Gather all persona IDs
    all_persona_ids: list[str] = []
    for results in comparison_results.values():
        for r in results:
            if r.persona_id not in all_persona_ids:
                all_persona_ids.append(r.persona_id)

    for pid in all_persona_ids:
        lines.extend(_format_comparison_persona(pid, comparison_results))

    # Decision guidance with computed deltas
    lines.append("## Decision Guidance")
    lines.append("")

    model_names = list(comparison_results.keys())
    if len(model_names) == 2:
        m_a = model_metrics[model_names[0]]
        m_b = model_metrics[model_names[1]]
        name_a = model_names[0].split("-")[1] if "-" in model_names[0] else model_names[0]
        name_b = model_names[1].split("-")[1] if "-" in model_names[1] else model_names[1]

        safety_delta = abs(m_a.avg_safety_score - m_b.avg_safety_score)
        approval_match = m_a.total_approved == m_b.total_approved
        cost_delta_pct = (
            (1.0 - min(m_a.total_cost_usd, m_b.total_cost_usd) /
             max(m_a.total_cost_usd, m_b.total_cost_usd)) * 100
            if max(m_a.total_cost_usd, m_b.total_cost_usd) > 0 else 0.0
        )
        cheaper = name_a if m_a.total_cost_usd < m_b.total_cost_usd else name_b

        lines.append("### Computed Deltas")
        lines.append("")
        lines.append(f"- Approval rate match: {'Yes' if approval_match else 'No'} "
                      f"({name_a}={m_a.total_approved}/{m_a.total_personas}, "
                      f"{name_b}={m_b.total_approved}/{m_b.total_personas})")
        lines.append(f"- Safety score delta: {safety_delta:.1f} points "
                      f"({name_a}={m_a.avg_safety_score:.1f}, "
                      f"{name_b}={m_b.avg_safety_score:.1f})")
        lines.append(f"- Cost savings: {cost_delta_pct:.0f}% ({cheaper} is cheaper)")
        lines.append("")

    lines.append("Switch reviewer from Opus to Sonnet if:")
    lines.append("")
    lines.append("1. Sonnet approval rate matches Opus (same plans approved/rejected)")
    lines.append("2. Sonnet safety scores are within 5 points of Opus")
    lines.append("3. Sonnet catches the same constraint violations")
    lines.append("4. Cost savings are meaningful (expected: ~60% reduction)")
    lines.append("")
    lines.append("If Sonnet misses safety issues that Opus catches, keep Opus as reviewer.")

    return "\n".join(lines)
