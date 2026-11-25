#!/usr/bin/python3
"""Pet feeder camera: records movement to .mp4 and serves the live view.

Replaces feeder-cam + motion. The Pi Zero's hardware encoder does the video work, so this
records at 15 fps for roughly the CPU that motion needed at 5 fps.

- main stream (640x480) -> H.264, hardware -> 3 s ring buffer -> .mp4 while something moves
- lores stream (160x120) -> movement check five times a second
- main stream -> MJPEG, hardware, every 5th frame -> http://127.0.0.1:8081/ (the app's /live)
"""
import io
import os
import signal
import socketserver
import threading
import time
from http import server

import numpy as np
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder
from picamera2.outputs import CircularOutput2, FileOutput, PyavOutput

VIDEO_DIR = '/var/www/feeder/feeder/static/video'
LIVE_PORT = 8081            # the app's /live page reads this (motion's old stream port)
FRAMERATE = 15
LIVE_EVERY = 5              # live view gets every 5th frame (3 fps)
PRE_SECONDS = 3             # video kept from before the movement started
POST_SECONDS = 13           # recording carries on this long after the last movement; the last
                            # PRE_SECONDS are still in the ring buffer when the file closes, so
                            # clips end about 10 s after the cat stops moving
MAX_SECONDS = 60            # longest single file; a long visit becomes several files
CHECKS_PER_SECOND = 5
WARMUP_SECONDS = 5          # no checks while the camera settles its exposure after starting

# Movement check, on the lores image shrunk to 80x60
PIXEL_CHANGE = 20           # brightness change (0-255) that counts a pixel as changed
CHANGED_PIXELS = 30         # changed pixels (of 4800) that count as movement
MOVING_CHECKS = 2           # consecutive checks needed, so one noisy frame doesn't record
BACKGROUND_RATE = 0.05      # how fast the background follows slow light changes


class FrameBuffer(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class Handler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/stream.mjpg'):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with live.condition:
                    live.condition.wait()
                    frame = live.frame
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Recorder:
    """Opens and closes .mp4 files on the ring buffer. A file is written as .mp4.part
    (which the app ignores) and renamed when it is complete."""

    def __init__(self, circular):
        self.circular = circular
        self.path = None
        self.started = 0

    def start(self):
        self.path = os.path.join(VIDEO_DIR, time.strftime('cam-%Y%m%d%H%M%S.mp4'))
        self.started = time.monotonic()
        self.circular.open_output(PyavOutput(self.path + '.part', format='mp4',
                                             options={'movflags': 'faststart'}))
        print('Recording', os.path.basename(self.path), flush=True)

    def stop(self):
        closing = time.monotonic()
        self.circular.close_output()
        os.rename(self.path + '.part', self.path)
        print('Saved', os.path.basename(self.path),
              f'({os.path.getsize(self.path) // 1024} KiB, recorded for {closing - self.started:.0f} s,'
              f' closing took {time.monotonic() - closing:.1f} s)', flush=True)
        self.path = None

    @property
    def recording(self):
        return self.path is not None


def shrink(lores):
    y = lores[:120, :160].astype(np.float32)          # Y plane of the YUV420 buffer
    return y.reshape(60, 2, 80, 2).mean(axis=(1, 3))  # 80x60, averages out sensor noise


stopping = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stopping.set())
signal.signal(signal.SIGINT, lambda *_: stopping.set())

cam = Picamera2()
cam.configure(cam.create_video_configuration(
    main={'size': (640, 480), 'format': 'YUV420'},
    lores={'size': (160, 120), 'format': 'YUV420'},
    controls={'FrameRate': FRAMERATE}))

circular = CircularOutput2(buffer_duration_ms=PRE_SECONDS * 1000)
cam.start_encoder(H264Encoder(bitrate=1_000_000, iperiod=FRAMERATE), circular, name='main')
live = FrameBuffer()
mjpeg = MJPEGEncoder()
mjpeg.frame_skip_count = LIVE_EVERY
cam.start_encoder(mjpeg, FileOutput(live), name='main')
cam.start()

httpd = Server(('127.0.0.1', LIVE_PORT), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
print(f'Camera running: {FRAMERATE} fps, live view on 127.0.0.1:{LIVE_PORT}', flush=True)

recorder = Recorder(circular)
time.sleep(WARMUP_SECONDS)
background = None
moving_count = 0
last_movement = 0.0
try:
    while not stopping.is_set():
        image = shrink(cam.capture_array('lores'))
        now = time.monotonic()
        if background is None:
            background = image
            continue
        changed = int(np.count_nonzero(np.abs(image - background) > PIXEL_CHANGE))
        background += (image - background) * BACKGROUND_RATE
        moving_count = moving_count + 1 if changed > CHANGED_PIXELS else 0

        if moving_count >= MOVING_CHECKS:
            last_movement = now
            if not recorder.recording:
                print(f'Movement ({changed} pixels changed)', flush=True)
                recorder.start()
        if recorder.recording and (now - last_movement > POST_SECONDS
                                   or now - recorder.started > MAX_SECONDS):
            recorder.stop()  # if it is still moving, the next check starts a new file

        stopping.wait(1 / CHECKS_PER_SECOND)
finally:
    if recorder.recording:
        recorder.stop()
    httpd.shutdown()
    cam.stop_encoder()
    cam.stop()
