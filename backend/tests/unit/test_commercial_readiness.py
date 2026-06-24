from __future__ import annotations

from app.services.commercial_readiness import build_onboarding_steps


def test_build_onboarding_steps_exposes_required_actions_and_auto_fix_hints():
    steps = build_onboarding_steps(
        completed=set(),
        system_hints={
            "branding": False,
            "license": False,
            "auth": False,
            "notification": True,
            "first_instance": False,
            "governance": False,
            "acceptance": False,
        },
    )
    by_key = {step["key"]: step for step in steps}

    assert by_key["notification"]["completed"] is True
    assert by_key["notification"]["status"] == "done"
    assert by_key["first_instance"]["required"] is True
    assert by_key["first_instance"]["status"] == "blocked"
    assert by_key["first_instance"]["quick_action"] == "navigate"
    assert by_key["governance"]["can_auto_fix"] is True
    assert by_key["governance"]["quick_action"] == "trial_bootstrap"
    assert by_key["acceptance"]["quick_action"] == "generate_acceptance"
