"""Authenticated loopback transport to the x86 GwAu3 adapter; no farm decisions."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import urllib.parse
import time
from version import bridge_name


def fields(reply):
    result = {}
    for part in reply.split('\t'):
        key, _, value = part.partition('=')
        try:
            result[key] = float(value) if '.' in value else int(value)
        except ValueError:
            result[key] = value
    return result


class GameBridge:
    def __init__(self, root, autoit, log_path):
        self.socket = None
        self.process = None
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        token = secrets.token_hex(32)
        args = ['--port', str(listener.getsockname()[1]), '--token', token, '--log', str(log_path)]
        native = Path(getattr(sys, '_MEIPASS', root)) / bridge_name()
        command = [str(native)] if native.is_file() else [autoit, str(Path(root) / 'GwAu3Bridge.au3')]
        try:
            self.process = subprocess.Popen(command + args, cwd=root, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.socket, _ = listener.accept()
            self.socket.settimeout(150)
            self.stream = self.socket.makefile('rb')
            if self.stream.readline(256).decode('ascii').strip() != token:
                raise RuntimeError('Game bridge authentication failed')
        except Exception:
            self.close()
            raise
        finally:
            listener.close()

    def call(self, command, *args):
        values = [command] + [str(x) for x in args]
        if any(any(c in value for c in '\t\r\n') for value in values):
            raise ValueError('Invalid bridge argument')
        self.socket.sendall(('\t'.join([values[0]] + [urllib.parse.quote(value, safe='') for value in values[1:]]) + '\n').encode('ascii'))
        line = self.stream.readline(65536)
        if not line or not line.endswith(b'\n'):
            raise RuntimeError('Game bridge disconnected')
        status, _, reply = line.decode('utf-8').rstrip('\r\n').partition('\t')
        if status != 'OK':
            raise RuntimeError('Game bridge request failed')
        return reply

    def snapshot(self):
        return fields(self.call('snapshot'))

    def inventory(self):
        return fields(self.call('inventory'))

    def agent(self, target):
        return fields(self.call('agent', target))

    def close(self):
        if self.socket is not None:
            try:
                self.socket.sendall(b'close\n')
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.stream.close()
            except (AttributeError, OSError):
                pass
            self.socket.close()
            self.socket = None
        if self.process is not None:
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                # Adapter restores rendering after detecting socket closure. Avoid killing game clients.
                pass
