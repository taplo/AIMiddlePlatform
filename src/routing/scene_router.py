import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

SceneMatcher = Callable[[dict], str | None]


class SceneRouter:
    def __init__(self) -> None:
        self._routes: dict[str, str] = {}
        self._matchers: list[SceneMatcher] = []
        self._last_modified: float = 0.0
        self._watch_path: Path | None = None

    def register_route(self, scene_id: str, pipeline_name: str) -> None:
        self._routes[scene_id] = pipeline_name
        logger.info("Route registered: %s -> %s", scene_id, pipeline_name)

    def unregister_route(self, scene_id: str) -> None:
        self._routes.pop(scene_id, None)

    def add_matcher(self, matcher: SceneMatcher) -> None:
        self._matchers.append(matcher)

    def resolve(self, frame_context: dict) -> str | None:
        for matcher in self._matchers:
            result = matcher(frame_context)
            if result is not None:
                return result

        scene_id = self._hash_scene(frame_context)
        return self._routes.get(scene_id)

    def enable_hot_reload(self, path: str | Path, interval: float = 10.0) -> None:
        self._watch_path = Path(path)
        self._last_modified = self._watch_path.stat().st_mtime if self._watch_path.exists() else 0

    def check_reload(self) -> bool:
        if self._watch_path is None or not self._watch_path.exists():
            return False
        mtime = self._watch_path.stat().st_mtime
        if mtime > self._last_modified:
            self._load_routes_from_file(self._watch_path)
            self._last_modified = mtime
            return True
        return False

    def _load_routes_from_file(self, path: Path) -> None:
        try:
            with open(path) as f:
                data = json.load(f)
            for item in data:
                self.register_route(item["scene_id"], item["pipeline"])
            logger.info("Routes loaded from %s (%d entries)", path, len(data))
        except Exception as e:
            logger.error("Failed to load routes: %s", e)

    @staticmethod
    def _hash_scene(context: dict) -> str:
        raw = json.dumps(context, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
