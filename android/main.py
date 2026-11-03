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
# The window is drawn at the HD frame's own resolution and scaled to the screen by SDL's renderer (platforms/android.py,
# logical_size): smoothly, and to any size (pygame's SCALED reads its own spelling of the hint for that).
os.environ.setdefault('SDL_RENDER_SCALE_QUALITY', '1')
os.environ.setdefault('SDL_HINT_RENDER_SCALE_QUALITY', '1')
# The HD menus draw at the frame's own resolution too, not the iPad's 2x (hd_scale): a 2x layer was four times the
# pixels, then shrunk every frame, for a frame shown about 768 pixels across (the sound prompt took 50 ms a frame).
os.environ.setdefault('SHSHD_HD_SCALE', '1')

from exp_runtime.platforms.android import main

if __name__ == '__main__':
    main()
