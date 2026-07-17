from enum import Enum
from dataclasses import dataclass
from typing import List, Any


class SLCommand(str, Enum):
    RECORD = "record"
    OVERDUB = "overdub"
    MULTIPLY = "multiply"
    INSERT = "insert"
    REPLACE = "replace"
    REVERSE = "reverse"
    MUTE = "mute"
    UNDO = "undo"
    REDO = "redo"
    ONESHOT = "oneshot"
    TRIGGER = "trigger"
    SUBSTITUTE = "substitute"
    UNDO_ALL = "undo_all"
    REDO_ALL = "redo_all"
    MUTE_ON = "mute_on"
    MUTE_OFF = "mute_off"
    SOLO = "solo"
    PAUSE = "pause"
    SOLO_NEXT = "solo_next"
    SOLO_PREV = "solo_prev"
    RECORD_SOLO = "record_solo"
    RECORD_SOLO_NEXT = "record_solo_next"
    RECORD_SOLO_PREV = "record_solo_prev"
    SET_SYNC_POS = "set_sync_pos"
    RESET_SYNC_POS = "reset_sync_pos"


class SLSetControl(Enum):

    REC_THRESH = "rec_thresh"
    FEEDBACK = "feedback"
    DRY = "dry"
    WET = "wet"
    INPUT_GAIN = "input_gain"
    RATE = "rate"
    SCRATCH_POS = "scratch_pos"
    DELAY_TRIGGER = "delay_trigger"
    QUANTIZE = "quantize"
    ROUND = "round"
    REDO_IS_TAP = "redo_is_tap"
    SYNC = "sync"
    PLAYBACK_SYNC = "playback_sync"
    USE_RATE = "use_rate"
    FADE_SAMPLES = "fade_samples"
    USE_FEEDBACK_PLAY = "use_feedback_play"
    USE_COMMON_INS = "use_common_ins"
    USE_COMMON_OUTS = "use_common_outs"
    RELATIVE_SYNC = "relative_sync"
    USE_SAFETY_FEEDBACK = "use_safety_feedback"
    PAN_1 = "pan_1"
    PAN_2 = "pan_2"
    PAN_3 = "pan_3"
    PAN_4 = "pan_4"
    INPUT_LATENCY = "input_latency"
    OUTPUT_LATENCY = "output_latency"
    TRIGGER_LATENCY = "trigger_latency"
    AUTOSET_LATENCY = "autoset_latency"
    MUTE_QUANTIZED = "mute_quantized"
    OVERDUB_QUANTIZED = "overdub_quantized"
    DISCRETE_PREFADER = "discrete_prefader"
    SELECTED_LOOP_NUM = "selected_loop_num"

    @property
    def name(self) -> str:
        return self.value


class SLGetControl(Enum):
    STATE = "state"
    NEXT_STATE = "next_state"
    LOOP_LEN = "loop_len"
    LOOP_POS = "loop_pos"
    CYCLE_LEN = "cycle_len"
    FREE_TIME = "free_time"
    TOTAL_TIME = "total_time"
    RATE_OUTPUT = "rate_output"
    IN_PEAK_METER = "in_peak_meter"
    OUT_PEAK_METER = "out_peak_meter"
    IS_SOLOED = "is_soloed"
    @property
    def name(self) -> str:
        return self.value


@dataclass
class OSCMessage():
    address: str
    value: List[Any]
