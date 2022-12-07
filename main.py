#!/usr/bin/python

import sys, os
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if not path in sys.path:
    sys.path.insert(1, path)

print("path: {}".format(sys.path))
# LED imports
import time

from gpiozero import LED
import numpy as np
# # Initalize LEDS
# power = LED(5)
# power.on()


import pyaudio
import _thread
from time import sleep
from array import array
import RPi.GPIO as GPIO
import time
import requests
import wave

import apa102
import time
import threading
import random

try:
    import queue as Queue
except ImportError:
    import Queue as Queue

class Pixels:
    PIXELS_N = 3

    def __init__(self):
        self.basis = [0] * 3 * self.PIXELS_N
        self.basis[0] = 2
        self.basis[3] = 1
        self.basis[4] = 1
        self.basis[7] = 2

        self.colors = [0] * 3 * self.PIXELS_N
        self.dev = apa102.APA102(num_led=self.PIXELS_N)

        self.next = threading.Event()
        self.queue = Queue.Queue()
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()

    def wakeup(self, direction=0):
        def f():
            self._wakeup(direction)

        self.next.set()
        self.queue.put(f)

    def listen(self):
        self.next.set()
        self.queue.put(self._listen)

    def think(self):
        self.next.set()
        self.queue.put(self._think)

    def speak(self):
        self.next.set()
        self.queue.put(self._speak)

    def off(self):
        self.next.set()
        self.queue.put(self._off)

    def _run(self):
        while True:
            func = self.queue.get()
            func()

    def _wakeup(self, direction=0):
        for i in range(1, 25):
            colors = [i * v for v in self.basis]
            self.write(colors)
            time.sleep(0.01)

        self.colors = colors

    def _listen(self):
        for i in range(1, 25):
            colors = [i * v for v in self.basis]
            self.write(colors)
            time.sleep(0.01)

        self.colors = colors

    def _think(self):
        colors = self.colors

        self.next.clear()
        while not self.next.is_set():
            colors = colors[3:] + colors[:3]
            self.write(colors)
            time.sleep(0.2)

        t = 0.1
        for i in range(0, 5):
            colors = colors[3:] + colors[:3]
            self.write([(v * (4 - i) / 4) for v in colors])
            time.sleep(t)
            t /= 2

        # time.sleep(0.5)

        self.colors = colors

    def _speak(self):
        colors = self.colors
        gradient = -1
        position = 24

        self.next.clear()
        while not self.next.is_set():
            position += gradient
            self.write([(v * position / 24) for v in colors])

            if position == 24 or position == 4:
                gradient = -gradient
                time.sleep(0.2)
            else:
                time.sleep(0.01)

        while position > 0:
            position -= 1
            self.write([(v * position / 24) for v in colors])
            time.sleep(0.01)

        # self._off()

    def _off(self):
        self.write([0] * 3 * self.PIXELS_N)

    def write(self, colors):
        for i in range(self.PIXELS_N):
            self.dev.set_pixel(i, int(colors[3*i]), int(colors[3*i + 1]), int(colors[3*i + 2]))

        self.dev.show()

clap = 0
wait = 2
flag = 0
pin = 24
exitFlag = False   
playSound = 0

def main():
    global clap
    global flag
    global pin
    global playSound

    pixels = Pixels()

    pixels.wakeup()
    time.sleep(3)
    pixels.off()

    chunk = 1024
    RESPEAKER_WIDTH = 2
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    max_threshold = 4000
    corr_threshold = 8e8
    max_value = 0

    audioList = ['audio1.wav', 'audio2.wav', 'audio3.wav', 'audio4.wav']

    audio1 = wave.open('/home/pi/rpi-clapper/audio1.wav', 'rb')

    p = pyaudio.PyAudio()
    input_stream = p.open(format=FORMAT,
             channels=CHANNELS, 
             rate=RATE, 
             input=True,
             output=False,
             frames_per_buffer=chunk)    
    output_stream = p.open(format = p.get_format_from_width(audio1.getsampwidth()),
            channels = audio1.getnchannels(),
            rate = audio1.getframerate(),
            output = True,
            input=False)

    # Load the reference wave form. All clappiness is determined in relation to this clap
    sample_waveform = np.array(np.load("/home/pi/rpi-clapper/golden_clap.npy"), dtype=np.float)
    sw_fft = np.fft.fft(sample_waveform) # Now you're cooking with gas

    print ("Clap detection initialized")
    c = 0
    last_intensity = 0
    last_time = time.time()
    while True:
        if playSound:
            pixels.wakeup()
            input_stream.stop_stream()
            output_stream.start_stream()
            wf = wave.open('/home/pi/rpi-clapper/' + random.choice(audioList), 'rb')
            # read data (based on the chunk size)
            output_data = wf.readframes(chunk)
            # play stream (looping from beginning of file to the end)
            while output_data:
                # writing to the stream is what *actually* plays the sound.
                output_stream.write(output_data)
                output_data = wf.readframes(chunk)
            input_stream.start_stream()
            output_stream.stop_stream()
            playSound = 0
            wf.close()
            pixels.off()
        data = input_stream.read(chunk)
        as_ints = array('h', data)
        max_value = max(as_ints)
        # print("max: {}, time = {}".format(max_value, time.time()))
        if max_value > max_threshold and max_value >= last_intensity: 
            as_float = np.array(as_ints, dtype=np.float)

            # Measure loudness
            mag = np.sum(as_float**2)

            #Measure clappiness
            corr = np.abs(np.fft.ifft(np.fft.fft(as_float)*sw_fft))**2/mag
            corr_value = np.max(corr)
            if corr_value > corr_threshold:
                #np.save("hand_clap" + str(c) + ".npy", as_ints) # save 
                #print("saving {}".format(c))
                now = time.time()
                if (now > last_time + 0.2): #better debounce (prevent samples from being stuck in fifo
                    print("corr: {}, max: {}, claps: {}".format(corr_value, max_value, clap))
                    clap += 1
                    last_time = now
                    print("Clapped")
        
        if clap > 1:
            playSound = 1
            clap = 0

        if exitFlag:
            sys.exit(0)
        last_intensity = max_value 

if __name__ == '__main__':
    main()
