from enum import Enum
import soundfile as sf
import signal
import logging
from datetime import datetime, timezone
import os
import asyncio
from events import *

logger = logging.getLogger("recorder")


class RecorderStates(Enum):
    STOPPED = "stopped"
    RECORDING = "recording"
    PLAYING = "playing"

@dataclass
class SoundFile:
    name: str
    duration: str

class Recorder:
    def __init__(self, eventQueue: asyncio.Queue):
        self.eventQueue: asyncio.Queue = eventQueue
        self.process = None
        self.state = RecorderStates.STOPPED
        self.output_path: str = "/home/marius/recordings"
        self.recorded_files: list[str] = []
        self.play_task: asyncio.Task = None

        self.list_recorded_files()

    def list_recorded_files(self):
        if not os.path.exists(self.output_path):
            return
        files = os.listdir(self.output_path)
        self.recorded_files = list(filter(lambda x: not os.path.isfile(x), files))
        self.recorded_files.sort(reverse=True)

        for f in self.recorded_files:
            info = sf.info(os.path.join(self.output_path, f))
            min, sec = divmod(int(info.duration), 60)
            print(f"File: {f} -> {min:02d}:{sec:02d}")

        self.eventQueue.put_nowait(EventRecordedFilesList(files=self.recorded_files))

    async def start_recording(self):
        await self.stop()

        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        filepath = os.path.join(self.output_path, datetime.now().strftime("%Y-%m-%d-%H:%M:%S")) + '.ogg'
        self.process = await asyncio.create_subprocess_exec('jack_capture', '-ns', '-f', 'ogg', '-V', '-dc', filepath)
        self.state = RecorderStates.RECORDING
        logger.info("Recording started")
        self.eventQueue.put_nowait(EventRecorderRecording(start=int(datetime.now(timezone.utc).timestamp())))

    async def stop(self):

        if self.state == RecorderStates.STOPPED:
            return

        if not self.process:
            return

        self.process.send_signal(signal.SIGTERM)
        # stdout, stderr = await self.process.communicate()
        await self.process.wait()

        self.process = None
        self.state = RecorderStates.STOPPED
        self.list_recorded_files()
        logger.info("Stopped")
        self.eventQueue.put_nowait(EventRecorderStopped())

    async def _wait_playback_finished(self):
        process = self.process
        returncode = await process.wait()

        if self.process is process:
            self.process = None
            self.state = RecorderStates.STOPPED
            self.eventQueue.put_nowait(EventRecorderStopped())

    async def start_playing(self, filename: str):
        await self.stop()

        if not os.path.exists(os.path.join(self.output_path, filename)):
            logger.error(f"File {filename} not found")
            return

        self.process = await asyncio.create_subprocess_exec('sndfile-jackplay', os.path.join(self.output_path, filename))
        self.state = RecorderStates.PLAYING
        logger.info("Playing started")
        self.play_task = asyncio.create_task(self._wait_playback_finished())
        self.eventQueue.put_nowait(EventRecorderPlaying(file=filename))
