import board
import busio
import displayio
import terminalio
import random
import time
import adafruit_displayio_ssd1306
from adafruit_display_text import label
from kmk.kmk_keyboard import KMKKeyboard
from kmk.keys import KC
from kmk.scanners import DiodeOrientation
from kmk.modules.layers import Layers
from kmk.modules.encoder import EncoderHandler
from kmk.extensions.RGB import RGB

keyboard = KMKKeyboard()

# --- Hardware Configuration ---
keyboard.col_pins = (board.GP29, board.GP6, board.GP7)
keyboard.row_pins = (board.GP26, board.GP27, board.GP28)
keyboard.diode_orientation = DiodeOrientation.COL2ROW

# RGB Setup on GPIO0 (Pin 7)
rgb = RGB(pixel_pin=board.GP0, num_pixels=1, val_limit=255, hue_default=0)
keyboard.extensions.append(rgb)

# Encoder and Layer Modules
layers = Layers()
encoder_handler = EncoderHandler()
keyboard.modules = [layers, encoder_handler]
encoder_handler.pins = ((board.GP1, board.GP2, None, False),)

# OLED Initialization (SCL: GP3, SDA: GP4)
displayio.release_displays()
i2c = busio.I2C(scl=board.GP3, sda=board.GP4)
display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=32)

# --- Tetris Engine Constants ---
BOARD_W = 10
BOARD_H = 8
SHAPES = [
    [[1, 1, 1, 1]], # I
    [[1, 1], [1, 1]], # O
    [[0, 1, 0], [1, 1, 1]], # T
    [[0, 1, 1], [1, 1, 0]], # S
    [[1, 1, 0], [0, 1, 1]], # Z
    [[1, 0, 0], [1, 1, 1]], # L
    [[0, 0, 1], [1, 1, 1]]  # J
]

class TetrisGame:
    def __init__(self):
        self.reset()

    def reset(self):
        self.board = [[0] * BOARD_W for _ in range(BOARD_H)]
        self.new_piece()
        self.score = 0
        self.game_over = False

    def new_piece(self):
        self.piece = random.choice(SHAPES)
        self.px = BOARD_W // 2 - len(self.piece[0]) // 2
        self.py = 0
        if self.check_collision(self.px, self.py):
            self.game_over = True

    def check_collision(self, x, y, piece=None):
        piece = piece or self.piece
        for r, row in enumerate(piece):
            for c, val in enumerate(row):
                if val:
                    if (x + c < 0 or x + c >= BOARD_W or 
                        y + r >= BOARD_H or self.board[y + r][x + c]):
                        return True
        return False

    def rotate(self):
        new_p = [list(r) for r in zip(*self.piece[::-1])]
        if not self.check_collision(self.px, self.py, new_p):
            self.piece = new_p

    def move(self, dx, dy):
        if not self.check_collision(self.px + dx, self.py + dy):
            self.px += dx
            self.py += dy
            return True
        if dy > 0:
            self.lock_piece()
        return False

    def lock_piece(self):
        for r, row in enumerate(self.piece):
            for c, val in enumerate(row):
                if val: self.board[self.py + r][self.px + c] = 1
        self.clear_lines()
        self.new_piece()

    def clear_lines(self):
        self.board = [row for row in self.board if not all(row)]
        while len(self.board) < BOARD_H:
            self.board.insert(0, [0] * BOARD_W)
            self.score += 10

    def draw(self):
        bitmap = displayio.Bitmap(128, 32, 2)
        palette = displayio.Palette(2)
        palette[0], palette[1] = 0x000000, 0xFFFFFF
        for r in range(BOARD_H):
            for c in range(BOARD_W):
                if self.board[r][c]: self._fill_rect(bitmap, c*4 + 44, r*4, 3, 3)
        for r, row in enumerate(self.piece):
            for c, val in enumerate(row):
                if val: self._fill_rect(bitmap, (self.px+c)*4 + 44, (self.py+r)*4, 3, 3)
        tg = displayio.Group()
        tg.append(displayio.TileGrid(bitmap, pixel_shader=palette))
        display.show(tg)

    def _fill_rect(self, bitmap, x, y, w, h):
        for i in range(x, x+w):
            for j in range(y, y+h):
                if 0 <= i < 128 and 0 <= j < 32: bitmap[i, j] = 1

tetris = TetrisGame()

# --- Keymap ---
# SW9 (Index 8) is set to KC.RGB_HUI to cycle colors on every layer
keyboard.keymap = [
    [KC.LCTL(KC.C), KC.LCTL(KC.V), KC.LCTL(KC.Z), KC.F1, KC.F2, KC.F3, KC.F4, KC.F5, KC.RGB_HUI],
    [KC.W, KC.A, KC.S, KC.D, KC.Q, KC.E, KC.R, KC.F, KC.RGB_HUI],
    [KC.NO, KC.TRNS, KC.NO, KC.TRNS, KC.TRNS, KC.TRNS, KC.NO, KC.TRNS, KC.RGB_HUI]
]

# --- Mode Logic ---
current_mode = 0
def update_mode(direction):
    global current_mode
    current_mode = (current_mode + (1 if direction > 0 else -1)) % 3
    layers.activate(current_mode)
    splash = displayio.Group()
    modes = ["WORK", "GAME", "TETRIS"]
    splash.append(label.Label(terminalio.FONT, text=f"MODE: {modes[current_mode]}", x=30, y=15))
    display.show(splash)
    if current_mode == 2: tetris.reset()

encoder_handler.set_callback(lambda dir: update_mode(dir))

# --- Custom Runtime Loop ---
last_gravity = time.monotonic()
def main_loop_hook():
    global last_gravity
    if current_mode != 2: return
    if tetris.game_over: tetris.reset()
    
    # Manual matrix check for Tetris inputs
    keys = keyboard.matrix.update()
    if keys:
        for key in keys:
            if key.pressed:
                if key.number == 1: tetris.rotate()
                if key.number == 3: tetris.move(-1, 0)
                if key.number == 4: tetris.move(0, 1)
                if key.number == 5: tetris.move(1, 0)
                if key.number == 7: 
                    while tetris.move(0, 1): pass

    if time.monotonic() - last_gravity > 0.8:
        tetris.move(0, 1)
        last_gravity = time.monotonic()
        tetris.draw()

keyboard.after_matrix_scan = main_loop_hook

if __name__ == '__main__':
    keyboard.go()