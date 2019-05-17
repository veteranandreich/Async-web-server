import http_server
import os
import sys

class AsyncWSGIServer(http_server.AsyncServer):

    def set_app(self, application):
        self.application = application

    def get_app(self):
        return self.application


class AsyncWSGIRequestHandler(http_server.AsyncHTTPRequestHandler):

    def get_environ(self):
        env = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': sys.stdin,
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'REQUEST_METHOD': self.method,
            'PATH_INFO': self.path,
            'SERVER_NAME': self.server_name,
            'SERVER_PORT': str(self.server_port)
        }

        return env

    def start_response(self, status, response_headers, exc_info=None):
        pass

    def handle_request(self):
        pass

    def finish_response(self, result):
        pass