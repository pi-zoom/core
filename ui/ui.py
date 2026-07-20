import zmq
import zmq.asyncio
import asyncio

import json
import logging
from events import *
from command import *

DEFAULT_SUB_ADDR = "localhost"
DEFAULT_SUB_PORT = 9955
DEFAULT_PUB_ADDR = "localhost"
DEFAULT_PUB_PORT = 9956

logger = logging.getLogger("ui")
logger.setLevel(level=logging.DEBUG)

class UI():
    def __init__(
        self,
        commandsQueue: asyncio.Queue,
        subAddr: str = DEFAULT_SUB_ADDR,
        subPort: int = DEFAULT_SUB_PORT,
        pubAddr: str = DEFAULT_PUB_ADDR,
        pubPort: int = DEFAULT_PUB_PORT,
    ):
        self.subAddr = subAddr
        self.subPort = subPort
        self.pubAddr = pubAddr
        self.pubPort = pubPort

        self.commandsQueue = commandsQueue
        self.context = zmq.asyncio.Context()
        self.subSocket = self.context.socket(zmq.SUB)
        self.subSocket.connect(f"tcp://{self.subAddr}:{self.subPort}")
        self.subSocket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.pubSocket = self.context.socket(zmq.PUB)
        self.pubSocket.bind(f"tcp://{self.pubAddr}:{self.pubPort}")

    async def send(self, msg: dict):
        logger.debug(f"sending: {msg["type"]}")
        # msg = json.dumps(msg)
        await self.pubSocket.send_json(msg)

    def stop(self):
        self.subSocket.close()
        logger.debug("UI stopped")

    async def run(self):
        logger.info("Starting ZMQ server")
        while True:
            try:
                data = await self.subSocket.recv_string()
                data_json = json.loads(data)

                command_type = data_json.get("type", None)
                if command_type is None:
                    logger.error(f"Unable to get command type. Message: {data_json}")
                    continue

                if command_type == 0:
                    msg = CmdAddLoop()
                elif command_type == 1:
                    msg = CmdRemoveLoop()
                elif command_type == 2:
                    msg = CmdSelectLoop(id=data_json.get("id"))
                elif command_type == 3:
                    msg = CmdSelectPedalboard(name=data_json.get("name"))
                elif command_type == 4:
                    msg  = CmdSetEffectParam(instance_id=data_json["instance_id"], symbol=data_json["symbol"], value=data_json["value"])
                elif command_type == 5:
                    msg = CmdListPedalboards()
                elif command_type == 6:
                    msg = CmdSelectPedalboardSnapshot(index=data_json["index"])
                elif command_type == 7:
                    msg = CmdListLoops()
                elif command_type == 8:
                    msg = CmdSequencerSetBpm(bpm=data_json["bpm"])
                elif command_type == 9:
                    msg = CmdSequencerSetVolume(volume=data_json["volume"])
                elif command_type == 10:
                    msg = CmdSequencerSelectMidiFile(file=data_json["file"])
                elif command_type == 11:
                    msg = CmdSequencerListMidiFiles()
                elif command_type == 12:
                    msg = CmdTuner(state=data_json["state"])
                else:
                    logger.error(f"Unknown ZMQ message type: {data_json}")
                    continue
                self.commandsQueue.put_nowait(msg)
            except Exception as error:
                logger.error(f"Error receiving ZMQ: {error}")
