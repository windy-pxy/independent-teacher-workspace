from teacher_workspace.performance_smoke import percentile
from teacher_workspace.security_check import check_repository, repository_root


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([4, 1, 3, 2], 0.5) == 2
    assert percentile([4, 1, 3, 2], 0.95) == 4


def test_repository_security_rules_pass() -> None:
    result = check_repository(repository_root())
    assert result["status"] == "ok"
    assert result["pinned_actions"] >= 1
