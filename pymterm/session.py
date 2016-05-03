import os
import select
import socket
import sys
import time
import traceback

class Session:
    def __init__(self, cfg, terminal):
        self.cfg = cfg
        self.terminal = terminal
        self.sock = None
        self.writer = None
        self.chan = None
        self.terminal.session = self

    def connect(self):
        username = self.cfg.username
        hostname = self.cfg.hostname
        port = self.cfg.port

        # now connect
        try:
            self.sock = sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((hostname, port))

            return sock
        except Exception as e:
            print('*** Connect failed: ' + str(e))
            traceback.print_exc()
            self.report_error("connect to %s@%s:%d failed." % (username, hostname, port))

        return None

    def report_error(self, msg):
        print('^^^^ ' + msg);

    def interactive_shell(self, chan):
        cols = self.terminal.get_cols()
        rows = self.terminal.get_rows()
        
        chan.get_pty(term=self.cfg.term_name, width=cols, height = rows)
        chan.invoke_shell()
        self.windows_shell(chan)

    def windows_shell(self, chan):
        import threading

        self.chan = chan
	    
        def writeall(sock):
	        while True:
		        data = sock.recv(4096)
		        if not data:
			        sys.stdout.write('\r\n*** EOF ***\r\n\r\n')
			        sys.stdout.flush()
			        break
		        self.terminal.on_data(data)

        self.writer = writer = threading.Thread(target=writeall, args=(chan,))
        writer.start()

        chan.send('echo $TERM\x01abc\r\n')
        chan.send('ls\r\n')

    def wait_for_quit(self):
        self.writer.join()

    def get_tab_width(self):
        return self.terminal.get_tab_width()
