from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

class UIMessageType(Enum):
    LOOP_COUNT = 0
    LOOP_POS = 1
    MOD = 2


@dataclass
class UIMessage(ABC):
    type: UIMessageType
    payload: Any

class LoopCountMessage(UIMessage):
    type = UIMessageType.LOOP_COUNT

class LoopPosMessage(UIMessage):
    type = UIMessageType.LOOP_POS