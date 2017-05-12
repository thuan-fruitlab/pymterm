# coding=utf-8
import logging

from functools32 import lru_cache

from OpenGL.GL import glClearColor

import pyglet
from pyglet.window import key

import term.term_keyboard
from term import TextMode

import pymterm

from key_board import KeyState

SINGLE_WIDE_CHARACTERS =    \
                    " !\"#$%&'()*+,-./" \
                    "0123456789" \
                    ":;<=>?@" \
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ" \
                    "[\\]^_`" \
                    "abcdefghijklmnopqrstuvwxyz" \
                    "{|}~" \
                    ""
LOGGER = logging.getLogger('term_pyglet')

PADDING = 5
FONT_NAME = 'WenQuanYi Micro Hei Mono'
LEADING = 3


class TermPygletWindowBase(pyglet.window.Window):
    def __init__(self, *args, **kwargs):
        super(TermPygletWindowBase, self).__init__(width=1280,
                                                   height=800,
                                                   vsync=True,
                                                   *args, **kwargs)
        self.visible_cols = 132
        self.visible_rows = 24
        self._keys_handler = key.KeyStateHandler()
        self.push_handlers(self._keys_handler)
        self._key_first_down = False

    def on_resize(self, w, h):
        col_width, line_height = self._get_layout_info()
        self._clear_color = map(lambda x: float(x) / 255.0,
                                self.session.cfg.default_background_color)

        self.visible_cols = (w - 2 * PADDING) / col_width
        self.visible_rows = (h - 2 * PADDING) / line_height

        if self.session:
            self.session.resize_pty(self.visible_cols, self.visible_rows, w, h)
            self.session.terminal.resize_terminal()
        super(TermPygletWindowBase, self).on_resize(w, h)

    @lru_cache(1)
    def _get_font_info(self):
        font_file, font_name, font_size = \
            self.session.cfg.get_font_info()

        if font_file:
            pyglet.font.add_file(font_file)

        return font_name, font_size

    @lru_cache(1)
    def _get_layout_info(self):
        font_name, font_size = self._get_font_info()

        f = pyglet.font.load(font_name, font_size)

        glyphs = f.get_glyphs(SINGLE_WIDE_CHARACTERS)

        col_width = max([g.advance for g in glyphs])
        line_height = f.ascent - f.descent + LEADING

        return col_width, line_height

    def _set_doc_attribute(self, doc, begin, end, f_color, b_color, bold):
        attrs = {}

        if f_color != \
           self.session.cfg.default_foreground_color:
            attrs['color'] = f_color

        if b_color != \
           self.session.cfg.default_background_color:
            attrs.update({'background_color': b_color})

        if bold:
            attrs.update({'bold': True})

        doc.set_style(begin, end, attrs)

    def _create_line_layout(self, line, batch):
        text = line.get_text().strip()

        last_b_color = self.session.cfg.default_background_color
        last_f_color = self.session.cfg.default_foreground_color
        last_bold = False
        last_col = 0
        cur_col = 0

        font_name, font_size = self._get_font_info()

        doc = pyglet.text.document.FormattedDocument(text)

        # set attributes for whole document
        doc.set_style(0, len(text),
                      {'font_name': font_name,
                       'font_size': font_size,
                       'color':
                       self.session.cfg.default_foreground_color,
                       'bold': False
                       }
                      )

        for cell in line.get_cells():
            if cell.get_char() == '\000':
                continue

            cur_f_color, cur_b_color = \
                self.session.terminal.determin_colors(cell.get_attr())

            cur_bold = cell.get_attr().has_mode(TextMode.BOLD)

            if (cur_b_color, cur_f_color, cur_bold) != \
               (last_b_color, last_f_color, last_bold):
                if cur_col > last_col:
                    self._set_doc_attribute(doc,
                                            last_col,
                                            cur_col,
                                            last_f_color,
                                            last_b_color,
                                            last_bold)

                last_b_color = cur_b_color
                last_f_color = cur_f_color
                last_bold = cur_bold
                last_col = cur_col

            cur_col += 1

        if last_col < cur_col:
            self._set_doc_attribute(doc,
                                    last_col,
                                    cur_col,
                                    last_f_color,
                                    last_b_color,
                                    last_bold)

        return pyglet.text.layout.TextLayout(doc,
                                             multiline=False,
                                             wrap_lines=False,
                                             batch=batch)

    def on_draw(self):
        col_width, line_height = self._get_layout_info()

        def locked_draw():
            glClearColor(*self._clear_color)
            self.clear()
            y = self.height - PADDING - line_height

            batch = pyglet.graphics.Batch()

            for line in self.lines:
                layout = self._create_line_layout(line, batch)
                layout.begin_update()
                layout.x = PADDING
                layout.y = y
                layout.width = self.width
                layout.height = line_height
                layout.end_update()

                y -= line_height

            batch.draw()

        if (self.session):
            self.session.terminal.lock_display_data_exec(locked_draw)

    def on_show(self):
        if self.session:
            self.session.start()

    def refresh(self):
        def update(dt):
            pass

        pyglet.clock.schedule_once(update, 0)

    def on_key_press(self, symbol, modifiers):
        if pymterm.debug_log:
            LOGGER.debug('on_key_press:{}, {}'.format(
                key.symbol_string(symbol),
                key.modifiers_string(modifiers)))

        LOGGER.error('on_key_press:{}, {}'.format(
                key.symbol_string(symbol),
                key.modifiers_string(modifiers)))
        
        key_state = KeyState(symbol, modifiers)

        if symbol == key.Q and \
           (modifiers == key.MOD_COMMAND or modifiers == key.MOD_CTRL):
            self.close()
            return

        if self.session.terminal.process_key(key_state):
            if pymterm.debug_log:
                logging.getLogger('term_pygui').debug(' processed by pyterm')
            return

        v, handled = term.term_keyboard.translate_key(self.session.terminal,
                                                      key_state)

        if len(v) > 0:
            self.session.send(v)

        logging.error('{},{}'.format(v, handled))
        self._key_first_down = True

    def on_text(self, text):
        if pymterm.debug_log:
            LOGGER.debug(u'on_text:{}'.format(text))

        LOGGER.error(u'on_text:{}'.format(text))
        self.session.send(text.encode('utf_8'))

    def on_text_motion(self, motion):
        if motion == key.MOTION_BACKSPACE:
            if self._key_first_down:
                self._key_first_down = False
            else:
                self.on_key_press(key.BACKSPACE, 0)
