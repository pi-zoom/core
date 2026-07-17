from pythonosc.udp_client import SimpleUDPClient
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from typing import List, Any
import asyncio
import threading
import logging
from .protocol import OSCMessage, SLCommand, SLGetControl, SLSetControl
from events import *

DEFAULT_LOOPER_ADDR = "127.0.0.1"
DEFAULT_LOOPER_PORT = 9951
DEFAULT_LOOPER_SERVER_PORT = 9952

logger = logging.getLogger("looper")


@dataclass
class Loop:
    id: int
    len: float
    pos: float
    state: int


class SooperLooperClient:

    def __init__(
        self,
        eventsQueue: asyncio.Queue,
        host: str = DEFAULT_LOOPER_ADDR,
        port: int = DEFAULT_LOOPER_PORT,
        serverPort: int = DEFAULT_LOOPER_SERVER_PORT,
    ):
        self.host = host
        self.port = port
        self.serverPort = serverPort
        self.eventsQueue = eventsQueue
        self.sendQueue = asyncio.Queue()
        self.tasks = []

        self.oscClient = None
        self.oscServer = None
        self.oscTransport = None
        self.oscProtocol = None
        self.connected = False
        self.pingInterval = 5

        # self.loopCount = 0
        self.selectedLoop = -1

        self.loops: list[Loop] = []

        self._init_osc()
        self._init_default_looper()

    def _init_osc(self):
        self.dispatcher = Dispatcher()
        self.dispatcher.map("/looper/loop_auto_update", self._loopAutoUpdateHandler)
        self.dispatcher.map("/looper/loop_count", self._loopCountUpdateHandler)
        self.dispatcher.map("/looper/loop_update", self._loopUpdateHandler)
        self.dispatcher.map("/looper/loop_info", self._loopInfoHandler)
        self.dispatcher.map("/looper/pong", self._pongHandler)
        self.dispatcher.set_default_handler(self._defaultHandler)
        self.oscClient = SimpleUDPClient(self.host, self.port)

    async def run(self):

        logger.info("Starting OSC server")
        self.oscServer = AsyncIOOSCUDPServer(
            server_address=("127.0.0.1", 9952),
            dispatcher=self.dispatcher,
            loop=asyncio.get_running_loop(),
        )
        self.oscTransport, self.oscProtocol = (
            await self.oscServer.create_serve_endpoint()
        )

        self.tasks.append(self._sendTask())
        self.tasks.append(self._pingTask())
        await asyncio.gather(*self.tasks)

    def stop(self):
        self.oscTransport.close()
        logger.info("OSC server stopped")

    async def _pingTask(self):
        logger.info("starting ping task")
        while True:
            self.ping()
            await asyncio.sleep(self.pingInterval)

    def _init_default_looper(self):
        self.ping()  # used if sl is already started
        self.registerUpdate(control=SLSetControl.SELECTED_LOOP_NUM)  ## selected
        self.registerLoopCount()
        self.set(param="sync_source", value=-1.0)
        self.set(param="eighth_per_cycle", value=8.0)

    def _defaultHandler(self, address, *args):
        logger.error(f"No handler for {address}: {args}")

    def _loopInfoHandler(self, address, loop, control, value):
        if loop > len(self.loops):
            return
        print(f"INFO {loop} {control}")
        if control == "loop_len":
            self.loops[loop].len = value
        elif control == "state":
            self.loops[loop].state = value

    def _pongHandler(self, address, hostUrl, version, loopCount):
        logger.info("pong")
        if not self.connected:
            logger.info("now connected")
            self.connected = True
            self._loopCountUpdateHandler(
                address=address, hostUrl=hostUrl, version=version, loopCount=loopCount
            )
            self.getLoopInfos()

        # self.loopCount = loopCount

    def _loopUpdateHandler(self, address, loop, control, value):
        if control == SLSetControl.SELECTED_LOOP_NUM.value:
            self.selectedLoop = int(value)

        msg = EventLoopSelected(id=int(value))
        self.eventsQueue.put_nowait(msg)

    def _loopCountUpdateHandler(self, address, hostUrl, version, loopCount):
        print("************************ok")
        # if self.loopCount == loopCount:
        #     return

        while len(self.loops) != loopCount:
            if len(self.loops) > loopCount:
                if len(self.loops) - 1 == self.selectedLoop:
                    self.selectLoop(loopCount - 1)
                self.loops.pop()

            elif len(self.loops) < loopCount:
                self.registerAutoUpdate(
                    loop=loopCount - 1, control=SLGetControl.LOOP_POS
                )
                self.registerAutoUpdate(
                    loop=loopCount - 1, control=SLGetControl.LOOP_LEN
                )
                self.registerAutoUpdate(loop=loopCount - 1, control=SLGetControl.STATE)
                self.setSync(loop=loopCount - 1, value=1.0)
                self.setPlaybackSync(loop=loopCount - 1, value=1.0)
                self.setQuantize(loop=loopCount - 1, value=1.0)
                self.selectLoop(loop=loopCount - 1)
                self.loops.append(Loop(id=len(self.loops), pos=0.0, len=0.0, state=0))

        # self.loopCount = loopCount

        msg = EventLoopCount(count=len(self.loops))
        self.eventsQueue.put_nowait(msg)

    def _loopAutoUpdateHandler(self, address, loop, control, value):
        if control == SLGetControl.LOOP_POS.value:
            if len(self.loops) > loop:
                self.loops[loop].pos = value
            msg = EventLoopPos(id=loop, pos=value)
        elif control == SLGetControl.LOOP_LEN.value:
            if len(self.loops) > loop:
                self.loops[loop].len = value
            msg = EventLoopLen(id=loop, len=value)
        elif control == SLGetControl.STATE.value:
            if len(self.loops) > loop:
                self.loops[loop].state = int(value)
            msg = EventLoopState(id=loop, state=value)
        else:
            return

        self.eventsQueue.put_nowait(msg)

    async def _sendTask(self):
        logger.info("starting send task")

        while True:
            data = await self.sendQueue.get()
            logger.debug(f"sending : {data}")
            try:
                self._send(data)
            except Exception as err:
                logger.error(err)

    def ping(self):
        logger.info("ping")
        self.sendQueue.put_nowait(
            OSCMessage(address="/ping", value=[f"{self.host}:9952", "/looper/pong"])
        )

    def addLoop(self):
        self.sendQueue.put_nowait(OSCMessage(address="/loop_add", value=[1, 40]))

    def removeLoop(self):
        self.sendQueue.put_nowait(OSCMessage(address="/loop_del", value=[-1]))

    def selectLoop(self, loop: int):
        self.sendQueue.put_nowait(
            OSCMessage(address="/set", value=["selected_loop_num", float(loop)])
        )

    def record(self, loop: int):
        self.sendQueue.put_nowait(
            OSCMessage(address=f"/sl/{loop}/hit", value=[SLCommand.RECORD.value])
        )

    def overdub(self, loop: int):
        self.sendQueue.put_nowait(
            OSCMessage(address=f"/sl/{loop}/hit", value=[SLCommand.OVERDUB.value])
        )

    def mute(self, loop: int):
        self.sendQueue.put_nowait(
            OSCMessage(address=f"/sl/{loop}/hit", value=[SLCommand.MUTE.value])
        )

    def undo(self, loop: int):
        self.sendQueue.put_nowait(
            OSCMessage(address=f"/sl/{loop}/hit", value=[SLCommand.UNDO.value])
        )

    def setQuantize(self, loop: int, value: float):
        self.sendQueue.put_nowait(
            OSCMessage(
                address=f"/sl/{loop}/set", value=[SLSetControl.QUANTIZE.value, value]
            )
        )

    def setSync(self, loop: int, value: float):
        self.sendQueue.put_nowait(
            OSCMessage(
                address=f"/sl/{loop}/set", value=[SLSetControl.SYNC.value, value]
            )
        )

    def setPlaybackSync(self, loop: int, value: float):
        self.sendQueue.put_nowait(
            OSCMessage(
                address=f"/sl/{loop}/set",
                value=[SLSetControl.PLAYBACK_SYNC.value, value],
            )
        )

    def set(self, param: str, value: float):
        self.sendQueue.put_nowait(OSCMessage(address=f"/set", value=[param, value]))

    def getLoopInfos(self):
        for loop in self.loops:
            self.sendQueue.put_nowait(
                OSCMessage(
                    address=f"/sl/{loop.id}/get",
                    value=[
                        SLGetControl.LOOP_LEN.value,
                        f"{self.host}:{self.serverPort}",
                        "/looper/loop_info",
                    ],
                )
            )
            self.sendQueue.put_nowait(
                OSCMessage(
                    address=f"/sl/{loop.id}/get",
                    value=[
                        SLGetControl.STATE.value,
                        f"{self.host}:{self.serverPort}",
                        "/looper/loop_info",
                    ],
                )
            )
            self.sendQueue.put_nowait(
                OSCMessage(
                    address=f"/sl/{loop.id}/get",
                    value=[
                        SLGetControl.LOOP_POS.value,
                        f"{self.host}:{self.serverPort}",
                        "/looper/loop_info",
                    ],
                )
            )
    def registerAutoUpdate(
        self, loop: int, control: SLGetControl, register: bool = True
    ):
        msg = None

        if register:
            msg = OSCMessage(
                address=f"/sl/{loop}/register_auto_update",
                value=[
                    control.name,
                    100,
                    f"{self.host}:{self.serverPort}",
                    "/looper/loop_auto_update",
                ],
            )
        else:
            msg = OSCMessage(
                address=f"/sl/{loop}/unregister_auto_update",
                value=[
                    control.name,
                    f"{self.host}:{self.serverPort}",
                    "/looper/loop_auto_update",
                ],
            )

        self.sendQueue.put_nowait(msg)

    def registerUpdate(self, control: SLGetControl, register: bool = True):
        msg = None

        if register:
            msg = OSCMessage(
                address=f"/register_update",
                value=[
                    control.name,
                    f"{self.host}:{self.serverPort}",
                    "/looper/loop_update",
                ],
            )
        else:
            msg = OSCMessage(
                address=f"/unregister_update",
                value=[
                    control.name,
                    f"{self.host}:{self.serverPort}",
                    "/looper/loop_update",
                ],
            )

        self.sendQueue.put_nowait(msg)

    def registerLoopCount(self):
        self.sendQueue.put_nowait(
            OSCMessage(
                address="/register",
                value=[f"{self.host}:{self.serverPort}", "/looper/loop_count"],
            )
        )

    def registerLoopSelected(self):
        self.sendQueue.put_nowait(
            OSCMessage(
                address="/register_update",
                value=[f"{self.host}:{self.serverPort}", "/looper/loop_selected"],
            )
        )

    def _send(self, msg: OSCMessage):
        self.oscClient.send_message(address=msg.address, value=msg.value)
