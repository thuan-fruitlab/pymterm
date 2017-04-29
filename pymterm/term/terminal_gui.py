import logging
import sys
import threading

from term import TextAttribute, TextMode, reserve, clone_attr, get_default_text_attribute, DEFAULT_FG_COLOR_IDX, DEFAULT_BG_COLOR_IDX
from term import Cell, Line
from term_char_width import char_width
from terminal import Terminal
from charset_mode import translate_char, translate_char_british

class TerminalGUI(Terminal):
    def __init__(self, cfg):
        Terminal.__init__(self, cfg)

        self.term_widget = None
        self.session = None

        self.lines = []
        self.col = 0
        self.row = 0
        self.remain_buffer = []

        self.cur_line_option = get_default_text_attribute()
        self.saved_lines, self.saved_cursor, self.saved_cur_line_option = [], (0, 0), get_default_text_attribute()
        self.scroll_region = None

        self.view_history_begin = None
        self.history_lines = []

        self.status_line = []
        self.status_line_mode = 0

        self.charset_modes_translate = [None, None]
        self.charset_mode = 0

        self._data_lock = threading.RLock()

    def _translate_char(self, c):
        if self.charset_modes_translate[self.charset_mode]:
            return self.charset_modes_translate[self.charset_mode](c)
        else:
            return c

    def get_line(self, row):
        reserve(self.lines, row + 1, Line())

        return self.lines[row]

    def get_cur_line(self):
        line = self.get_line(self.row)

        line.alloc_cells(self.col + 1)

        return line

    def wrap_line(self, chars, insert):
        save_col, save_row = self.col, self.row

        self.col = 0
        self.cursor_down(None)
        for c in chars:
            if c == '\000':
                continue
            self._save_buffer(c, insert)

        if insert:
            self.col, self.row = save_col, save_row

    def save_buffer(self, c, insert = False):
        line = self.get_cur_line()

        #take care utf_8
        self.remain_buffer.append(c)

        c = ''.join(self.remain_buffer).decode('utf_8', errors='ignore')

        if len(c) == 0:
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('remain_buffer found:{}'.format(map(ord, self.remain_buffer)))
            return

        self.remain_buffer = []

        #translate g0, g1 charset
        c = self._translate_char(c)

        w = char_width(c)

        if w == 0 or w == -1:
            logging.getLogger('term_gui').warning(u'save buffer get a invalid width char: w= {}, c={}'.format(w, c))

        if len(c.encode('utf_8')) > 1 and w > 1:
            c += '\000'

        if self.cfg.debug_more:
            logging.getLogger('term_gui').debug(u'save buffer width:{},{},{},len={}, line_len={}, cols={}'.format(self.col, self.row, w, len(c), line.cell_count(), self.get_cols()))

        if insert:
            if line.cell_count() + len(c) > self.get_cols():
                wrap_c = line.get_cells()[self.get_cols() - line.cell_count() - len(c):]

                if wrap_c[0].get_char() == '\000':
                    wrap_c = line.get_cells()[self.get_cols() - line.cell_count() - len(c) - 1:]

                two_bytes = len(wrap_c)

                if self.cfg.debug_more:
                    logging.getLogger('term_gui').debug(u'save buffer wrap:c=[{}], wrap=[{}]'.format(c, wrap_c))

                self._save_buffer(c, insert)
                self.wrap_line(''.join([c.get_char() for c in wrap_c]), insert)
            else:
                self._save_buffer(c, insert)
        else:
            if self.col + len(c) > self.get_cols():
                #wrap
                self.wrap_line(c, insert)
            else:
                self._save_buffer(c, insert)


    def _save_buffer(self, c, insert):
        line = self.get_cur_line()

        if self.cfg.debug_more:
            logging.getLogger('term_gui').debug(u'save buffer:{},{},{},len={}'.format(self.col, self.row, c, len(c)))

        if insert:
            line.insert_cell(self.col, Cell(c[0], self.cur_line_option, len(c) > 1))

            if len(c) > 1:
                line.insert_cell(self.col, Cell(c[1], self.cur_line_option, len(c) > 1))
        else:
            line.alloc_cells(self.col + len(c))
            if self.cfg.debug_more:
                logging.getLogger('term_gui').debug(u'save buffer option:{},{},{},option={}'.format(self.col, self.row,
                                                                                                            c, self.cur_line_option))
            line.get_cell(self.col).set_char(c[0])
            line.get_cell(self.col).set_attr(self.cur_line_option)
            line.get_cell(self.col).set_is_wide_char(len(c) > 1)

            self.col += 1
            if len(c) > 1:
                line.get_cell(self.col).set_char(c[1])
                line.get_cell(self.col).set_attr(self.cur_line_option)
                line.get_cell(self.col).set_is_wide_char(len(c) > 1)
                self.col += 1

    def get_rows(self):
        return self.term_widget.visible_rows

    def get_cols(self):
        cols = self.term_widget.visible_cols

        return cols

    def get_history_text(self):
        return self.history_lines + self.lines

    def get_text(self):
        if self.view_history_begin is not None:
            l = self.get_history_text()
            lines = l[self.view_history_begin: self.view_history_begin + self.get_rows()]
            return lines

        if len(self.lines) <= self.get_rows():
            return self.lines + [self.create_new_line()] * (self.get_rows() - len(self.lines))
        else:
            if self.cfg.debug:
                logging.getLogger('get_text').debug('{}={}'.format(len(self.lines), self.get_rows))
            lines = self.lines[len(self.lines) - self.get_rows():]
            return lines

    def output_normal_data(self, c, insert = False):
        if c == '\x1b':
            logging.getLogger('term_gui').error('normal data has escape char')
            sys.exit(1)

        try:
            for cc in c:
                self.save_buffer(cc, insert)
        except:
            logging.getLogger('term_gui').exception('save buffer failed')

    def output_status_line_data(self, c):
        if c == '\x1b':
            logging.getLogger('term_gui').error('status line data has escape char')
            sys.exit(1)

        self.status_line.append(c)

    def save_cursor(self, context):
        self.saved_cursor = self.get_cursor()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('{} {} {} {} {} {} {}'.format( 'save', self.saved_cursor, self.row, self.col, len(self.lines), self.get_rows(), self.get_cols()))

    def restore_cursor(self, context):
        col, row = self.saved_cursor
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('{} {} {}'.format( 'restore', row, col))
        self.set_cursor(col, row)

    def get_cursor(self):
        if len(self.lines) <= self.get_rows():
            return (self.col, self.row)
        else:
            return (self.col, self.row - len(self.lines) + self.get_rows())

    def set_cursor(self, col, row):
        self.col = col
        if len(self.lines) <= self.get_rows():
            self.row = row
        else:
            self.row = row + len(self.lines) - self.get_rows()

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('terminal cursor:{}, {}'.format(self.col, self.row));

    def cursor_right(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('cursor right:{}, {}'.format(self.col, self.row));
        if self.col < self.get_cols() - 1:
            self.col += 1
        self.refresh_display()

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('after cursor right:{}, {}'.format(self.col, self.row));

    def cursor_left(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('cursor left:{}, {}'.format(self.col, self.row));
        if self.col > 0:
            self.col -= 1
        self.refresh_display()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('after cursor left:{}, {}'.format(self.col, self.row));

    def cursor_down(self, context):
        self.parm_down_cursor(context)

    def cursor_up(self, context):
        self.parm_up_cursor(context)

    def carriage_return(self, context):
        self.col = 0
        self.refresh_display()

    def set_foreground(self, light, color_idx):
        self.set_attributes(1 if light else -1, color_idx, -2)

    def set_background(self, light, color_idx):
        self.set_attributes(1 if light else -1, -2, color_idx)

    def origin_pair(self):
        self.cur_line_option.reset_mode()
        self.cur_line_option.reset_fg_idx()
        self.cur_line_option.reset_bg_idx()

    def clr_line(self, context):
        line = self.get_cur_line()

        for cell in line.get_cells():
            cell.reset()

        self.refresh_display()

    def clr_eol(self, context):
        line = self.get_cur_line()

        begin = self.col
        if line.get_cell(begin).get_char() == '\000':
            begin -= 1

        for i in range(begin, line.cell_count()):
            line.get_cell(i).reset()

        self.refresh_display()

    def clr_bol(self, context):
        line = self.get_cur_line()

        end = self.col
        if end + 1 < line.cell_count() and line.get_cell(end + 1).get_char() == '\000':
            end = end + 1

        for i in range(end + 1):
            line.get_cell(i).reset()

        self.refresh_display()

    def delete_chars(self, count, overwrite = False):
        line = self.get_cur_line()
        begin = self.col

        if line.get_cell(begin).get_char() == '\000':
            begin -= 1

        end = line.cell_count() if not overwrite or begin + count > line.cell_count() else begin + count

        for i in range(begin, end):
            if not overwrite and i + count < line.cell_count():
                line.get_cell(i).copy(line.get_cell(i + count))
            else:
                line.get_cell(i).reset()

        self.refresh_display()

    def refresh_display(self):
        self.term_widget.refresh()

    def lock_display_data_exec(self, func):
        try:
            self._data_lock.acquire()

            lines = self.get_text()

            self.term_widget.lines = lines
            self.term_widget.term_cursor = self.get_cursor()
            self.term_widget.cursor_visible = self.view_history_begin is None
            self.term_widget.focus = True

            func()
        except:
            logging.getLogger('term_gui').exception('lock display data exec')
        finally:
            self._data_lock.release()

    def on_data(self, data):
        try:
            self._data_lock.acquire()
            Terminal.on_data(self, data)
        except:
            logging.getLogger('term_gui').exception('on data')
        finally:
            self._data_lock.release()

        self.refresh_display()

    def meta_on(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('meta_on')

    def set_attributes(self, mode, f_color_idx, b_color_idx):
        fore_color = None
        back_color = None

        text_mode = None

        if (mode > 0):
            if mode & (1 << 1):
                self.cur_line_option.set_mode(TextMode.BOLD)
            if mode & (1 << 2):
                self.cur_line_option.set_mode(TextMode.DIM)
            if mode & (1 << 7):
                self.cur_line_option.set_mode(TextMode.REVERSE)
            if mode & (1 << 21) or mode & (1 << 22):
                self.cur_line_option.unset_mode(TextMode.BOLD)
                self.cur_line_option.unset_mode(TextMode.DIM)
            if mode & (1 << 27):
                self.cur_line_option.unset_mode(TextMode.REVERSE)
        elif mode == 0:
            self.cur_line_option.reset_mode()
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('reset mode')

        if f_color_idx >= 0:
            self.cur_line_option.set_fg_idx(f_color_idx)
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('set fore color:{} {} {}, cur_option:{}'.format(f_color_idx, ' at ', self.get_cursor(), self.cur_line_option))
        elif f_color_idx == -1:
            #reset fore color
            self.cur_line_option.reset_fg_idx()
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('reset fore color:{} {} {}, cur_option:{}'.format(f_color_idx, ' at ', self.get_cursor(), self.cur_line_option))

        if b_color_idx >= 0:
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('set back color:{} {} {}, cur_option:{}'.format(b_color_idx, ' at ', self.get_cursor(), self.cur_line_option))
            self.cur_line_option.set_bg_idx(b_color_idx)
        elif b_color_idx == -1:
            #reset back color
            if self.cfg.debug:
                logging.getLogger('term_gui').debug('reset back color:{} {} {}, cur_option:{}'.format(b_color_idx, ' at ', self.get_cursor(), self.cur_line_option))
            self.cur_line_option.reset_bg_idx()

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('set attribute:{}'.format(self.cur_line_option))

    def cursor_address(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('cursor address:{}'.format(context.params))
        self.set_cursor(context.params[1], context.params[0])
        self.refresh_display()

    def cursor_home(self, context):
        self.set_cursor(0, 0)
        self.refresh_display()

    def _row_from_screen(self, s_row):
        if len(self.lines) <= self.get_rows():
            return s_row
        else:
            return s_row + len(self.lines) - self.get_rows()

    def clr_eos(self, context):
        self.get_cur_line()

        begin = self._row_from_screen(0)
        end = self._row_from_screen(self.get_rows())

        if len(context.params) == 0 or context.params[0] == 0:
            self.clr_eol(context)

            begin = self.row + 1
        elif context.params[0] == 1:
            self.clr_bol(context)

            end = self.row

        for row in range(begin, end):
            line = self.get_line(row)

            for cell in line.get_cells():
                cell.reset()

        self.refresh_display()

    def parm_right_cursor(self, context):
        self.col += context.params[0] if context.params[0] > 0 else 1
        if self.col > self.get_cols():
            self.col = self.get_cols() - 1
        self.refresh_display()

    def parm_left_cursor(self, context):
        self.col -= context.params[0] if context.params[0] > 0 else 1
        if self.col < 0:
            self.col = 0
        self.refresh_display()

    def client_report_version(self, context):
        self.session.send('\033[>0;136;0c')

    def user7(self, context):
        if (context.params[0] == 6):
            col, row = self.get_cursor()
            self.session.send(''.join(['\x1B[', str(row + 1), ';', str(col + 1), 'R']))
        elif context.params[0] == 5:
            self.session.send('\033[0n')

    def tab(self, context):
        col = self.col / self.session.get_tab_width()
        col = (col + 1) * self.session.get_tab_width();

        if col >= self.get_cols():
            col = self.get_cols() - 1

        self.col = col
        self.refresh_display()

    def row_address(self, context):
        self.set_cursor(self.col, context.params[0])

    def delete_line(self, context):
        self.parm_delete_line(context)

    def parm_delete_line(self, context):
        begin, end = self.get_scroll_region()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('delete line:{} begin={} end={}'.format(context.params, begin, end))

        c_to_delete = context.params[0] if len(context.params) > 0 else 1

        for i in range(c_to_delete):
            if self.row <= end:
                self.lines = self.lines[:self.row] + self.lines[self.row + 1: end + 1] + [self.create_new_line()] +self.lines[end + 1:]

        self.refresh_display()

    def get_scroll_region(self):
        if self.scroll_region:
            return self.scroll_region

        self.set_scroll_region(0, self.get_rows() - 1)

        return self.scroll_region

    def set_scroll_region(self, begin, end):
        if len(self.lines) > self.get_rows():
            begin = begin + len(self.lines) - self.get_rows()
            end = end + len(self.lines) - self.get_rows()

        self.get_line(end)
        self.get_line(begin)

        self.scroll_region = (begin, end)

    def change_scroll_region(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('change scroll region:{} rows={}'.format(context.params, self.get_rows()))
        if len(context.params) == 0:
            self.scroll_region = None
        else:
            self.set_scroll_region(context.params[0], context.params[1])
        self.refresh_display()

    def change_scroll_region_from_start(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('change scroll region from start:{} rows={}'.format(context.params, self.get_rows()))
        self.set_scroll_region(0, context.params[0])
        self.refresh_display()

    def change_scroll_region_to_end(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('change scroll region to end:{} rows={}'.format(context.params, self.get_rows()))
        self.set_scroll_region(context.params[0], self.get_rows() - 1)
        self.refresh_display()

    def insert_line(self, context):
        self.parm_insert_line(context)

    def parm_insert_line(self, context):
        begin, end = self.get_scroll_region()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('insert line:{} begin={} end={}'.format(context.params, begin, end))

        c_to_insert = context.params[0] if len(context.params) > 0 else 1

        for i in range(c_to_insert):
            if self.row <= end:
                self.lines = self.lines[:self.row] + [self.create_new_line()] + self.lines[self.row: end] +self.lines[end + 1:]

        self.refresh_display()

    def request_background_color(self, context):
        rbg_response = '\033]11;rgb:%04x/%04x/%04x/%04x\007' % (self.cfg.default_background_color[0], self.cfg.default_background_color[1], self.cfg.default_background_color[2], self.cfg.default_background_color[3])

        if self.cfg.debug:
            logging.getLogger('term_gui').debug("response background color request:{}".format(rbg_response.replace('\033', '\\E')))
        self.session.send(rbg_response)

    def user9(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('response terminal type:{} {}'.format(context.params, self.cap.cmds['user8'].cap_value))
        self.session.send(self.cap.cmds['user8'].cap_value)

    def enter_reverse_mode(self, context):
        self.cur_line_option.set_mode(TextMode.REVERSE)
        self.refresh_display()

    def exit_standout_mode(self, context):
        self.cur_line_option.reset_mode()
        self.refresh_display()

    def enter_ca_mode(self, context):
        self.saved_lines, self.saved_col, self.saved_row, self.saved_cur_line_option = \
          self.lines, self.col, self.row, self.cur_line_option
        self.lines, self.col, self.row, self.cur_line_option = \
          [], 0, 0, get_default_text_attribute()
        self.term_widget.cancel_selection()
        self.refresh_display()

    def exit_ca_mode(self, context):
        self.lines, self.col, self.row, self.cur_line_option = \
            self.saved_lines, self.saved_col, self.saved_row, self.saved_cur_line_option
        self.term_widget.cancel_selection()
        self.refresh_display()

    def key_shome(self, context):
        self.set_cursor(1, 0)
        self.refresh_display()

    def enter_bold_mode(self, context):
        self.cur_line_option.set_mode(TextMode.BOLD)
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('set bold mode:attr={}'.format(self.cur_line_option))

    def keypad_xmit(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('keypad transmit mode')
        self.keypad_transmit_mode = True

    def keypad_local(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('keypad local mode')
        self.keypad_transmit_mode = False

    def cursor_invisible(self, context):
        self.term_widget.cursor_visible = False
        self.refresh_display()

    def cursor_normal(self, context):
        self.term_widget.cursor_visible = True
        self.refresh_display()

    def cursor_visible(self, context):
        self.cursor_normal(context)

    def next_line(self, context):
        self.col = 0
        self.parm_down_cursor(context)

    def parm_down_cursor(self, context):
        begin, end = self.get_scroll_region()

        count = context.params[0] if context and context.params and len(context.params) > 0 else 1

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('before parm down cursor:{} {} {} {} {}'.format(begin, end, self.row, count, len(self.lines)))
        for i in range(count):
            self.get_cur_line()

            if self.row == end:
                if begin == 0:
                    self.history_lines.append(self.lines[begin])
                self.lines = self.lines[:begin] + self.lines[begin + 1: end + 1] + [self.create_new_line()] + self.lines[end + 1:]
            else:
                self.row += 1

            self.get_cur_line()

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('after parm down cursor:{} {} {} {} {}'.format(begin, end, self.row, count, len(self.lines)))
        self.refresh_display()

    def exit_alt_charset_mode(self, context):
        self.charset_modes_translate[0] = None
        self.exit_standout_mode(context)
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('exit alt:{} {}'.format(' at ', self.get_cursor()))

    def enter_alt_charset_mode(self, context):
        self.charset_modes_translate[0] = translate_char
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('enter alt:{} {}'.format(' at ', self.get_cursor()))

    def enter_alt_charset_mode_british(self, context):
        self.charset_modes_translate[0] = translate_char_british

    def enter_alt_charset_mode_g1(self, context):
        self.charset_modes_translate[1] = translate_char

    def enter_alt_charset_mode_g1_british(self, context):
        self.charset_modes_translate[1] = translate_char_british

    def exit_alt_charset_mode_g1_british(self, context):
        self.charset_modes_translate[1] = None
        self.exit_standout_mode(context)

    def shift_in_to_charset_mode_g0(self, context):
        self.charset_mode = 0
        self.refresh_display()

    def shift_out_to_charset_mode_g1(self, context):
        self.charset_mode = 1
        self.refresh_display()

    def enable_mode(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('enable mode:{}'.format(context.params))

        mode = context.params[0]

        if mode == 25:
            self.cursor_normal(context)

    def disable_mode(self, context):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('disable mode:{}'.format(context.params))

        mode = context.params[0]

        if mode == 25:
            self.cursor_invisible(context)

    def process_key(self, keycode, text, modifiers):
        handled = False
        code, key = keycode
        view_history_key = False

        if ('shift' in modifiers or 'shift_L' in modifiers or 'shift_R' in modifiers ) and key == 'insert':
            #paste
            self.paste_data()
            handled = True
        elif ('ctrl' in modifiers or 'ctrl_L' in modifiers or 'ctrl_R' in modifiers) and key == 'insert':
            #copy
            self.copy_data()
            handled = True
        elif ('shift' in modifiers or 'shift_L' in modifiers or 'shift_R' in modifiers ) and (key == 'pageup' or key == 'pagedown'):
            self.view_history(key == 'pageup')
            handled = True
            view_history_key = True

        if (not view_history_key and
            not ((key == 'shift' or key == 'shift_L' or key == 'shift_R') and len(modifiers) == 0)):
            self.view_history_begin = None

        return handled

    def has_selection(self):
        s_from, s_to = self.term_widget.get_selection()

        return not (s_from == s_to)

    def get_selection_text(self):
        lines = self.get_text()

        s_from, s_to = self.term_widget.get_selection()

        if s_from == s_to:
            return ''

        s_f_col, s_f_row = s_from
        s_t_col, s_t_row = s_to

        texts = []

        if s_f_row == s_t_row:
            line = lines[s_f_row]
            if not line:
                return ''

            return line.get_text(s_f_col, s_t_col)

        for line_num, line in enumerate(lines[s_f_row:s_t_row + 1], start=s_f_row):
            if not line:
                continue
            if line_num == s_f_row:
                if s_f_col < line.cell_count():
                    texts.append(line.get_text(s_f_col))
            elif line_num == s_t_row:
                if s_t_col <= line.cell_count():
                    texts.append(line.get_text(0, s_t_col))
            else:
                texts.append(line.get_text())

        d = '\r\n'

        if 'carriage_return' in self.cap.cmds:
            d = self.cap.cmds['carriage_return'].cap_value

        data = d.join(texts).replace('\000', '')

        return data

    def column_address(self, context):
        col, row = self.get_cursor()
        self.set_cursor(context.params[0], row)
        self.refresh_display()

    def parm_up_cursor(self, context):
        begin, end = self.get_scroll_region()

        count = context.params[0] if context and context.params and len(context.params) > 0 else 1

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('before parm up cursor:{} {} {} {} {}'.format(begin, end, self.row, count, len(self.lines)))
        for i in range(count):
            self.get_cur_line()

            if self.row == begin:
                self.lines = self.lines[:begin] + [self.create_new_line()] + self.lines[begin: end] + self.lines[end + 1:]
            else:
                self.row -= 1

            self.get_cur_line()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('after parm up cursor:{} {} {} {} {}'.format(begin, end, self.row, count, len(self.lines)))
        self.refresh_display()

    def view_history(self, pageup):
        lines = self.get_history_text()
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('view history:pageup={}, lines={}, rows={}, view_history_begin={}'.format(pageup, len(lines), self.get_rows(), self.view_history_begin))

        if len(lines) <=  self.get_rows():
            return

        if self.view_history_begin is not None:
            self.view_history_begin -= self.get_rows() if pageup else self.get_rows() * -1
        elif pageup:
            self.view_history_begin = len(lines) - 2 * self.get_rows()
        else:
            return

        if self.view_history_begin < 0:
            self.view_history_begin = 0
        if self.view_history_begin > len(lines):
            self.view_history_begin = len(lines) - self.get_rows()

        self.refresh_display()

    def prompt_login(self, t, username):
        logging.getLogger('term_gui').warn('sub class must implement prompt login')
        pass

    def prompt_password(self, action):
        logging.getLogger('term_gui').warn('sub class must implement prompt password')
        pass

    def create_new_line(self):
        return Line()

    def paste_data(self):
        data = ''
        if self.has_selection():
            data = self.get_selection_text()
            self.term_widget.cancel_selection()

        if len(data) == 0:
            data = self.term_widget.paste_from_clipboard()
        else:
            self.term_widget.copy_to_clipboard(data)

        if len(data) > 0:
            self.session.send(data.encode('utf-8'))

    def copy_data(self):
        data = self.get_selection_text()

        if len(data) == 0:
            return

        self.term_widget.copy_to_clipboard(data)

        self.term_widget.cancel_selection()

    def resize_terminal(self):
        if len(self.lines) <= self.get_rows():
            self.set_scroll_region(0, self.get_rows() - 1)
            return

        last_line = -1
        for i in range(len(self.lines) - 1, 0, -1):
            if len(self.lines[i].get_text().strip()) > 0:
                last_line = i
                break

        self.lines = self.lines[:last_line + 1]

        for i in range(len(self.lines)):
            self.lines[i].alloc_cells(self.get_cols(), True)

        self.set_scroll_region(0, self.get_rows() - 1)

    def enter_status_line(self, mode, enter):
        if not enter:
            status_line = ''.join(self.status_line)
            if len(status_line) > 0:
                self.process_status_line(mode, status_line)
        else:
            self.status_line = []
            self.status_line_mode = mode

        Terminal.enter_status_line(self, mode, enter)

    def process_status_line(self, mode, status_line):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('status line:mode={}, {}'.format(mode, status_line))
        self.session.on_status_line(mode, status_line)

    def determin_colors(self, attr):
        if self.cfg.debug:
            logging.getLogger('term_gui').debug('determin_colors:attr={}'.format(attr))
        def _get_color(idx):
            color = None

            if idx < 8:
                color = self.cfg.get_color(8 + idx if attr.has_mode(TextMode.BOLD) else idx)
            elif idx < 16:
                color = self.cfg.get_color(idx)
            elif idx < 256:
                color = self.cfg.get_color(idx)
            elif idx == DEFAULT_FG_COLOR_IDX:
                color = self.cfg.default_foreground_color
            elif idx == DEFAULT_BG_COLOR_IDX:
                color = self.cfg.default_background_color
            else:
                logging.getLogger('term_gui').error('not implemented color:{} mode={}'.format(idx, mode))
                sys.exit(1)

            if attr.has_mode(TextMode.DIM):
                color = map(lambda x: int(float(x) * 2 / 3), color)
            return color

        f_color = _get_color(attr.get_fg_idx())
        b_color = _get_color(attr.get_bg_idx())

        if attr.has_mode(TextMode.REVERSE):
            f_color, b_color = b_color, f_color

        if attr.has_mode(TextMode.SELECTION):
            f_color, b_color = b_color, f_color

        if attr.has_mode(TextMode.CURSOR):
            f_color, b_color = b_color, self.cfg.default_cursor_color

        if self.cfg.debug:
            logging.getLogger('term_gui').debug('determin_colors:attr={},f={},b={}'.format(attr, map(hex, f_color), map(hex, b_color)))
        return (f_color, b_color)

    def send_primary_device_attributes(self, context):
        self.session.send('\033[?62;c')

    def screen_alignment_test(self, context):
        self.save_cursor(context)
        self.get_line(self.get_rows() - 1)

        for i in range(self.get_rows()):
            self.set_cursor(0, i)
            line = self.get_cur_line()
            line.alloc_cells(self.get_cols(), True)

            for cell in line.get_cells():
                cell.set_char('E')

        self.restore_cursor(context)
        self.refresh_display()
