import asyncore
import asynchat
import socket
import multiprocessing
import logging
import os
import mimetypes
from urllib.parse import urlparse
import argparse
from time import strftime, gmtime


def url_normalize(path):
    if path.startswith("."):
        path = "/" + path
    while "../" in path:
        p1 = path.find("/..")
        p2 = path.rfind("/", 0, p1)
        if p2 != -1:
            path = path[:p2] + path[p1 + 3:]
        else:
            path = path.replace("/..", "", 1)
    path = path.replace("/./", "/")
    path = path.replace("/.", "")
    return path


class FileProducer(object):

    def __init__(self, file, chunk_size=4096):
        self.file = file
        self.chunk_size = chunk_size

    def more(self):
        if self.file:
            data = self.file.read(self.chunk_size)
            if data:
                return data
            self.file.close()
            self.file = None
        return ""


def read_file(path):
    file = bytes()
    fp = FileProducer(open(path, 'rb'))
    while True:
        cur_chunk = fp.more()
        if not cur_chunk:
            break
        file += cur_chunk
    return file


class AsyncServer(asyncore.dispatcher):

    def __init__(self, host="127.0.0.1", port=9000):
        super().__init__()
        self.create_socket()
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)

    def handle_accepted(self, sock, addr):
        log.debug(f"Incoming connection from {addr}")
        AsyncHTTPRequestHandler(sock)

    def serve_forever(self):
        try:
            asyncore.loop()
        except KeyboardInterrupt:
            log.debug("Shutting down")
        finally:
            self.close()


class AsyncHTTPRequestHandler(asynchat.async_chat):

    def __init__(self, sock):
        super().__init__(sock)
        self.set_terminator(b"\r\n\r\n")
        self.ibuffer = ''
        self.obuffer = b""
        self.reading_headers = True
        self.headers = {}
        self.path = ''
        self.response = ''

    def collect_incoming_data(self, data):
        log.debug(f"Incoming data: {data}")
        self.ibuffer = data.decode('utf-8')

    def found_terminator(self):
        self.parse_request()

    def parse_request(self):
        if self.reading_headers:
            self.reading_headers = False
            self.method, self.path, self.ibuffer = self.ibuffer.split(' ', 2)
            self.parse_headers()
            if not self.headers['method']:
                self.send_error(400)
            if self.headers['method'] == "POST":
                try:
                    content_length = self.headers['Content-Length']
                    if content_length == '0':
                        raise KeyError
                    self.set_terminator(int(content_length))
                except KeyError:
                    self.send_error(400)
                    return
            else:
                self.handle_request()
        else:
            self.ibuffer = ''
            self.handle_request()

    def parse_headers(self):
        self.headers = {}
        key_value_strings = self.ibuffer.split('\r\n')
        for key_value in key_value_strings:
            key, value = key_value.split(':', 1)
            self.headers[key] = value
        return self

    def handle_request(self):
        method_name = 'do_' + self.headers['method']
        if not hasattr(self, method_name):
            self.send_error(405)
            self.handle_close()
            return
        handler = getattr(self, method_name)
        handler()

    def add_header(self, keyword, value):
        self.response += f"{keyword}: {value}"
        self.end_headers()

    def send_error(self, code, message=None):
        try:
            short_msg, long_msg = self.responses[code]
        except KeyError:
            short_msg, long_msg = '???', '???'
        if message is None:
            message = short_msg

        self.init_response(code, message)
        self.add_header("Content-Type", "text/plain")
        self.add_header("Connection", "close")
        self.end_headers()
        self.send(self.response.encode('utf-8'))
        self.close()

    def init_response(self, code, message=None):
        self.response = f"HTTP/1.1 {code} {message}"

    def end_headers(self):
        self.response += "\r\n"

    def date_time_string(self):
        return strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())

    def send_head(self):
        path = url_normalize(os.getcwd() + self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
            if not os.path.isfile(path):
                self.send_error(404)
                return
            file_type, _ = mimetypes.guess_type(path)
            file = read_file(path)
        elif os.path.isfile(path):
            file_type, _ = mimetypes.guess_type(path)
            file = read_file(path)
        else:
            self.send_error(404)
            return
        return file, file_type

    def do_GET(self):
        file, file_type = self.send_head()
        self.init_response(200, "OK")
        self.add_header("Content-Type", file_type)
        self.add_header("Date", self.date_time_string())
        self.add_header("Content-Length", len(file))
        self.add_header("Connection", "close")
        self.end_headers()
        self.send(bytes(self.response + file))
        self.close()

    def do_HEAD(self):
        file, file_type = self.send_head()
        self.init_response(200, "OK")
        self.add_header("Date", self.date_time_string())
        self.add_header("Content-Type", file_type)
        self.add_header("Content-Length", len(file))
        self.add_header("Connection", "close")
        self.end_headers()
        self.send(self.response.encode('utf-8'))
        self.close()

    def do_POST(self):
        self.init_response(200, "OK")
        self.add_header("Date", self.date_time_string())
        self.add_header("Content-Type", self.headers['Content-Type'])
        self.add_header("Connection", "close")
        self.add_header("Content-Length", self.headers['Content-Length'])
        self.end_headers()
        self.send(self.response.encode('utf-8'))
        self.close()

    responses = {
        200: ('OK', 'Request fulfilled, document follows'),
        400: ('Bad Request',
              'Bad request syntax or unsupported method'),
        403: ('Forbidden',
              'Request forbidden -- authorization will not help'),
        404: ('Not Found', 'Nothing matches the given URI'),
        405: ('Method Not Allowed',
              'Specified method is invalid for this resource.'),
    }


def parse_args():
    parser = argparse.ArgumentParser("Simple asynchronous web-server")
    parser.add_argument("--host", dest="host", default="127.0.0.1")
    parser.add_argument("--port", dest="port", type=int, default=9000)
    parser.add_argument("--log", dest="loglevel", default="info")
    parser.add_argument("--logfile", dest="logfile", default=None)
    parser.add_argument("-w", dest="nworkers", type=int, default=1)
    parser.add_argument("-r", dest="document_root", default=".")
    return parser.parse_args()


def run():
    server = AsyncServer(host=args.host, port=args.port)
    server.serve_forever()


if __name__ == "__main__":
    args = parse_args()

    logging.basicConfig(
        filename=args.logfile,
        level=getattr(logging, args.loglevel.upper()),
        format="%(name)s: %(process)d %(message)s")
    log = logging.getLogger(__name__)

    DOCUMENT_ROOT = args.document_root
    for _ in range(args.nworkers):
        p = multiprocessing.Process(target=run)
        p.start()
