#!/usr/bin/env python3

import asyncio
import jack
import logging
import aubio
import numpy as np
from collections import deque
from events import *

logger = logging.getLogger("tuner")
logger.setLevel(level=logging.DEBUG)


class Tuner:
    def __init__(self, queue: asyncio.Queue):
        logger.info("Init tuner")
        self.sample_rate = 48000
        self.buffer_size = 2048
        self.hop_size = 256
        self.display_threshold_cents = 2.0
        self.client = None
        self.input_port = None
        self.running = False
        self.queue: asyncio.Queue = queue
        self.loop: asyncio.AbstractEventLoop = None
        self.t: list[asyncio.Task] = []

        self.pitch_detector = None
        self.latest_pitch = 0.0
        self.latest_confidence = 0.0
        self.pitch_history = deque(maxlen=5)
        self.last_note = None
        self.last_cents = None
        self.updated_event = asyncio.Event()

    def _init_jack(self):
        self.client = jack.Client("tuner")
        self.input_port = self.client.inports.register("input")
        self.client.set_process_callback(self._process)
        # self.client.connect("system:capture_1", "tuner:input")

    def _init_detector(self):
        self.pitch_detector = aubio.pitch(
            "yin", self.buffer_size, self.hop_size, self.sample_rate
        )
        self.pitch_detector.set_unit("Hz")
        self.pitch_detector.set_silence(-40)
        self.latest_pitch = 0.0
        self.latest_confidence = 0.0

    def _note_from_frequency(self, freq):
        if freq <= 0:
            return None, 0

        midi = 69 + 12 * np.log2(freq / 440.0)
        note_number = round(midi)
        cents = (midi - note_number) * 100
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        octave = note_number // 12 - 1
        return f"{names[note_number % 12]}{octave}", cents

    def _process(self, frames):

        audio = self.input_port.get_array()
        samples = np.array(audio[: self.hop_size], dtype=np.float32)

        freq = self.pitch_detector(samples)[0]
        confidence = self.pitch_detector.get_confidence()

        if freq <= 0 or confidence < 0.8:
            return

        note, cents = self._note_from_frequency(freq)

        changed = (
            self.last_note != note or
            self.last_cents is None or
            abs(cents - self.last_cents) > 2
        )

        if changed:
            print(f"{note} {cents} {confidence}")

            self.last_note = note
            self.last_cents = cents
            self.loop.call_soon_threadsafe(self.updated_event.set)

    async def send(self):
        while True:
            await self.updated_event.wait()
            self.updated_event.clear()
            print("ok")
            event = EventTuner(
                note=self.last_note,
                cents=float(self.last_cents),
            )
            self.queue.put_nowait(event)

    async def start(self, loop):

        if not self.running:
            self.loop = loop
            self._init_jack()
            self._init_detector()

            self.t.append(asyncio.create_task(self.send()))
            self.running = True
            self.client.activate()
            self.client.connect("system:capture_1", "tuner:input")
            print("Tuner started")

    async def stop(self):

        if self.running:
            self.running = False
            self.client.deactivate()
            self.client.close()
            for t in self.t:
                t.cancel()

            print("Tuner stopped")


