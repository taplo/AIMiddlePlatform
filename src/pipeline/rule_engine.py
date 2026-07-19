import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    label: str
    track_id: str | None = None

    def centroid(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2,
                (self.bbox[1] + self.bbox[3]) / 2)


@dataclass
class RuleEvaluationResult:
    triggered: bool
    rule_id: int
    binding_id: int
    camera_id: str
    rule_type: str
    matches: list[dict]
    details: dict


class CameraRuleState:

    @dataclass
    class TrackedObject:
        track_id: str
        enter_time: float
        last_seen: float
        positions: list[tuple]

    def __init__(self) -> None:
        self._state: dict[str, dict[int, dict[str, CameraRuleState.TrackedObject]]] = {}

    def get_or_create(self, camera_id: str, binding_id: int) -> dict[str, "CameraRuleState.TrackedObject"]:
        if camera_id not in self._state:
            self._state[camera_id] = {}
        if binding_id not in self._state[camera_id]:
            self._state[camera_id][binding_id] = {}
        return self._state[camera_id][binding_id]

    def cleanup(self, max_age_seconds: float = 60) -> None:
        now = time.time()
        for camera_id in list(self._state.keys()):
            for binding_id in list(self._state[camera_id].keys()):
                tracks = self._state[camera_id][binding_id]
                stale = [tid for tid, obj in tracks.items()
                         if now - obj.last_seen > max_age_seconds]
                for tid in stale:
                    del tracks[tid]


class RuleEngine:

    def point_in_polygon(self, point: tuple[float, float], polygon: list[list[float]]) -> bool:
        x, y = point
        inside = False
        n = len(polygon)
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def _resolve_config(self, rule: Any, binding: Any) -> dict:
        raw = rule.config
        if isinstance(raw, str):
            config = json.loads(raw)
        else:
            config = raw
        if binding.config_overrides:
            config = {**config, **binding.config_overrides}
        return config

    def evaluate(self, rule: Any, binding: Any, camera_id: str,
                 detections: list[Detection], state: CameraRuleState) -> RuleEvaluationResult | None:
        rule_type = rule.rule_type
        config = self._resolve_config(rule, binding)

        if rule_type == "region_intrusion":
            return self._eval_region_intrusion(rule, binding, camera_id, detections, state, config)
        if rule_type == "loitering":
            return self._eval_loitering(rule, binding, camera_id, detections, state, config)
        if rule_type == "count_threshold":
            return self._eval_count_threshold(rule, binding, camera_id, detections, state, config)
        return None

    def _eval_region_intrusion(self, rule: Any, binding: Any, camera_id: str,
                               detections: list[Detection], state: CameraRuleState,
                               config: dict) -> RuleEvaluationResult | None:
        polygon = config["polygon"]
        alert_on = config.get("alert_on", "enter")
        tracks = state.get_or_create(camera_id, binding.id)
        matches: list[dict] = []

        for det in detections:
            if det.track_id is None:
                continue
            pt = det.centroid()
            inside = self.point_in_polygon(pt, polygon)
            prev = tracks.get(det.track_id)
            prev_inside = prev is not None

            if inside and not prev_inside:
                if alert_on in ("enter", "both"):
                    matches.append({"track_id": det.track_id, "action": "enter", "label": det.label})
                tracks[det.track_id] = CameraRuleState.TrackedObject(
                    track_id=det.track_id, enter_time=time.time(), last_seen=time.time(),
                    positions=[pt],
                )
            elif inside and prev_inside:
                prev.last_seen = time.time()
                prev.positions.append(pt)
            elif not inside and prev_inside:
                if alert_on in ("exit", "both"):
                    matches.append({"track_id": det.track_id, "action": "exit", "label": det.label})
                del tracks[det.track_id]

        if matches:
            return RuleEvaluationResult(
                triggered=True, rule_id=rule.id, binding_id=binding.id,
                camera_id=camera_id, rule_type="region_intrusion",
                matches=matches, details={"polygon": polygon, "alert_on": alert_on},
            )
        return None

    def _eval_loitering(self, rule: Any, binding: Any, camera_id: str,
                        detections: list[Detection], state: CameraRuleState,
                        config: dict) -> RuleEvaluationResult | None:
        polygon = config["polygon"]
        duration_seconds = config.get("duration_seconds", 10)
        tracks = state.get_or_create(camera_id, binding.id)
        now = time.time()
        matches: list[dict] = []
        current_ids: set[str] = set()

        for det in detections:
            if det.track_id is None:
                continue
            pt = det.centroid()
            inside = self.point_in_polygon(pt, polygon)
            current_ids.add(det.track_id)

            if inside:
                if det.track_id not in tracks:
                    tracks[det.track_id] = CameraRuleState.TrackedObject(
                        track_id=det.track_id, enter_time=now, last_seen=now,
                        positions=[pt],
                    )
                else:
                    obj = tracks[det.track_id]
                    if not getattr(obj, "_alerted", False) and (now - obj.enter_time) >= duration_seconds:
                        matches.append({
                            "track_id": det.track_id,
                            "duration": round(now - obj.enter_time, 1),
                            "label": det.label,
                        })
                        obj._alerted = True
                    obj.last_seen = now
                    obj.positions.append(pt)
            else:
                if det.track_id in tracks:
                    del tracks[det.track_id]

        for tid in list(tracks.keys()):
            if tid not in current_ids:
                del tracks[tid]

        if matches:
            return RuleEvaluationResult(
                triggered=True, rule_id=rule.id, binding_id=binding.id,
                camera_id=camera_id, rule_type="loitering",
                matches=matches,
                details={"polygon": polygon, "duration_seconds": duration_seconds},
            )
        return None

    def _eval_count_threshold(self, rule: Any, binding: Any, camera_id: str,
                              detections: list[Detection], state: CameraRuleState,
                              config: dict) -> RuleEvaluationResult | None:
        min_count = config.get("min", 0)
        max_count = config.get("max")
        direction = config.get("direction", "above")
        polygon = config.get("polygon")

        if polygon:
            count = sum(1 for d in detections if self.point_in_polygon(d.centroid(), polygon))
        else:
            count = len(detections)

        triggered = False
        if direction == "above" and max_count is not None and count > max_count:
            triggered = True
        elif direction == "below" and count < min_count:
            triggered = True
        elif direction == "within":
            if (max_count is not None and count > max_count) or count < min_count:
                triggered = True

        if triggered:
            details: dict[str, Any] = {"count": count}
            if direction == "above" and max_count is not None:
                details["threshold_max"] = max_count
            elif direction == "below":
                details["threshold_min"] = min_count
            elif direction == "within":
                details["threshold_min"] = min_count
                details["threshold_max"] = max_count

            return RuleEvaluationResult(
                triggered=True, rule_id=rule.id, binding_id=binding.id,
                camera_id=camera_id, rule_type="count_threshold",
                matches=[], details=details,
            )
        return None
