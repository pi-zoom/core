from dataclasses import dataclass
from abc import ABC

@dataclass
class Event(ABC):
    pass

@dataclass
class EventLoopsList(Event):
    loops: list
    selected: int

@dataclass
class EventLoopCount(Event):
    count: int

@dataclass
class EventLoopSelected(Event):
    id: int

@dataclass
class EventLoopLen(Event):
    id: int
    len: float

@dataclass
class EventLoopState(Event):
    id: int
    state: int

@dataclass
class EventLoopPos(Event):
    id: int
    pos: float

@dataclass
class UILoopSelectedEvent(Event):
    id: int

@dataclass
class UILoopAddEvent(Event):
    pass

@dataclass
class UILoopDelEvent(Event):
    pass

@dataclass
class UILoopSelectedEvent(Event):
    id: int

@dataclass
class UIPedalboardSelectedEvent(Event):
    pname: str

@dataclass
class EventPedalboardList(Event):
    pedalboards: list[str]

@dataclass
class EventPedalboardLoading(Event):
    pass

@dataclass
class EventPedalboardLoaded(Event):
    pedalboard: dict

@dataclass
class EventEffectParam(Event):
    instance_id: str
    symbol: str
    value: float

@dataclass
class EventSnapshotChanged(Event):
    index: int
    name: str

@dataclass
class EventSequencerMidiFilesList(Event):
    midiFiles: list[str]

@dataclass
class EventSequencerPos(Event):
    pos: float

@dataclass
class EventTuner(Event):
    note: str
    cents: float

@dataclass
class EventRecordedFilesList(Event):
    files: list[str]

@dataclass
class EventRecorderPlaying(Event):
    file: str

@dataclass
class EventRecorderRecording(Event):
    start: int

@dataclass
class EventRecorderStopped(Event):
    pass