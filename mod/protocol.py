from dataclasses import dataclass
from typing import Union

@dataclass
class LoadingStartMessage:
    is_default: bool

@dataclass
class LoadingEndMessage:
    snapshot_id: int
    pedalboard_bundle: str

@dataclass
class ParamSetMessage:
    instance: str
    symbol: str
    value: float

@dataclass
class StatsMessage:
    cpu_load: float
    xruns: int

@dataclass
class SysStatsMessage:
    mem_load: float
    cpu_freq: float
    cpu_temp: float

@dataclass
class PingMessage:
    pass

@dataclass
class PedalSnapshotMessage:
    snapshot_id: int
    snapshot_name: str

# Union of all message types
ModMessage = Union[
    LoadingStartMessage,
    LoadingEndMessage,
    ParamSetMessage,
    StatsMessage,
    SysStatsMessage,
    PedalSnapshotMessage
]

def parse_message(message: str) -> ModMessage:
    try:
        s = message.split(" ")
        match s:
            # Format: loading_start {isDefault}
            case ["loading_start", flag]:
                return LoadingStartMessage(is_default=bool(int(flag)))
            case ["loading_start"]:
                return LoadingStartMessage(is_default=False)

            # Format: loading_end {snapshotId}
            case ["loading_end", snapshot_id, pedalboard_bundle]:
                return LoadingEndMessage(snapshot_id=int(snapshot_id), pedalboard_bundle=pedalboard_bundle)
            case ["loading_end"]:
                return LoadingEndMessage(snapshot_id=0, pedalboard_bundle="")

            case ["param_set", path, symbol, value]:
                instance = path.removeprefix("/graph/")
                return ParamSetMessage(instance=instance, symbol=symbol, value=float(value))

            case ["stats", cpu_load, xruns]:
                return StatsMessage(cpu_load=cpu_load, xruns=xruns)

            case ["sys_stats", mem_load, cpu_freq, cpu_temp]:
                return SysStatsMessage(mem_load=mem_load, cpu_freq=cpu_freq, cpu_temp=cpu_temp)

            case ["ping"]:
                return PingMessage()

            case ["pedal_snapshot", snapshot_id, snapshot_name]:
                return PedalSnapshotMessage(snapshot_id=int(snapshot_id), snapshot_name=snapshot_name)

            case ["pedal_snapshot", snapshot_id]:
                return PedalSnapshotMessage(snapshot_id=int(snapshot_id), snapshot_name="")

            case ["pedal_snapshot"]:
                return PedalSnapshotMessage(snapshot_id=0, snapshot_name="")

    except Exception as error:
        print(error)

    pass

