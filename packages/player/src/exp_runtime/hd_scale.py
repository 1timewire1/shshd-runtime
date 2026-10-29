"""Pixels per HD frame point in the menus' drawing layers (the episode picker, the main menu, the pause menu...).

2 draws the 768 x 1024 point frame at the iPad's Retina resolution. A phone shows the frame at about 768 pixels
across, so drawing four times the pixels and shrinking every frame was wasted work there: the Android host asks
for 1 (SHSHD_HD_SCALE, set before the menus are imported).
"""
import os

S = 1 if os.environ.get('SHSHD_HD_SCALE') == '1' else 2
