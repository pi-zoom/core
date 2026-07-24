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
)
from watchfiles import Change, awatch

logger = logging.getLogger("mod")
logger.setLevel(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.ERROR)
# logging.getLogger("watchfiles.main").setLevel(logging.ERROR)


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


@dataclass
class Snapshot:
    index: int
    name: str


@dataclass
class Pedalboard:
    title: str
    bundle: str
    uri: str
    plugins: list[Plugin]
    snapshots: list[Snapshot]
    snapshot_id: int


class Mod:
    def __init__(
        self,
        host: str,
        port: int,
        queue: asyncio.Queue,
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

        self.queue = queue
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

        self._data_path = Path("/home/marius/wks/git/guitare/mod-ui/data/")
        self._last_pedalboard_path = Path(self._data_path, "last.json")
        self._pedalboards_folder = "/home/pedal/.pedalboards"
        self._current_pedalboard_name = None
        self._current_pedalboard_bundle = None

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
            self.queue.put_nowait(event)
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

    # async def _load_plugin_parameter(self):

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
        # check on cache
        if plugin["uri"] in self.plugins:
            return self.plugins.get(plugin["uri"])

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
                ranges["default"] = plugin["bypassed"]
                bypassFound = True

            # for x in plugin["ports"]:
            #     if x["symbol"] == symbol:
            #         print("Updating value using pedalboard info")
            #         ranges["default"] = x["value"]

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
                        "default": plugin["bypassed"],
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
        )

        self.plugins[_plugin_uri] = pl
        return pl

    async def _load_pedalboard(self, bundle: str, title: str, uri: str):
        # # check on cache
        # if pedalboard["bundle"] in self.pedalboards:
        #     continue

        _pedalboard_info = await self._get_pedalboard_info(bundlepath=bundle)

        if not _pedalboard_info:
            return

        # plugins
        plugins = []
        for plugin in _pedalboard_info.get("plugins", []):
            p = await self._load_plugin(plugin=plugin)
            if p:
                plugins.append(p)

        # add to cache
        self.pedalboards[bundle] = Pedalboard(
            title=title,
            bundle=bundle,
            uri=uri,
            plugins=plugins,
            snapshots=[],
            snapshot_id=-1,
        )

        print(self.pedalboards.keys())

    async def _load_all_pedalboards(self):
        """Load all pedalboards and their plugin into local cache"""
        _pedalboards = await self._list_pedalboards()
        if _pedalboards is None:
            return

        for pedalboard in _pedalboards:
            await self._load_pedalboard(
                bundle=pedalboard["bundle"],
                title=pedalboard["title"],
                uri=pedalboard["uri"],
            )

    def _get_current_pedalboard(self):
        """Read data/last.json file to get current pedalboard"""

        try:
            if not self._last_pedalboard_path.exists():
                logger.warning(f"{self._last_pedalboard_path} not found")
                return

            if not self._last_pedalboard_path.is_file():
                logger.warning(f"{self._last_pedalboard_path} is not a file")
                return

            with open(self._last_pedalboard_path, "r") as file:
                pedalboard = json.load(file).get("pedalboard", "")
                if pedalboard == "":
                    logger.warning("Pedalboard is ''")
                    return

                self._current_pedalboard_bundle = pedalboard
                # self._current_pedalboard_name = os.path.basename(pedalboard).replace(
                #     ".pedalboard", ""
                # )
                self._current_pedalboard_name = self._current_pedalboard_bundle
                logger.info(
                    f"Current pedal board: {self._current_pedalboard_name} {self._current_pedalboard_bundle}"
                )

        except Exception as error:
            logger.error(f"Unable to read current pedalboard file. Error: {error}")

    async def _get_pedalboard_snapshots(self):
        """Get snapshots for the current pedalboard using mod-ui API"""

        if not self._current_pedalboard_name:
            logger.error(f"Unable to get snapshot: no pedalboard selected")
            return

        status, snapshots = await self._request(
            method="GET", url=f"{self.mod_ui_url}/snapshot/list"
        )
        if not status:
            logger.error(
                f"Unable to get snapshot for pedalboard {self._current_pedalboard_name}."
            )
            return

        # first, clean all snapshots
        self.pedalboards[self._current_pedalboard_name].snapshots = []
        self.pedalboards[self._current_pedalboard_name].snapshot_id = -1
        for index, name in snapshots.items():
            self.pedalboards[self._current_pedalboard_name].snapshots.append(
                Snapshot(index=int(index), name=name)
            )
        # select first one
        if len(self.pedalboards[self._current_pedalboard_name].snapshots):
            self.pedalboards[self._current_pedalboard_name].snapshot_id = 0

    async def _monitor_last_pedalboard_file(self):
        """Monitor data/last.json file to detect new pedalboard used"""

        logger.info(
            f"Starting monitoring last pedalboard file: {self._last_pedalboard_path}"
        )
        while True:
            async for changes in awatch(self._data_path):
                for change, path in changes:
                    if change is Change.added and Path(path) == Path(
                        self._last_pedalboard_path
                    ):
                        try:
                            self._get_current_pedalboard()
                            # TODO: reload if required
                            if self._current_pedalboard_bundle not in self.pedalboards:
                                await self._load_all_pedalboards()
                            else:
                                p = self.pedalboards[self._current_pedalboard_bundle]
                                await self._load_pedalboard(
                                    bundle=p.bundle, title=p.title, uri=p.uri
                                )

                            await self._get_pedalboard_snapshots()
                            self._push_event(
                                EventPedalboardLoaded(
                                    pedalboard=asdict(
                                        self.pedalboards[self._current_pedalboard_name]
                                    )
                                )
                            )
                            break
                        except Exception as err:
                            logger.error(
                                f"Unable to read file: { traceback.print_exc()}"
                            )

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

        # first, init everything
        try:
            await self._load_all_pedalboards()
            self._get_current_pedalboard()
            await self._get_pedalboard_snapshots()
        except Exception as err:
            logger.error(f"okokok {err}")

        if self._current_pedalboard_name not in self.pedalboards:
            logger.warning(
                f"Current pedalboard {self._current_pedalboard_name} not found in pedalboards list. Must reset"
            )

        self._tasks = [
            asyncio.create_task(self._monitor_last_pedalboard_file()),
            asyncio.create_task(self._monitor_pedalboards_folder()),
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
        try:
            async with websockets.connect(self.mod_ui_ws, logger=logger) as websocket:
                logger.info("WS Connected")
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

                rx = asyncio.create_task(self._wsReceiveTask())
                tx = asyncio.create_task(self._wsSendTask())

                done, pending = await asyncio.wait(
                    {rx, tx},
                    return_when=asyncio.FIRST_EXCEPTION,
                )
        except Exception as error:
            logger.error(f"Error in global. Error: {error}")

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

                event = None
                if message.startswith("param_set"):
                    s = message.split(" ")
                    instance_id = s[1].replace("/graph/", "")
                    symbol = s[2]
                    value = s[3]

                    if self._current_pedalboard_name:
                        pedalboard = self.pedalboards.get(
                            self._current_pedalboard_name, None
                        )
                        if not pedalboard:
                            logger.error(
                                f"Pedalboard {self._current_pedalboard_name} not found"
                            )
                            continue

                        for plugin in pedalboard.plugins:
                            if plugin.instance_id == instance_id:
                                for param in plugin.params:
                                    if param.symbol == symbol:
                                        param.ranges["default"] = float(value)

                        event = EventEffectParam(
                            instance_id=instance_id,
                            symbol=symbol,
                            value=float(value),
                        )

                elif message.startswith("pedal_snapshot"):
                    s = message.split(" ")
                    index = s[1]
                    name = s[2]
                    logger.info(f"Snapshot changed: name:{name} id:{index}")
                    self.pedalboards[self._current_pedalboard_name].snapshot_id = int(
                        index
                    )
                    self._push_event(EventSnapshotChanged(index=int(index), name=name))

                elif message.startswith("loading_start"):
                    pass
                elif message.startswith("loading_end"):
                    pass
                elif message == "ping":
                    self.tx_queue.put_nowait("pong")

                if event:
                    self._push_event(event)

        except websockets.ConnectionClosed:
            logger.info("Receiver disconnected")
        except Exception as err:
            logger.error(err)

    async def setEffectParam(self, instance_id, symbol, value):
        try:
            self.tx_queue.put_nowait(f"param_set /graph/{instance_id}/{symbol} {value}")
            if self._current_pedalboard_name:
                pedalboard = self.pedalboards.get(self._current_pedalboard_name, None)
                if not pedalboard:
                    logger.error(
                        f"Pedalboard {self._current_pedalboard_name} not found"
                    )
                    return

                for plugin in pedalboard.plugins:
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
            index < len(self.pedalboards[self._current_pedalboard_name].snapshots)
            and index != self.pedalboards[self._current_pedalboard_name].snapshot_id
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

        await self._get_pedalboard_snapshots()
