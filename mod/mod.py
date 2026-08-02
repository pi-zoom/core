from pathlib import Path
from typing import Tuple
import traceback
import httpx
import asyncio
import logging
import os
import lilv
import urllib
import requests as req
import sys
import json
import websockets
from dataclasses import asdict, dataclass
from events import (
    Event,
    EventPedalboardLoaded,
    EventEffectParam,
    EventSnapshotChanged,
    EventTunerOutput,
    EventTunerState,
)
from watchfiles import Change, awatch
import re
from graphlib import TopologicalSorter
from collections import defaultdict
from mod.protocol import (
    DataReadyMessage,
    TunerOutputMessage,
    TunerStateMessage,
    parse_message,
    ModMessage,
    LoadingEndMessage,
    ParamSetMessage,
    PedalSnapshotMessage,
)

logger = logging.getLogger("mod")
logger.setLevel(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.ERROR)


@dataclass
class PluginParameterRanges:
    minimum: float
    maximum: float
    default: float


@dataclass
class PluginParameterUnits:
    label: str
    render: str
    symbol: str
    _custom: bool


@dataclass
class PluginParameterScalePoints:
    valid: bool
    value: float
    label: str


@dataclass
class PluginParameter:
    index: int
    name: str
    symbol: str
    ranges: PluginParameterRanges
    units: PluginParameterUnits
    scalePoints: list[PluginParameterScalePoints]
    properties: list[str]
    shortName: str


@dataclass
class Plugin:
    name: str
    uri: str
    label: str
    instance_id: str
    bundle: str
    category: list[str]
    params: list[PluginParameter]
    bypassed: bool


@dataclass
class Snapshot:
    index: int
    name: str


@dataclass
class Pedalboard:
    title: str
    bundle: str
    plugins: list[Plugin]
    snapshots: list[Snapshot]
    snapshot_id: int


class Mod:
    def __init__(
        self,
        host: str,
        port: int,
        eventsQueue: asyncio.Queue,
        reconnect_min: float = 1.0,
        reconnect_max: float = 30.0,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        rx_queue_size: int = 1000,
        tx_queue_size: int = 1000,
    ):
        self.host = host
        self.port = port
        self.mod_ui_url = f"http://{self.host}:{self.port}"
        self.mod_ui_ws = f"ws://{self.host}:{self.port}/websocket"

        self.eventsQueue = eventsQueue
        self.client = httpx.AsyncClient()

        self._tasks: list[asyncio.Task] = []
        self.ws = None
        self.rx_queue = asyncio.Queue(maxsize=rx_queue_size)
        self.tx_queue = asyncio.Queue(maxsize=tx_queue_size)
        self._stop = asyncio.Event()

        self._reconnect_min = reconnect_min
        self._reconnect_max = reconnect_max

        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout

        self.pedalboards: dict[str, Pedalboard] = {}
        self.plugins: dict[str, Plugin] = {}
        self.current_pedalboard: Pedalboard = None

        self._data_path = Path("/home/marius/wks/git/guitare/pi-zoom/mod-ui/data/")
        self._last_pedalboard_path = Path(self._data_path, "last.json")
        self._pedalboards_folder = "/home/pedal/.pedalboards"

    async def _request(
        self, method: str, url: str, data=None, params=None
    ) -> Tuple[bool, dict]:
        """Send HTTP request to mod-ui

        Args:
            method (str): GET or POST
            url (str): Url to send request to
            data (dict, optional): Data to sent using POST. Defaults to None.
            params (optional): Data to send using POST or GET. Defaults to None.

        Raises:
            Exception: Raised if method is not POST or GET

        Returns:
            Tuple[bool, dict]: Tuple of (status, response)
        """
        if method not in ["GET", "POST"]:
            raise Exception("Method must be GET or POST")

        ret = (False, None)
        try:
            response = None
            if method == "GET":
                response = await self.client.get(url=url, params=params)
            else:
                response = await self.client.post(url=url, data=data, params=params)
            response.raise_for_status()
            ret = (True, response.json())
        except httpx.RequestError as error:
            logger.error(f"An error occurred while requesting {error.request.url!r}.")
        except httpx.HTTPStatusError as error:
            logger.error(
                f"Error response {error.response.status_code} while requesting {error.request.url!r}."
            )
        return ret

    def _push_event(self, event: Event):
        """Push an event to the main thread

        Args:
            event (Event): event to push
        """
        try:
            self.eventsQueue.put_nowait(event)
        except asyncio.QueueFull as error:
            logger.error(f"Unable to push event. Queue full")

    async def _get_pedalboard_info(self, bundlepath: str) -> dict:
        """Get pedalboard info using mod-ui API.

        Args:
            bundlepath (str): bundlepath of the pedalboard

        Returns:
            dict: pedalboard info
        """
        logger.info(f"Getting pedalboard info: {bundlepath}")

        status, pedalboard_info = await self._request(
            method="GET",
            url=f"{self.mod_ui_url}/pedalboard/info/",
            params=f"bundlepath={bundlepath}",
        )

        if not status:
            logger.error(f"Unable to get pedalboard infos for {bundlepath}")

        return pedalboard_info

    async def _list_pedalboards(self) -> dict:
        """Get list of pedalboard using mod-ui API

        Returns:
            dict: Pedalboards
        """
        logger.info("Listing pedalboards")

        status, pedalboards = await self._request(
            method="GET", url=f"{self.mod_ui_url}/pedalboard/list"
        )

        if not status:
            logger.error("Unable to list pedalboards")

        return pedalboards

    async def _get_plugin_info(self, uri: str) -> dict:
        """Get plugin info using mod-ui API

        Args:
            uri (str): URI of the plugin

        Returns:
            dict: Plugin info
        """
        logger.info(f"Getting plugin info: {uri}")

        status, plugin_info = await self._request(
            method="GET", url=f"{self.mod_ui_url}/effect/get", params=f"uri={uri}"
        )

        if not status:
            logger.error(f"Unable to get plugin info for {uri}")

        return plugin_info

    def _check_bypass_parameter(self, control: dict):
        ret = False
        if "bypass" in [
            control.get("name", "").lower(),
            control.get("shortName", "").lower(),
            control.get("symbol", "").lower(),
        ]:
            ret = True
        return ret

    async def _load_plugin(self, plugin: dict):
        if plugin["uri"] in self.plugins:
            self.plugins.get(plugin["uri"]).bypassed = plugin.get("bypassed", False)
            return self.plugins.get(plugin["uri"])

        bypassed = plugin.get("bypassed", False)

        _plugin_info = await self._get_plugin_info(uri=plugin["uri"])
        if not _plugin_info:
            return None

        _plugin_name = _plugin_info.get("name")
        _plugin_uri = _plugin_info.get("uri")
        _plugin_instance = plugin.get("instance")
        _plugin_category = _plugin_info.get("category", [])
        _plugin_label = _plugin_info.get("label", "")
        _plugin_category = _plugin_info.get("category", [])
        _plugin_bundle = _plugin_info.get("bundles", [])
        if len(_plugin_bundle):
            _plugin_bundle = _plugin_bundle[0]

        _controls = _plugin_info.get("ports", {}).get("control", {}).get("input", [])
        plugin_parameters = []
        bypassFound = False
        for control in _controls:

            # handle bypass
            symbol = control.get("symbol")
            ranges = control.get("ranges", {})
            if not bypassFound and self._check_bypass_parameter(control=control):
                symbol = ":bypass"
                ranges["default"] = bypassed
                bypassFound = True

            plugin_parameters.append(
                PluginParameter(
                    index=control.get("index"),
                    name=control.get("name"),
                    symbol=symbol,
                    properties=control.get("properties", []),
                    ranges=ranges,
                    shortName=control.get("shortName", ""),
                    units=control.get("units", {}),
                    scalePoints=control.get("scalePoints", []),
                )
            )

        if not bypassFound:
            plugin_parameters.insert(
                0,
                PluginParameter(
                    index=0,
                    name="bypass",
                    symbol=":bypass",
                    properties=[],
                    ranges={
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": bypassed,
                    },
                    shortName="bypass",
                    units={
                        "_custom": False,
                        "label": "",
                        "render": "",
                        "symbol": "",
                    },
                    scalePoints=[],
                ),
            )

        # add to cache
        pl = Plugin(
            name=_plugin_name,
            bundle=_plugin_bundle,
            category=_plugin_category,
            instance_id=_plugin_instance,
            label=_plugin_label,
            uri=_plugin_uri,
            params=plugin_parameters,
            bypassed=bypassed,
        )

        self.plugins[_plugin_uri] = pl
        return pl

    def _link_plugins(self, connections: list):
        pattern = re.compile(r"(_[^/]+_)")

        graph = defaultdict(set)
        all_nodes = set()

        for conn in connections:
            src = pattern.match(conn["source"])
            dst = pattern.match(conn["target"])

            if src and dst:
                src = src.group(1)
                dst = dst.group(1)
                graph[dst].add(src)  # dst depends on src
                all_nodes.update([src, dst])

        for node in all_nodes:
            graph.setdefault(node, set())

        order = list(TopologicalSorter(graph).static_order())
        return order

    async def _load_pedalboard(self, bundle: str):
        _pedalboard_info = await self._get_pedalboard_info(bundlepath=bundle)
        if not _pedalboard_info:
            return

        # plugins
        plugins = {}
        for plugin in _pedalboard_info.get("plugins", []):
            p = await self._load_plugin(plugin=plugin)
            if p:
                plugins[p.instance_id] = p

        links = self._link_plugins(connections=_pedalboard_info.get("connections", []))
        sorted = []
        for l in links:
            sorted.append(plugins[l])

        self.pedalboards[bundle] = Pedalboard(
            title=_pedalboard_info.get("title"),
            bundle=bundle,
            plugins=sorted,
            snapshots=[],
            snapshot_id=-1,
        )

        return self.pedalboards[bundle]

    async def _load_all_pedalboards(self):
        """Load all pedalboards and their plugin into local cache"""
        _pedalboards = await self._list_pedalboards()
        if _pedalboards is None:
            return

        for pedalboard in _pedalboards:
            if pedalboard.get("broken", False):
                logger.info(f"Pedalboard {pedalboard.get("bundle")} is broken.")
                continue
            await self._load_pedalboard(bundle=pedalboard["bundle"])

    async def _set_pedalboard_snapshots(self, snapshot_id: int = None):
        """Get snapshots for the current pedalboard using mod-ui API"""
        if self.current_pedalboard is None:
            logger.error(f"Unable to get snapshot: no pedalboard selected")
            return

        status, snapshots = await self._request(
            method="GET", url=f"{self.mod_ui_url}/snapshot/list"
        )
        if not status:
            logger.error(
                f"Unable to get snapshot for pedalboard {self.current_pedalboard.bundle}."
            )
            return

        # first, clean all snapshots
        self.current_pedalboard.snapshots = []
        self.current_pedalboard.snapshot_id = -1
        for index, name in snapshots.items():
            self.current_pedalboard.snapshots.append(
                Snapshot(index=int(index), name=name)
            )

        # init with first snapshot if possible
        if len(self.current_pedalboard.snapshots):
            self.current_pedalboard.snapshot_id = 0

        # set based on snapshot_id
        if snapshot_id is not None and snapshot_id <= len(
            self.current_pedalboard.snapshots
        ):
            self.current_pedalboard.snapshot_id = snapshot_id

    async def _set_current_pedalboard(self, bundle: str, snapshot_id: int):
        self.current_pedalboard = await self._load_pedalboard(bundle=bundle)
        await self._set_pedalboard_snapshots(snapshot_id)

    # TODO: update list based on folder
    async def _monitor_pedalboards_folder(self):
        logger.info(
            f"Starting monitoring for pedalboards on folder : {self._pedalboards_folder}"
        )
        while True:
            async for changes in awatch(self._pedalboards_folder):
                for change, path in changes:
                    if path.endswith(".pedalboard"):
                        if change == Change.deleted:
                            logger.info(f"pedalboard folder deleted: {path}")
                        elif change == Change.added:
                            logger.info(f"New pedalboard folder detected: {path}")

    async def run(self):
        logger.info("Starting MOD")

        self._tasks = [
            # asyncio.create_task(self._monitor_pedalboards_folder()),
            asyncio.create_task(self._start()),
        ]
        await asyncio.gather(self._tasks)

    async def stop(self):
        logger.info("Stopping MOD")

        for t in self._tasks:
            t.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _start(self):
        while True:
            try:
                async with websockets.connect(
                    self.mod_ui_ws, logger=logger
                ) as websocket:
                    logger.info("Mod WS Connected")
                    self.ws = websocket

                    # drain
                    flushed = 0
                    while not self.rx_queue.empty():
                        try:
                            self.rx_queue.get_nowait()
                            flushed += 1
                        except self.rx_queue.empty():
                            break
                    if flushed:
                        logger.info(
                            f"Flushed {flushed} stale messages from queue after reconnect"
                        )

                    await self._load_all_pedalboards()

                    rx = asyncio.create_task(self._wsReceiveTask())
                    tx = asyncio.create_task(self._wsSendTask())

                    done, pending = await asyncio.wait(
                        {rx, tx},
                        return_when=asyncio.FIRST_EXCEPTION,
                    )

            except ConnectionRefusedError as error:
                logger.error(f"Unable to connect to MOD. {error}")
            except Exception as error:
                logger.error(f"Error: {error}")

            logger.info(f"Trying to reconnect to Mod")
            await asyncio.sleep(5)

    async def _wsSendTask(self):
        logger.info("WS send task started")
        while True:

            message = await self.tx_queue.get()
            try:
                logger.info(f"TX WS : {message}")
                await self.ws.send(message)

            except websockets.ConnectionClosed:
                logger.error("socker tx")
                raise

    async def _wsReceiveTask(self):
        logger.info("WS receive task started")
        try:
            async for message in self.ws:
                logger.info(f"RX WS : {message}")
                modMessage: ModMessage = parse_message(message)

                if isinstance(modMessage, LoadingEndMessage):
                    if modMessage.pedalboard_bundle == "":
                        continue

                    await self._set_current_pedalboard(
                        bundle=modMessage.pedalboard_bundle,
                        snapshot_id=modMessage.snapshot_id,
                    )
                    self._push_event(
                        EventPedalboardLoaded(
                            pedalboard=asdict(self.current_pedalboard)
                        )
                    )

                elif isinstance(modMessage, ParamSetMessage):
                    for plugin in self.plugins.values():
                        if plugin.instance_id == modMessage.instance:
                            for param in plugin.params:
                                if param.symbol == modMessage.symbol:
                                    param.ranges["default"] = modMessage.value

                                    if modMessage.symbol == ":bypass":
                                        plugin.bypassed = bool(modMessage.value)

                    self._push_event(
                        EventEffectParam(
                            instance_id=modMessage.instance,
                            symbol=modMessage.symbol,
                            value=modMessage.value,
                        )
                    )

                elif isinstance(modMessage, PedalSnapshotMessage):
                    await self._set_pedalboard_snapshots(
                        snapshot_id=modMessage.snapshot_id
                    )
                    self._push_event(
                        EventSnapshotChanged(
                            index=modMessage.snapshot_id, name=modMessage.snapshot_name
                        )
                    )

                elif isinstance(modMessage, DataReadyMessage):
                    self.tx_queue.put_nowait(f"data_ready {modMessage.count}")

                elif isinstance(modMessage, TunerStateMessage):
                    self._push_event(EventTunerState(state=bool(modMessage.state)))

                elif isinstance(modMessage, TunerOutputMessage):
                    self._push_event(
                        EventTunerOutput(
                            freq=modMessage.freq,
                            note=modMessage.note,
                            cents=modMessage.cents,
                        )
                    )

        except websockets.ConnectionClosed:
            logger.info("Receiver disconnected")
            raise
        except Exception as err:
            logger.error(traceback.print_exc())

    async def setEffectParam(self, instance_id, symbol, value):
        try:
            self.tx_queue.put_nowait(f"param_set /graph/{instance_id}/{symbol} {value}")
            if self.current_pedalboard:
                for plugin in self.current_pedalboard.plugins:
                    if plugin.instance_id == instance_id:
                        logger.info(f"Updating plugin {plugin.instance_id}")
                        for param in plugin.params:
                            if param.symbol == symbol:
                                logger.info(f"Updating param {param.name}")
                                param.ranges["default"] = float(value)

        except Exception as err:
            logger.error(err)

    async def setPedalboardSnapshot(self, index: int):
        if (
            index < len(self.current_pedalboard.snapshots)
            and index != self.current_pedalboard.snapshot_id
        ):
            status, response = await self._request(
                method="GET",
                url=f"{self.mod_ui_url}/snapshot/load",
                params=f"id={index}",
            )
            if not status:
                logger.error("Unable to set snapshot")

    async def setPedalboard(self, name) -> Pedalboard:

        # try to find the bundle
        pedalboard = None
        for p in self.pedalboards.values():
            if p.title == name:
                pedalboard = p
                break

        if not pedalboard:
            logger.error(f"Unable to set pedalboard. Pedalboard '{name}' not found")
            return

        status, response = await self._request(
            method="GET", url=f"{self.mod_ui_url}/reset"
        )
        if not status:
            logger.error("Unable to reset pedalboard")
            return

        data = {"bundlepath": pedalboard.bundle}
        status, response = await self._request(
            method="POST", url=f"{self.mod_ui_url}/pedalboard/load_bundle/", data=data
        )
        if not status or not response.get("ok", False):
            logger.error(f"Unable to load pedalboard {pedalboard.bundle}")
            return

        # await self._set_pedalboard_snapshots()

    async def setTunerState(self, state: bool):
        s = "on" if state else "off"
        status, response = await self._request(method="GET", url=f"{self.mod_ui_url}/tuner/{s}")
        if not status:
            logger.error(f"Unable to set tuner state: {s}")
            return