"""Qt-thread bridge from local MCP requests to the open desktop document."""
import json
from pathlib import Path
import secrets
import struct
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWidgets import QAbstractSpinBox, QApplication

from .model import ProjectError, project_bytes, project_from_record, project_record
from .sharing import (MAX_MESSAGE, TIMEOUT, Lease, ProjectBusy, SharingError,
                      digest, encode_message)


class LiveEditor:
    def __init__(self, editor):
        self.editor, self.lease = editor, None
        self.server = QTcpServer(editor)
        self.connections = {}
        self.server.newConnection.connect(self.accept)

    def attach(self, path):
        path = Path(path).resolve() if path else None
        if self.lease and self.lease.path == path: return
        if path is not None:
            if not self.server.isListening() and not self.server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
                raise SharingError('Cannot start local desktop sharing: ' + self.server.errorString())
            lease = Lease(path, self.server.serverPort())
        else:
            lease = None
        previous, self.lease = self.lease, lease
        if previous is not None: previous.close()

    def close(self):
        self.attach(None)
        self.server.close()
        for connection in list(self.connections): connection.abort()

    def accept(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            if len(self.connections) >= 8:
                connection.abort(); connection.deleteLater(); continue
            self.connections[connection] = [bytearray(), time.monotonic()]
            connection.setReadBufferSize(MAX_MESSAGE + 4)
            connection.readyRead.connect(lambda c=connection: self.receive(c))
            connection.disconnected.connect(lambda c=connection: self.disconnected(c))
            timer = QTimer(connection)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda c=connection: c.abort())
            timer.start((TIMEOUT - 2) * 1000)

    def disconnected(self, connection):
        self.connections.pop(connection, None)
        connection.deleteLater()

    def receive(self, connection):
        if connection not in self.connections: return
        buffer, started = self.connections[connection]
        buffer.extend(bytes(connection.readAll()))
        if time.monotonic() - started > TIMEOUT - 3 or len(buffer) > MAX_MESSAGE + 4:
            connection.abort(); return
        if len(buffer) < 4: return
        size, = struct.unpack('>I', buffer[:4])
        if not 0 < size <= MAX_MESSAGE:
            connection.abort(); return
        if len(buffer) < size + 4: return
        try:
            message = json.loads(buffer[4:])
            response = self.dispatch(message)
        except (ProjectError, ValueError, TypeError, KeyError, OSError, RecursionError) as error:
            response = dict(error=str(error), code=getattr(error, 'code', 'invalid_request'))
        # One request per connection; dispatch and all UI changes run on the
        # Qt thread, so a revision check and replacement cannot interleave.
        self.connections.pop(connection, None)
        connection.write(encode_message(response))
        connection.disconnectFromHost()

    def dispatch(self, message):
        if (not isinstance(message, dict) or self.lease is None
                or not isinstance(message.get('token'), str)
                or not secrets.compare_digest(message['token'], self.lease.record['token'])
                or message.get('path') != str(self.lease.path)):
            raise ProjectError('Unknown desktop session')
        editor, path = self.editor, self.lease.path
        if Path(editor.path).resolve() != path: raise SharingError('Desktop project changed; reread the project')
        if QApplication.activeModalWidget() is not None or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            raise ProjectBusy('Desktop is editing a dialog or dragging a selection; retry after it finishes.')
        focus = QApplication.focusWidget()
        if focus is not None:
            spin = focus if isinstance(focus, QAbstractSpinBox) else focus.parentWidget()
            if isinstance(spin, QAbstractSpinBox) and not spin.hasAcceptableInput():
                raise ProjectBusy('Finish entering the number in the desktop editor, then retry.')
        revision = digest(project_bytes(editor.project, path))
        if message.get('action') == 'read':
            return dict(project=project_record(editor.project), revision=revision, unsaved=editor.dirty)
        if message.get('action') != 'commit': raise ProjectError('Unknown desktop operation')
        if message.get('revision') != revision:
            raise ProjectError('Project changed; read its current revision before editing')
        candidate = project_from_record(message['project'])
        encoded = project_bytes(candidate, path)
        # The workspace validates edit operations before submission. A full
        # checkpoint restore may contain unfinished connections, just as a
        # desktop undo can; retain the model's structural validation here.
        # Recover the entire accepted transaction even if the app exits before
        # the periodic autosave. Failure leaves the live document untouched.
        editor.recovery.write(candidate, path)
        editor.remember()
        editor.project = candidate
        if editor.selected not in {node.id for node in candidate.nodes}:
            editor.selected = candidate.start if any(n.id == candidate.start for n in candidate.nodes) else candidate.nodes[0].id
        editor.refresh(preserve_focus=True)
        editor.statusBar().showMessage('Model edits applied. Undo reverses this edit; Save writes the shared project.')
        return dict(revision=digest(encoded), live=True, unsaved=True)
