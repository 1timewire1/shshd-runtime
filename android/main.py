"""python-for-android SDL entry point; game content is always player supplied."""
import os

# SDL synthesizes mouse events from the primary finger. Keep one input path.
os.environ.setdefault('SDL_TOUCH_MOUSE_EVENTS', '1')
os.environ.setdefault('SDL_MOUSE_TOUCH_EVENTS', '0')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from exp_runtime.platforms.android import main

if __name__ == '__main__':
    main()
