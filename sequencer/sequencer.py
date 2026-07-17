import logging
import asyncio
from pathlib import Path
from watchfiles import Change, awatch
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from events import *

DEFAULT_SEQUENCER_ADDR = "127.0.0.1"
DEFAULT_SEQUENCER_PORT = 9999
DEFAULT_SEQUENCER_SERVER_PORT = 9998
DEFAULT_MIDI_FOLDER = "~/.midi"

logger = logging.getLogger("sequencer")


class Sequencer:
    def __init__(
        self,
        eventsQueue: asyncio.Queue,
        host: str = DEFAULT_SEQUENCER_ADDR,
        port: int = DEFAULT_SEQUENCER_PORT,
        serverPort: int = DEFAULT_SEQUENCER_SERVER_PORT,
        midiFolder: str = DEFAULT_MIDI_FOLDER,
    ):
        self.eventsQueue = eventsQueue
        self.host = host
        self.port = port
        self.serverPort = serverPort
        self.sendQueue = asyncio.Queue()
        self.tasks = []

        self._midi_folder = midiFolder
        self._midi_files: list[str] = []

        self.oscClient = None
        self.oscServer = None
        self.oscTransport = None
        self.oscProtocol = None
        self.connected = False
        self.pingInterval = 5

        # current values
        self._volume = None
        self._bpm = 120
        self._selectedMidiFile = None
        self._muted = False
        self._selectedMidiFileDuration = None

        self._init_osc()
        self._list_midi_files()

    def _init_osc(self):
        self.dispatcher = Dispatcher()
        self.dispatcher.map("/sequencer/midi_file_info", self._midiFileInfoHandler)
        self.dispatcher.map("/sequencer/midi_pos", self._midiPosHandler)
        self.dispatcher.map("/sequencer/pong", self._pongHandler)
        self.dispatcher.set_default_handler(self._defaultHandler)
        self.oscClient = SimpleUDPClient(self.host, self.port)

    async def run(self):

        logger.info("Starting OSC server")
        self.oscServer = AsyncIOOSCUDPServer(
            server_address=("127.0.0.1", self.serverPort),
            dispatcher=self.dispatcher,
            loop=asyncio.get_running_loop(),
        )
        self.oscTransport, self.oscProtocol = (
            await self.oscServer.create_serve_endpoint()
        )

        self.tasks.append(self._sendTask())
        self.tasks.append(self._pingTask())
        await asyncio.gather(*self.tasks)

    async def _pingTask(self):
        logger.info("starting ping task")
        while True:
            self.ping()
            await asyncio.sleep(self.pingInterval)

    def ping(self):
        self.sendQueue.put_nowait(
            {
                "address": "/sequencer/ping",
                "value": [f"{self.host}:9952", "/sequencer/pong"],
            }
        )

    def _midiPosHandler(self, address, pos):
        self.eventsQueue.put_nowait(EventSequencerPos(pos=pos))

    def _midiFileInfoHandler(self, address, midi_file, duration):
        print(f"{address} {midi_file} {duration}")

    def _pongHandler(self, address, *message):
        logger.info("pong")
        if not self.connected:
            logger.info("now connected")
            self.connected = True

    def _defaultHandler(self):
        print("default")

    def _send(self, data: dict):
        self.oscClient.send_message(address=data["address"], value=data["value"])

    async def _sendTask(self):
        logger.info("starting send task")

        while True:
            data = await self.sendQueue.get()
            logger.info(f"sending : {data}")
            try:
                self._send(data)
            except Exception as err:
                logger.error(err)

    @property
    def midi_files(self) -> list[str]:
        return self._midi_files

    @midi_files.setter
    def midi_files(self, midi_files: list[str]):
        self._midi_files = midi_files

    def _list_midi_files(self):
        if not Path(self._midi_folder).expanduser().is_dir():
            logger.error(f"MIDI folder {self._midi_folder} not found")
            return

        for file in Path(self._midi_folder).expanduser().iterdir():
            if file.is_file() and file.suffix in [".mid", ".midi"]:
                self._midi_files.append(file.name)

        self.eventsQueue.put_nowait(
            EventSequencerMidiFilesList(midiFiles=self._midi_files)
        )

    def set_selected_midi_file(self, midi_file: str):
        self.sendQueue.put_nowait(
            {
                "address": "/sequencer/load_midi_file",
                "value": [
                    midi_file,
                    f"localhost:{self.serverPort}",
                    "/sequencer/midi_file_info",
                ],
            }
        )

    def set_bpm(self, bpm: int):
        self.sendQueue.put_nowait({"address": "/sequencer/bpm", "value": bpm})
        self._bpm = bpm

    def set_state(self, play: bool):
        self.sendQueue.put_nowait({"address": "/sequencer/state", "value": play})

    def set_volume(self, volume: int):
        self.sendQueue.put_nowait({"address": "/sequencer/volume", "value": volume})
        self._volume = volume

    def set_mute(self, mute: bool):
        self.sendQueue.put_nowait({"address": "/sequencer/mute", "value": mute})
        self._muted = mute
