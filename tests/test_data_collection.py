import numpy as np
import pytest

from src.data.collector import FrameCollector


@pytest.mark.asyncio
async def test_collect_agent_pair(tmp_path):
    collector = FrameCollector(output_dir=str(tmp_path))
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    path = await collector.collect_agent_pair(
        camera_id="cam-test",
        image=img,
        context={"scene": "intersection"},
        result={"analysis": {"scene_type": "traffic"}},
    )
    assert path is not None
    assert path.exists()
    assert "cam-test" in path.name


@pytest.mark.asyncio
async def test_collect_agent_pair_disabled(tmp_path):
    collector = FrameCollector(output_dir=str(tmp_path))
    img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    path = await collector.collect_agent_pair(
        camera_id="cam-test",
        image=img,
        context={},
        result={},
    )
    assert path is not None


@pytest.mark.asyncio
async def test_collector_save_frames(tmp_path):
    from src.data.collector import CollectedFrame
    collector = FrameCollector(output_dir=str(tmp_path))
    frames = [
        CollectedFrame(camera_id="cam-1", timestamp=1000.0, image=np.zeros((10, 10, 3), dtype=np.uint8)),
    ]
    saved = await collector.save_frames(frames, subdir="test")
    assert len(saved) == 1
    assert saved[0].exists()
