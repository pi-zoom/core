from dataclasses import dataclass
from enum import Enum

class Command(Enum):
    CMD_LOOPER_ADD_LOOP = "looper_add_loop"
    CMD_LOOPER_REMOVE_LOOP = "looper_remove_loop"
    CMD_LOOPER_SELECT_LOOP = "looper_select_loop"
    CMD_LOOPER_LIST_LOOPS = "looper_list_loops"
    CMD_LOOPER_SET_LOOP_VOLUME = "looper_loop_volume"

    CMD_MOD_SELECT_PEDALBOARD = "mod_select_pedalboard"
    CMD_MOD_SET_EFFECT_PARAM = "mod_set_param"
    CMD_MOD_LIST_PEDALBOARDS = "mod_list_pedalboards"
    CMD_MOD_SELECT_SNAPSHOT = "mod_select_snapshot"

    CMD_SEQUENCER_SET_BPM = "sequencer_set_bpm"
    CMD_SEQUENCER_SET_VOLUME = "sequencer_set_volume"
    CMD_SEQUENCER_SELECT_MIDI_FILE = "sequencer_select_file"
    CMD_SEQUENCER_LIST_MIDI_FILES = "sequencer_list_files"
    CMD_SEQUENCER_PLAY = "sequencer_play"
    CMD_SEQUENCER_MUTE = "sequencer_mute"

    CMD_PLAYER_SET_STATE = "player_state"
    CMD_PLAYER_LIST_FILES = "player_list_files"

    CMD_TUNER_STATE = "tuner_state"


@dataclass
class CmdListLoops:
    pass


@dataclass
class CmdAddLoop:
    pass


@dataclass
class CmdRemoveLoop:
    pass


@dataclass
class CmdSelectLoop:
    id: int


@dataclass
class CmdLooperSetLoopVolume:
    id: int
    volume: float


@dataclass
class CmdListPedalboards:
    pass


@dataclass
class CmdSelectPedalboard:
    name: str


@dataclass
class CmdSetEffectParam:
    instance_id: str
    symbol: str
    value: float


@dataclass
class CmdSelectPedalboardSnapshot:
    index: int


@dataclass
class CmdSequencerSetBpm:
    bpm: int


@dataclass
class CmdSequencerSetVolume:
    volume: int


@dataclass
class CmdSequencerSelectMidiFile:
    file: str


@dataclass
class CmdSequencerListMidiFiles:
    pass


@dataclass
class CmdSequencerPlay:
    state: bool


@dataclass
class CmdSequencerMute:
    mute: bool


@dataclass
class CmdTunerState:
    state: bool


@dataclass
class CmdPlayerState:
    state: int
    file: str

@dataclass
class CmdPlayerListFiles:
    pass
