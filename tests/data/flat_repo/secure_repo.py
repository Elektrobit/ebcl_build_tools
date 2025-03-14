import base64
import argparse
from functools import partial
import os
import signal
import sys
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer


""" global variable ok since used in pytest code only """
ebcl_auth_status = False


class AuthHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, username, password, directory=None, **kwargs):
        self.username = username
        self.password = password
        if directory is None:
            directory = os.getcwd()
        super().__init__(*args, directory=directory, **kwargs)

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Secure Area"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        global ebcl_auth_status
        auth_header = self.headers.get('Authorization')
        if auth_header is None:
            ebcl_auth_status = False
            self.do_AUTHHEAD()
            self.wfile.write(b'No auth header received')
        elif self.authenticate(auth_header):
            ebcl_auth_status = True
            SimpleHTTPRequestHandler.do_GET(self)
        else:
            ebcl_auth_status = False
            self.do_AUTHHEAD()
            self.wfile.write(b'Invalid credentials')

    def authenticate(self, auth_header):
        encoded_credentials = auth_header.split(' ')[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        username, password = decoded_credentials.split(':')
        return username == self.username and password == self.password


class Server:
    def __init__(self, port, username, password, directory):
        self.port = port
        self.username = username
        self.password = password
        self.directory = directory
        self.httpd = None
        self.server_thread = None

    def start(self):
        handler = partial(
            AuthHTTPRequestHandler,
            username=self.username,
            password=self.password,
            directory=self.directory
        )
        self.httpd = HTTPServer(('', self.port), handler)
        print(f'Serving APT repository from {self.directory} on http://localhost:{self.port}')
        self.server_thread = threading.Thread(target=self.httpd.serve_forever)
        self.server_thread.start()

    def stop(self):
        if self.httpd:
            print("Stopping server...")
            self.httpd.shutdown()
            self.httpd.server_close()
            self.server_thread.join()
            print("Server stopped.")

    def get_last_auth_status(self):
        global ebcl_auth_status
        return ebcl_auth_status


def signal_handler(signum, frame):
    print(f"Received signal {signum}")
    server.stop()
    sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run an authenticated HTTPS server for APT repository')
    parser.add_argument('--port', type=int, default=8088, help='Port to run the server on')
    parser.add_argument('--username', required=True, help='Username for authentication')
    parser.add_argument('--password', required=True, help='Password for authentication')
    parser.add_argument('--directory', required=True, help='Directory containing the APT repository')
    args = parser.parse_args()

    server = Server(args.port, args.username, args.password, args.directory)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server.start()

    # Keep the main thread alive
    while True:
        signal.pause()
