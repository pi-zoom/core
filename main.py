import asyncio
import inspect
import signal
import logging
from dataclasses import asdict
from looper.looper import SooperLooperClient
from ui.ui import UI
from mod.mod import Mod
from sequencer.sequencer import Sequencer

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

# -----------------------------
# Commnands handling
# -----------------------------
import json


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

async def processCommands():
    while True:
        command = await commandsQueue.get()
        try:
            handler = commandHandlers.get(type(command), None)
            logger.debug(f"Received command : {command}")
            if handler:
                try:
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

    # await mod.listPedalboards()

    # await mod.start()
    # await ui.start()

    # wait for Ctrl+C / SIGTERM
    await stopEvent.wait()
    logger.info("Shuting down...")

    # stop receivers
    for t in tasks:
        t.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    # close OSC transport
    looper.stop()
    ui.stop()

    # drain queue (optional but safe)
    await eventsQueue.join()

    logger.info("Shutdown complete.")

    pass


if __name__ == "__main__":
    asyncio.run(run_app())

# if __name__ == '__main__':
#     looper = SooperLooperClient(rxCallback=rx_from_looper)
#     ui = UI(rxCallback=rx_from_ui)
#     looper.register_loop_pos_update(loop=0)
#     looper.register_loop_count()


# import asyncio
# import signal

# import zmq
# import zmq.asyncio
# from pythonosc.osc_server import AsyncIOOSCUDPServer
# from pythonosc.dispatcher import Dispatcher
# from pythonosc.udp_client import SimpleUDPClient

# # -----------------------------
# # Shared event queue
# # -----------------------------
# events_queue = asyncio.Queue(maxsize=10000)
# stopEvent = asyncio.Event()


# # -----------------------------
# # ZMQ receiver
# # -----------------------------
# async def zmq_receiver():
#     ctx = zmq.asyncio.Context()
#     sock = ctx.socket(zmq.SUB)
#     sock.connect("tcp://localhost:5555")
#     sock.setsockopt_string(zmq.SUBSCRIBE, "")

#     try:
#         while not stopEvent.is_set():
#             msg = await sock.recv_string()

#             event = {
#                 "source": "zmq",
#                 "data": msg,
#             }

#             await queue.put(event)

#     except asyncio.CancelledError:
#         pass
#     finally:
#         sock.close()
#         ctx.term()


# def loop_count(address, hostUrl, version, loopCount):
#     print("Loop count")

# def loop_auto_update(address, loop, control, value):
#     print("loop update")

# dispatcher = Dispatcher()
# dispatcher.map("/looper/loop_auto_update", loop_auto_update)
# dispatcher.map("/looper/loop_count", loop_count)


# async def start_osc_server(host="0.0.0.0", port=9000):
#     loop = asyncio.get_running_loop()

#     server = AsyncIOOSCUDPServer(server_address=("127.0.0.1", 9952), dispatcher=dispatcher, loop=asyncio.get_event_loop())
#     transport, protocol = await server.create_serve_endpoint()

#     return transport

# -----------------------------
# Event processor
# -----------------------------
# async def processor():
#     while True:
#         try:
#             event = await asyncio.wait_for(queue.get(), timeout=0.5)
#         except asyncio.TimeoutError:
#             if stopEvent.is_set() and queue.empty():
#                 break
#             continue

#         try:
#             await handle_event(event)
#         finally:
#             queue.task_done()


# async def handle_event(event):
#     if event["source"] == "zmq":
#         print("[ZMQ]", event["data"])

#     elif event["source"] == "osc":
#         print("[OSC]", event["addr"], len(event["raw"]))


# # -----------------------------
# # Shutdown handling
# # -----------------------------
# def setup_signals(loop):
#     loop.add_signal_handler(signal.SIGINT, stopEvent.set)
#     loop.add_signal_handler(signal.SIGTERM, stopEvent.set)


# -----------------------------
# Main
# -----------------------------
# async def main():
#     loop = asyncio.get_running_loop()
#     setup_signals(loop)

#     print("Starting system...")

#     osc_transport = await start_osc_server()
#     oscClient = SimpleUDPClient("127.0.0.1", 9951)
#     oscClient.send_message(address="/register", value=["127.0.0.1:9952", "/looper/loop_count"])
#     tasks = [
#         asyncio.create_task(zmq_receiver()),
#         asyncio.create_task(processor()),
#     ]

#     # wait for Ctrl+C / SIGTERM
#     await stopEvent.wait()
#     print("Shutdown requested...")

#     # stop receivers
#     for t in tasks:
#         t.cancel()

#     await asyncio.gather(*tasks, return_exceptions=True)

#     # close OSC transport
#     osc_transport.close()

#     # drain queue (optional but safe)
#     await queue.join()

#     print("Shutdown complete.")


# if __name__ == "__main__":
#     asyncio.run(main())
