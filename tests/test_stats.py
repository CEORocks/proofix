from proofix.stats import summarize_pairs


def test_paired_summary_is_deterministic_and_reports_lift():
    baseline = [False, False, True, False, True]
    proofix = [True, True, True, False, True]
    first = summarize_pairs(baseline, proofix, bootstrap_samples=500, seed=7)
    second = summarize_pairs(baseline, proofix, bootstrap_samples=500, seed=7)
    assert first == second
    assert first.lift_percentage_points == 40.0
    assert first.discordant_proofix_wins == 2
    assert first.discordant_baseline_wins == 0
