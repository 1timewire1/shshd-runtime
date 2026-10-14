"""Button tracking shared by the desktop and native touch hosts."""


class ButtonPress:
    def __init__(self):
        self.cancel()

    def cancel(self):
        self.origin = self.pressed = self.token = None

    def validate(self, token):
        if self.token != token:
            self.cancel()

    def update(self, phase, hit, token=None):
        if phase == 'down':
            self.origin, self.pressed, self.token = hit, hit, token
        else:
            self.validate(token)
            self.pressed = hit if hit == self.origin else None
            if phase == 'up':
                command = self.pressed
                self.cancel()
                return command
        return None
