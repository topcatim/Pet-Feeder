#!/usr/bin/python3
"""MJPEG stream of the Pi camera on 127.0.0.1:8090 for motion's netcam_url.

motion cannot use the camera directly on 32-bit Trixie (libcamera's V4L2 compat layer
misses __ioctl_time64), so this reads it with picamera2 and serves multipart MJPEG.
"""
import io
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput


class FrameBuffer(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class Handler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/stream.mjpg':
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with output.condition:
                    output.condition.wait()
                    frame = output.frame
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


cam = Picamera2()
cam.configure(cam.create_video_configuration(main={'size': (640, 480)}, controls={'FrameRate': 5}))
output = FrameBuffer()
cam.start_recording(MJPEGEncoder(), FileOutput(output))
try:
    Server(('127.0.0.1', 8090), Handler).serve_forever()
finally:
    cam.stop_recording()
