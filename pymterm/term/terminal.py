import logging
import os

import cap.cap_manager
import parse_termdata
import read_termdata

from collections import deque

class Terminal(object):
    def __init__(self, cfg):
        self.cfg = cfg

        self.cap_str = self.__load_cap_str__('generic-cap')
        try:
            self.cap_str += self.__load_cap_str__(self.cfg.term_name)
        except:
            logging.exception('unable to load term data:%s' % self.cfg.term_name)
            self.cap_str += self.__load_cap_str__('xterm-256color')

        self.cap = parse_termdata.parse_cap(self.cap_str)
        self.context = parse_termdata.ControlDataParserContext()
        self.state = self.cap.control_data_start_state
        self.control_data = []
        self.in_status_line = False
        self.keypad_transmit_mode = False
        self._cap_state_stack = deque()

        logging.getLogger('terminal').debug('cap-str:{}, cap:{}, self={}'.format(self.cap_str, self.cap, self))

    def __load_cap_str__(self, term_name):
        if 'termcap_dir' in self.cfg.config:
            term_path = os.path.join(self.cfg.config['termcap_dir'], term_name+'.dat')

        if not os.path.exists(term_path):
            term_path = os.path.dirname(os.path.realpath(__file__))
            term_path = os.path.join(term_path, '..', '..', 'data', term_name+'.dat')

        logging.getLogger('terminal').info('load term cap data file:{}'.format(term_path))

        return read_termdata.get_entry(term_path, term_name)

    def on_data(self, data):
        self.__try_parse__(data)

    def on_control_data(self, cap_turple):
        cap_name, increase_params = cap_turple
        cap_handler = cap.cap_manager.get_cap_handler(cap_name)

        logging.getLogger('terminal').debug("control data:[[[" + ''.join(self.control_data) + ']]],for cap:' + cap_name)
        if not cap_handler:
            logging.getLogger('terminal').error('no matched:{}, params={}'.format(cap_turple, self.context.params))
        elif cap_handler:
            cap_handler.handle(self, self.context, cap_turple)

    def output_data(self, c):
        if self.in_status_line:
            self.output_status_line_data(c)
        else:
            self.output_normal_data(c)

    def __handle_cap__(self, check_unknown = True, data = None, c = None):
        cap_turple = self.state.get_cap(self.context.params)

        if cap_turple:
            self.on_control_data(cap_turple)

            if len(self._cap_state_stack) > 0:
                self.state, self.context.params, self.control_data = self._cap_state_stack.pop()
            else:
                self.state = self.cap.control_data_start_state
                self.context.params = []
                self.control_data = []
        elif check_unknown and len(self.control_data) > 0:
            m1 = 'start state:{}, params={}, self={}, next_states={}'.format(self.cap.control_data_start_state.cap_name, self.context.params, self, self.cap.control_data_start_state.next_states)
            m2 = 'current state:{}, params={}, next_states={}, {}, [{}]'.format(self.state.cap_name, self.context.params, self.state.next_states, self.state.digit_state, ord(c) if c else 'None')
            m3 = "unknown control data:[[[" + ''.join(self.control_data) + ']]]'
            m4 = 'data:[[[' + data.replace('\x1B', '\\E').replace('\r', '\r\n') + ']]]'
            m5 = 'data:[[[' + ' '.join(map(str, map(ord, data))) + ']]]'

            next_state = self.cap.control_data_start_state.handle(self.context, c)

            if not next_state:
                logging.getLogger('terminal').error('\r\n'.join([m1, m2, m3, m4, m5, str(self.in_status_line)]))

            self._cap_state_stack.append((self.state, self.context.params, self.control_data))

            self.state = self.cap.control_data_start_state
            self.context.params = []
            self.control_data = []

        if not check_unknown and not cap_turple and len(self.control_data) > 0:
            logging.getLogger('terminal').debug('found unfinished data')

        return cap_turple

    def __try_parse__(self, data):
        next_state = None

        for c in data:
            next_state = self.state.handle(self.context, c)

            if not next_state or self.state.get_cap(self.context.params):
                cap_turple = self.__handle_cap__(data=data, c=c)

                # retry last char
                next_state = self.state.handle(self.context, c)

                if next_state:
                    self.state = next_state
                    self.control_data.append(c if not c == '\x1B' else '\\E')
                else:
                    self.output_data(c)

                continue

            self.state = next_state
            self.control_data.append(c if not c == '\x1B' else '\\E')

        if self.state:
	        self.__handle_cap__(False)

    def enter_status_line(self, mode, enter):
        self.in_status_line = enter

    def get_cols(self):
        if 'columns' in self.cap.flags:
            return self.cap.flags['columns']

        return 80

    def get_rows(self):
        if 'lines' in self.cap.flags:
            return self.cap.flags['lines']

        return 24

    def get_tab_width(self):
        if 'init_tabs' in self.cap.flags:
            return self.cap.flags['init_tabs']

        return 8

    def set_selection(self, s_f, s_t):
        pass
