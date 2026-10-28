"""python-for-android SDL entry point; game content is always player supplied."""
import os

# SDL synthesizes mouse events from the primary finger. Keep one input path.
os.environ.setdefault('SDL_TOUCH_MOUSE_EVENTS', '1')
os.environ.setdefault('SDL_MOUSE_TOUCH_EVENTS', '0')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
# SDL otherwise blocks its event pump while the activity is paused, holding Python's lock: the file picker's result
# (onActivityResult -> the host's callback) then waits for that lock on the UI thread, and the activity never resumes
# (a black screen after choosing a file). The host sleeps while it is in the background instead.
os.environ.setdefault('SDL_ANDROID_BLOCK_ON_PAUSE', '0')

from exp_runtime.platforms.android import main

if __name__ == '__main__':
    main()
