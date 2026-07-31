from enum import Enum
import soundfile as sf
import signal
import logging
from datetime import datetime, timezone
import os
import asyncio
from events import *
from dataclasses import asdict, dataclass

logger = logging.getLogger("player")


class PlayerStates(Enum):
    STOPPED = 0
    PLAYING = 1
    RECORDING = 2

@dataclass
class SoundFile:
    name: str
    duration: str

class Player:
    def __init__(self, eventQueue: asyncio.Queue):
        self.eventQueue: asyncio.Queue = eventQueue
        self.process = None
        self.state = PlayerStates.STOPPED
        self.output_path: str = "/home/marius/recordings"
        self.sound_files: list[SoundFile] = []
        self.play_task: asyncio.Task = None

        self.list_sound_files()

    def list_sound_files(self):
        if not os.path.exists(self.output_path):
            return
        for file in os.listdir(self.output_path):
            if not os.path.isfile(os.path.join(self.output_path, file)):
                continue
            info = sf.info(os.path.join(self.output_path, file))
            min, sec = divmod(int(info.duration), 60)
            self.sound_files.append(SoundFile(name=file, duration=f"{min} min {sec} s"))

        self.sound_files.sort(reverse=True, key=lambda x: x.name)
        self.eventQueue.put_nowait(EventPlayerFilesList(files=self.sound_files))

    async def start_recording(self):
        await self.stop()

        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        filepath = os.path.join(self.output_path, datetime.now().strftime("%Y-%m-%d-%H:%M:%S")) + '.ogg'
        self.process = await asyncio.create_subprocess_exec('jack_capture', '-ns', '-f', 'ogg', '-V', '-dc', filepath)
        self.state = PlayerStates.RECORDING
        logger.info("Recording started")
        self.eventQueue.put_nowait(EventPlayerState(state=PlayerStates.RECORDING.value))

    async def stop(self):

        if self.state == PlayerStates.STOPPED:
            return

        if not self.process:
            return

        self.process.send_signal(signal.SIGTERM)
        # stdout, stderr = await self.process.communicate()
        await self.process.wait()

        self.process = None
        self.state = PlayerStates.STOPPED
        self.list_sound_files()
        logger.info("Stopped")
        self.eventQueue.put_nowait(EventPlayerState(state=PlayerStates.STOPPED.value))

    async def _wait_playback_finished(self):
        process = self.process
        returncode = await process.wait()

        if self.process is process:
            self.process = None
            self.state = PlayerStates.STOPPED
            self.eventQueue.put_nowait(EventPlayerState(state=PlayerStates.STOPPED.value))

    async def start_playing(self, filename: str):
        await self.stop()

        if not os.path.exists(os.path.join(self.output_path, filename)):
            logger.error(f"File {filename} not found")
            return

        self.process = await asyncio.create_subprocess_exec('sndfile-jackplay', os.path.join(self.output_path, filename))
        self.state = PlayerStates.PLAYING
        logger.info("Playing started")
        self.play_task = asyncio.create_task(self._wait_playback_finished())
        self.eventQueue.put_nowait(EventPlayerState(state=PlayerStates.PLAYING.value))

    async def set_state(self, state: int, file: str = None):
        if state == PlayerStates.RECORDING.value:
            await self.start_recording()
        elif state == PlayerStates.PLAYING.value:
            await self.start_playing(filename=file)
        else:
            await self.stop()