import zmq
import zmq.asyncio
import asyncio
from dacite import from_dict
import json
import logging
from events import *
from command import *

DEFAULT_SUB_ADDR = "localhost"
DEFAULT_SUB_PORT = 9955
DEFAULT_PUB_ADDR = "localhost"
DEFAULT_PUB_PORT = 9956

logger = logging.getLogger("ui")
logger.setLevel(level=logging.INFO)

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
        print(msg)
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

                try:
                    cmd = Command(command_type)
                    msg = None
                    match cmd:
                        case Command.CMD_LOOPER_ADD_LOOP:
                            msg = from_dict(CmdAddLoop, data_json)
                        case Command.CMD_LOOPER_REMOVE_LOOP:
                            msg = from_dict(CmdRemoveLoop, data_json)
                        case Command.CMD_LOOPER_SELECT_LOOP:
                            msg = from_dict(CmdSelectLoop, data_json)
                        case Command.CMD_LOOPER_LIST_LOOPS:
                            msg = from_dict(CmdListLoops, data_json)
                        case Command.CMD_LOOPER_SET_LOOP_VOLUME:
                            msg = from_dict(CmdLooperSetLoopVolume, data_json)
                        case Command.CMD_MOD_LIST_PEDALBOARDS:
                            msg = from_dict(CmdListPedalboards, data_json)
                        case Command.CMD_MOD_SELECT_PEDALBOARD:
                            msg = from_dict(CmdSelectPedalboard, data_json)
                        case Command.CMD_MOD_SELECT_SNAPSHOT:
                            msg = from_dict(CmdSelectPedalboardSnapshot, data_json)
                        case Command.CMD_MOD_SET_EFFECT_PARAM:
                            msg = from_dict(CmdSetEffectParam, data_json)
                        case Command.CMD_SEQUENCER_LIST_MIDI_FILES:
                            msg = from_dict(CmdSequencerListMidiFiles, data_json)
                        case Command.CMD_SEQUENCER_MUTE:
                            msg = from_dict(CmdSequencerMute, data_json)
                        case Command.CMD_SEQUENCER_PLAY:
                            msg = from_dict(CmdSequencerPlay, data_json)
                        case Command.CMD_SEQUENCER_SELECT_MIDI_FILE:
                            msg = from_dict(CmdSequencerSelectMidiFile, data_json)
                        case Command.CMD_SEQUENCER_SET_BPM:
                            msg = from_dict(CmdSequencerSetBpm, data_json)
                        case Command.CMD_SEQUENCER_SET_VOLUME:
                            msg = from_dict(CmdSequencerSetVolume, data_json)
                        case Command.CMD_PLAYER_LIST_FILES:
                            msg = from_dict(CmdPlayerListFiles, data_json)
                        case Command.CMD_PLAYER_SET_STATE:
                            msg = from_dict(CmdPlayerState, data_json)
                        case Command.CMD_TUNER_STATE:
                            msg = from_dict(CmdTunerState, data_json)

                    if msg:
                        self.commandsQueue.put_nowait(msg)
                except ValueError:
                    logger.error(f"Unknowed command {command_type}")
                    continue

            except Exception as error:
                logger.error(f"Error receiving ZMQ: {error}")
