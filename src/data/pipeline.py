import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.data.annotator import AnnotationPipeline
from src.data.cleaner import CleaningReport, FrameCleaner
from src.data.collector import FrameCollector

logger = logging.getLogger(__name__)


@dataclass
class DataPipelineResult:
    collected: int
    cleaned: int
    cleaning_report: CleaningReport | None = None
    exports: dict[str, Path] = field(default_factory=dict)


class DataPipeline:
    def __init__(
        self,
        collector: FrameCollector | None = None,
        cleaner: FrameCleaner | None = None,
        annotator: AnnotationPipeline | None = None,
    ):
        self._collector = collector or FrameCollector()
        self._cleaner = cleaner or FrameCleaner()
        self._annotator = annotator or AnnotationPipeline(Path("data/exports"))

    async def run_from_directory(
        self,
        source_dir: str | Path,
        camera_id: str = "unknown",
        export_formats: list[str] | None = None,
        dataset_name: str = "dataset",
    ) -> DataPipelineResult:
        frames = await self._collector.collect_from_directory(
            source_dir=source_dir,
            camera_id=camera_id,
        )

        cleaned, report = self._cleaner.clean(frames)

        exports = await self._annotator.export_all(
            frames=cleaned,
            dataset_name=dataset_name,
            formats=export_formats,
        )

        logger.info(
            "Data pipeline completed: %d collected, %d cleaned, exports: %s",
            len(frames), len(cleaned), exports,
        )
        return DataPipelineResult(
            collected=len(frames),
            cleaned=len(cleaned),
            cleaning_report=report,
            exports=exports,
        )

    async def run_from_video(
        self,
        video_path: str | Path,
        camera_id: str = "unknown",
        sample_rate: float = 1.0,
        export_formats: list[str] | None = None,
        dataset_name: str = "dataset",
    ) -> DataPipelineResult:
        frames = await self._collector.collect_from_video(
            video_path=video_path,
            camera_id=camera_id,
            sample_rate=sample_rate,
        )

        cleaned, report = self._cleaner.clean(frames)

        exports = await self._annotator.export_all(
            frames=cleaned,
            dataset_name=dataset_name,
            formats=export_formats,
        )

        logger.info(
            "Data pipeline from video completed: %d collected, %d cleaned",
            len(frames), len(cleaned),
        )
        return DataPipelineResult(
            collected=len(frames),
            cleaned=len(cleaned),
            cleaning_report=report,
            exports=exports,
        )
