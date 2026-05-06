from __future__ import annotations

from policy_lab.domain import StudyContext
from policy_lab.engine.optimizer import PolicyOptimizer
from policy_lab.engine.policy_executor import PolicyExecutor
from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator
from policy_lab.storage.created_rule_repository import CreatedRuleRepository
from policy_lab.storage.feature_repository import FeatureRepository
from policy_lab.storage.manual_config_repository import ManualConfigRepository
from policy_lab.storage.result_repository import ResultRepository
from policy_lab.storage.scenario_repository import ScenarioRepository
from policy_lab.storage.studies_repository import StudyRepository

study_repository = StudyRepository()
feature_repository = FeatureRepository()
created_rule_repository = CreatedRuleRepository()
manual_config_repository = ManualConfigRepository()
scenario_repository = ScenarioRepository()
result_repository = ResultRepository()
orchestrator = ScenarioOrchestrator(
    study_repository=study_repository,
    feature_repository=feature_repository,
    scenario_repository=scenario_repository,
    result_repository=result_repository,
)
policy_executor = PolicyExecutor()
policy_optimizer = PolicyOptimizer()


def load_studies() -> list[StudyContext]:
    return study_repository.list_studies()


def default_study_id() -> str | None:
    studies = load_studies()
    return studies[0].study_id if studies else None


def load_study(study_id: str) -> StudyContext:
    return study_repository.load(study_id)
