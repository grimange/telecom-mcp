# Trend and Comparison Model

## Comparison Views
- PBX vs PBX: `telecom.scorecard_compare(entity_type=pbx, ...)`
- cluster vs cluster: `telecom.scorecard_compare(entity_type=cluster, ...)`
- environment vs environment: `telecom.scorecard_compare(entity_type=environment, ...)`

## Trend View
- `telecom.scorecard_trend(entity_type, entity_id, window)`
- outputs:
  - absolute score change
  - current/previous confidence
  - top new risks
  - top recovered areas

## Freshness Behavior
- current implementation uses local in-process score history
- if no prior score exists, trend initializes from first generated scorecard
- stale/missing evidence lowers confidence via missing evidence reasons
