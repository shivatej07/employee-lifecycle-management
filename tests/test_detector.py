from collections import Counter
from onboarding_sim.detection.core import detect
from onboarding_sim.config import EXPORTS

def test_six_anomaly_categories_are_detected_in_full_dataset():
    found=Counter(x['issue_type'] for x in detect(EXPORTS/'dataset.db'))
    expected={
      'ACCESS_BEFORE_START_OR_APPROVAL':20,
      'DUPLICATE_ASSET_ASSIGNMENT':20,
      'TERMINATED_EMPLOYEE_RETAINS_GRANT':20,
      'TASK_DEPENDENCY_CYCLE':40,
      'RECOVERED_ASSET_REMAINS_ASSIGNED':20,
      'OVERRIDE_WITHOUT_AUDIT':20,
    }
    assert found==Counter(expected)
