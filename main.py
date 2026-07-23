import asyncio
import inspect
import signal
import logging
import json
from dataclasses import asdict
from looper.looper import SooperLooperClient
from ui.ui import UI
from mod.mod import Mod
from sequencer.sequencer import Sequencer
from tuner.tuner import Tuner
from recorder.recorder import Recorder

from events import *
from command import *

logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("app")
logger.setLevel(level=logging.DEBUG)


eventHandlers = {}


def event_handler(func):
    params = list(inspect.signature(func).parameters.values())
    if len(params) != 1:
        raise TypeError("Handler must take exactly one argument")

    event_type = params[0].annotation
    if event_type is inspect.Signature.empty:
        raise TypeError("Handler argument must be annotated")

    eventHandlers[event_type] = func
    return func


commandHandlers = {}


def command_handler(func):
    params = list(inspect.signature(func).parameters.values())
    if len(params) != 1:
        raise TypeError("Handler must take exactly one argument")

    command_type = params[0].annotation
    if command_type is inspect.Signature.empty:
        raise TypeError("Handler argument must be annotated")

    commandHandlers[command_type] = func
    return func


# -----------------------------
# Shared event queue
# -----------------------------
commandsQueue = asyncio.Queue(maxsize=1000)
eventsQueue = asyncio.Queue(maxsize=1000)
stopEvent = asyncio.Event()

looper = SooperLooperClient(eventsQueue=eventsQueue)
ui = UI(commandsQueue=commandsQueue)
mod = Mod("localhost", 8888, queue=eventsQueue)
sequencer = Sequencer(eventsQueue=eventsQueue)
tuner = Tuner(queue=eventsQueue)
recorder = Recorder()

# -----------------------------
# Shutdown handling
# -----------------------------
def setup_signals():
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, stopEvent.set)
    loop.add_signal_handler(signal.SIGTERM, stopEvent.set)


# -----------------------------
# Events handling
# -----------------------------
@event_handler
async def loopCountHandler(event: EventLoopCount):
    await ui.send({"type": 0, "count": event.count})


@event_handler
async def loopPosHandler(event: EventLoopPos):
    await ui.send({"type": 1, "id": event.id, "pos": event.pos})


@event_handler
async def loopLenHandler(event: EventLoopLen):
    await ui.send({"type": 2, "id": event.id, "len": event.len})


@event_handler
async def loopStateHandler(event: EventLoopState):
    await ui.send({"type": 3, "id": event.id, "state": event.state})


@event_handler
async def loopSelectedHandler(event: EventLoopSelected):
    await ui.send({"type": 4, "id": event.id})


@event_handler
async def modListPedalboard(event: EventPedalboardList):
    await ui.send({"type": 5, "pedalboards": event.pedalboards})


@event_handler
async def modPedalboardLoaded(event: EventPedalboardLoaded):
    print(json.dumps(event.pedalboard, indent=4))
    await ui.send({"type": 6, "pedalboard": event.pedalboard})


@event_handler
async def modEffectParam(event: EventEffectParam):
    await ui.send(
        {
            "type": 7,
            "instance_id": event.instance_id,
            "symbol": event.symbol,
            "value": event.value,
        }
    )


@event_handler
async def modSnapshotChanged(event: EventSnapshotChanged):
    await ui.send({"type": 8, "index": event.index, "name": event.name})


@event_handler
async def loopListHandler(event: EventLoopsList):
    await ui.send({"type": 9, "loops": event.loops})

@event_handler
async def sequencerMidiFilesList(event: EventSequencerMidiFilesList):
    await ui.send({"type": 10, "files": event.midiFiles})

@event_handler
async def sequencerPosition(event: EventSequencerPos):
    await ui.send({"type": 11, "pos": event.pos})

@event_handler
async def tunerUpdate(event: EventTuner):
    print(f"Note: {event.note} Cents: {event.cents}")
    await ui.send({"type": 12, "note": event.note, "cents": event.cents})

@event_handler
async def recordedFileList(event: EventRecordedFilesList):
    await ui.send({"type": 13, "files": event.files})

# -----------------------------
# Commnands handling
# -----------------------------

@command_handler
async def listLoopsHandler(_: CmdListLoops):
    loops = []
    for loop in looper.loops:
        loops.append(asdict(loop))
    eventsQueue.put_nowait(EventLoopsList(loops=loops))


@command_handler
async def addLoopHandler(_: CmdAddLoop):
    looper.addLoop()


@command_handler
async def removeLoopHandler(_: CmdRemoveLoop):
    looper.removeLoop()


@command_handler
async def selectLoopHandler(event: CmdSelectLoop):
    looper.selectLoop(loop=event.id)


@command_handler
async def selectPedalboardHandler(event: CmdSelectPedalboard):
    await mod.setPedalboard(name=event.name)


@command_handler
async def setEffectParamHandler(event: CmdSetEffectParam):
    await mod.setEffectParam(
        instance_id=event.instance_id, symbol=event.symbol, value=event.value
    )


@command_handler
async def listPedalboardsHandler(event: CmdListPedalboards):
    # maybe we need to call mod and let it reload??
    eventsQueue.put_nowait(
        EventPedalboardList(
            pedalboards=list([x.title for x in mod.pedalboards.values()])
        )
    )

    pedalboard = mod.pedalboards.get(mod._current_pedalboard_name, None)
    if pedalboard:
        eventsQueue.put_nowait(EventPedalboardLoaded(pedalboard=asdict(pedalboard)))


@command_handler
async def selectPedalboardSnapshotHandler(event: CmdSelectPedalboardSnapshot):
    await mod.setPedalboardSnapshot(index=event.index)


@command_handler
async def sequencerSetBpm(event: CmdSequencerSetBpm):
    sequencer.set_bpm(bpm=event.bpm)


@command_handler
async def sequencerSetVolume(event: CmdSequencerSetVolume):
    sequencer.set_volume(volume=event.volume)

@command_handler
async def sequencerSelectMidiFile(event: CmdSequencerSelectMidiFile):
    sequencer.set_selected_midi_file(midi_file=event.file)

@command_handler
async def sequencerListMidiFiles(event: CmdSequencerListMidiFiles):
    eventsQueue.put_nowait(EventSequencerMidiFilesList(midiFiles=sequencer.midi_files))

@command_handler
async def sequencerState(event: CmdSequencerState):
    sequencer.set_state(play=event.state)

@command_handler
async def sequencerMute(event: CmdSequencerMute):
    sequencer.set_mute(mute=event.mute)

@command_handler
async def tunerState(event: CmdTuner):
    if(event.state):
        await tuner.start(loop=asyncio.get_event_loop())
    else:
        await tuner.stop()

@command_handler
async def playerRecord(event: CmdPlayerRecord):
    if event.state:
        await recorder.start_recording()
    else:
        await recorder.stop()
        eventsQueue.put_nowait(EventRecordedFilesList(files=recorder.recorded_files))

@command_handler
async def playerPlay(event: CmdPlayerPlay):
    if event.state:
        await recorder.start_playing(filename=event.file)
    else:
        await recorder.stop()

async def processCommands():
    while True:
        command = await commandsQueue.get()
        try:
            handler = commandHandlers.get(type(command), None)
            logger.debug(f"Received command : {command}")
            if handler:
                try:
                    # use iscoroutinefunction
                    await handler(command)
                except Exception as error:
                    logger.exception(f"Error in handler {handler}. Error: {error}")
            else:
                logger.error(f"No handler for command {type(command)}")
        finally:
            commandsQueue.task_done()


async def processEvents():
    while True:
        event = await eventsQueue.get()
        try:
            handler = eventHandlers.get(type(event), None)
            logger.debug(f"Received events : {type(event)}")
            if handler:
                try:
                    await handler(event)
                except Exception as error:
                    logger.exception(f"Error in handler {handler}. Error: {error}")
            else:
                logger.error(f"No handler for {type(event)}")
        finally:
            eventsQueue.task_done()


async def run_app():
    setup_signals()

    tasks = [
        asyncio.create_task(processCommands()),
        asyncio.create_task(processEvents()),
        asyncio.create_task(looper.run()),
        asyncio.create_task(mod.run()),
        asyncio.create_task(ui.run()),
        asyncio.create_task(sequencer.run()),
    ]

    # wait for Ctrl+C / SIGTERM
    await stopEvent.wait()
    logger.info("Shuting down...")

    # stop receivers
    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    looper.stop()
    ui.stop()

    await eventsQueue.join()

    logger.info("Shutdown complete.")

    pass


if __name__ == "__main__":
    asyncio.run(run_app())
