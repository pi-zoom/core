import logging
import asyncio
import aiofiles
import re
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import alsaaudio
import select

logger = logging.getLogger("alsa")

def list_cards():
    print("Available sound cards:")
    for i in alsaaudio.card_indexes():
        (name, longname) = alsaaudio.card_name(i)
        print("  %d: %s (%s)" % (i, name, longname))


def list_mixers(kwargs):
    print("Available mixer controls:")
    for m in alsaaudio.mixers(**kwargs):
        print("  '%s'" % m)

def show_mixer(name, kwargs):
    # Demonstrates how mixer settings are queried.
    try:
        mixer = alsaaudio.Mixer(name, **kwargs)
    except alsaaudio.ALSAAudioError:
        print("No such mixer", file=sys.stderr)
        sys.exit(1)

    print("Mixer name: '%s'" % mixer.mixer())
    volcap = mixer.volumecap()
    print("Capabilities: %s %s" % (' '.join(volcap),
                                   ' '.join(mixer.switchcap())))

    if "Volume" in volcap or "Joined Volume" in volcap or "Playback Volume" in volcap:
        pmin, pmax = mixer.getrange(alsaaudio.PCM_PLAYBACK)
        pmin_keyword, pmax_keyword = mixer.getrange(pcmtype=alsaaudio.PCM_PLAYBACK, units=alsaaudio.VOLUME_UNITS_RAW)
        pmin_default, pmax_default = mixer.getrange()
        assert pmin == pmin_keyword
        assert pmax == pmax_keyword
        assert pmin == pmin_default
        assert pmax == pmax_default
        print("Raw playback volume range {}-{}".format(pmin, pmax))
        pmin_dB, pmax_dB = mixer.getrange(units=alsaaudio.VOLUME_UNITS_DB)
        print("dB playback volume range {}-{}".format(pmin_dB / 100.0, pmax_dB / 100.0))

    if "Capture Volume" in volcap or "Joined Capture Volume" in volcap:
        # Check that `getrange` works with keyword and positional arguments
        cmin, cmax = mixer.getrange(alsaaudio.PCM_CAPTURE)
        cmin_keyword, cmax_keyword = mixer.getrange(pcmtype=alsaaudio.PCM_CAPTURE, units=alsaaudio.VOLUME_UNITS_RAW)
        assert cmin == cmin_keyword
        assert cmax == cmax_keyword
        print("Raw capture volume range {}-{}".format(cmin, cmax))
        cmin_dB, cmax_dB = mixer.getrange(pcmtype=alsaaudio.PCM_CAPTURE, units=alsaaudio.VOLUME_UNITS_DB)
        print("dB capture volume range {}-{}".format(cmin_dB / 100.0, cmax_dB / 100.0))

    volumes = mixer.getvolume()
    volumes_dB = mixer.getvolume(units=alsaaudio.VOLUME_UNITS_DB)
    for i in range(len(volumes)):
        print("Channel %i playback volume: %i%% (%.1f dB)" % (i, volumes[i], volumes_dB[i] / 100.0))

    volumes = mixer.getvolume(pcmtype=alsaaudio.PCM_CAPTURE)
    volumes_dB = mixer.getvolume(pcmtype=alsaaudio.PCM_CAPTURE, units=alsaaudio.VOLUME_UNITS_DB)
    for i in range(len(volumes)):
        print("Channel %i capture volume: %i%% (%.1f dB)" % (i, volumes[i], volumes_dB[i] / 100.0))

    try:
        mutes = mixer.getmute()
        for i in range(len(mutes)):
            if mutes[i]:
                print("Channel %i is muted" % i)
    except alsaaudio.ALSAAudioError:
        # May not support muting
        pass

    try:
        recs = mixer.getrec()
        for i in range(len(recs)):
            if recs[i]:
                print("Channel %i is recording" % i)
    except alsaaudio.ALSAAudioError:
        # May not support recording
        pass


class PollDescriptor(object):
	'''File Descriptor, event mask and a name for logging'''
	def __init__(self, name, fd, mask):
		self.name = name
		self.fd = fd
		self.mask = mask

	def as_tuple(self):
		return (self.fd, self.mask)

	@classmethod
	def from_alsa_object(cls, name, alsaobject, mask=None):
		# TODO maybe refactor: we ignore objects that have more then one polldescriptor
		fd, alsamask = alsaobject.polldescriptors()[0]

		if mask is None:
			mask = alsamask

		return cls(name, fd, mask)

# for i in alsaaudio.card_indexes():
#     (name, longname) = alsaaudio.card_name(i)
#     print("%d: %s (%s)" % (i, name, longname))

#     for m in alsaaudio.mixers(cardindex=i):
#         print("  '%s'" % m)

#         show_mixer(m, {"cardindex": i})
#     print()
mixer = alsaaudio.Mixer(control="Master", cardindex=1)

def handler(fd, ev, name):
    v = mixer.getvolume(units=alsaaudio.VOLUME_UNITS_DB)
    print(f"{ev} {name}: volume: {v}")
    pass

poll = select.poll()
descriptors = {}

pd = PollDescriptor.from_alsa_object(name=mixer.mixer(), alsaobject=mixer)
descriptors[pd.fd] = (pd, handler)
poll.register(pd.fd, select.POLLIN)

for fd, mask in mixer.polldescriptors():
    print(f"{fd} {mask}")
print("Poll")
while True:
    events = poll.poll(0.25)
    for fd, ev in events:
        pd, h = descriptors[fd]
        h(fd, ev, pd.name)

    mixer.handleevents()