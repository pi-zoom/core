from dataclasses import dataclass
from abc import ABC
from enum import Enum
# @dataclass
# class Event(ABC):
#     pass

class Event(Enum):
    EVENT_LOOPER_ADD_LOOP = "looper_add_loop"
    EVENT_LOOPER_REMOVE_LOOP = "looper_remove_loop"
    EVENT_LOOPER_SELECT_LOOP = "looper_select_loop"
    EVENT_LOOPER_LIST_LOOPS = "looper_list_loops"
    EVENT_LOOPER_LOOPS_COUNT = "looper_loops_count"
    EVENT_LOOPER_LOOP_LEN = "looper_loop_len"
    EVENT_LOOPER_LOOP_POS = "looper_loop_pos"
    EVENT_LOOPER_LOOP_STATE = "looper_loop_state"

    EVENT_MOD_SELECT_PEDALBOARD = "mod_select_pedalboard"
    EVENT_MOD_SET_EFFECT_PARAM = "mod_set_param"
    EVENT_MOD_LIST_PEDALBOARDS = "mod_list_pedalboards"
    EVENT_MOD_SELECT_SNAPSHOT = "mod_select_snapshot"

    EVENT_SEQUENCER_LIST_MIDI_FILES = "sequencer_list_files"
    EVENT_SEQUENCER_POS = "sequencer_pos"

    EVENT_PLAYER_SET_STATE = "player_state"
    EVENT_PLAYER_LIST_FILES = "player_list_files"

@dataclass
class EventLoopsList:
    loops: list
    selected: int

@dataclass
class EventLoopCount:
    count: int

@dataclass
class EventLoopSelected:
    id: int

@dataclass
class EventLoopLen:
    id: int
    len: float

@dataclass
class EventLoopState:
    id: int
    state: int

@dataclass
class EventLoopPos:
    id: int
    pos: float

@dataclass
class UILoopSelectedEvent:
    id: int

@dataclass
class UILoopAddEvent:
    pass

@dataclass
class UILoopDelEvent:
    pass

@dataclass
class UILoopSelectedEvent:
    id: int

@dataclass
class UIPedalboardSelectedEvent:
    pname: str

@dataclass
class EventPedalboardList:
    pedalboards: list[str]

@dataclass
class EventPedalboardLoading:
    pass

@dataclass
class EventPedalboardLoaded:
    pedalboard: dict

@dataclass
class EventEffectParam:
    instance_id: str
    symbol: str
    value: float

@dataclass
class EventSnapshotChanged:
    index: int
    name: str

@dataclass
class EventSequencerMidiFilesList:
    midiFiles: list[str]

@dataclass
class EventSequencerPos:
    pos: float

@dataclass
class EventTuner:
    note: str
    cents: float

@dataclass
class EventPlayerFilesList:
    files: list

@dataclass
class EventPlayerState:
    state: int
