from dataclasses import dataclass

@dataclass
class CmdListLoops():
    pass

@dataclass
class CmdAddLoop():
    pass

@dataclass
class CmdRemoveLoop():
    pass

@dataclass
class CmdSelectLoop():
    id: int

@dataclass
class CmdListPedalboards():
    pass

@dataclass
class CmdSelectPedalboard():
    name: str

@dataclass
class CmdSetEffectParam():
    instance_id: str
    symbol: str
    value: float

@dataclass
class CmdSelectPedalboardSnapshot():
    index: int

@dataclass
class CmdSequencerSetBpm():
    bpm: int

@dataclass
class CmdSequencerSetVolume():
    volume: int

@dataclass
class CmdSequencerSelectMidiFile():
    file: str

@dataclass
class CmdSequencerListMidiFiles():
    pass

@dataclass
class CmdSequencerState():
    state: bool

@dataclass
class CmdSequencerMute():
    mute: bool

@dataclass
class CmdTuner():
    state: bool

@dataclass
class CmdPlayerRecord():
    state: bool

@dataclass
class CmdPlayerPlay():
    state: bool
    file: str

@dataclass
class CmdPlayerListFiles():
    pass
