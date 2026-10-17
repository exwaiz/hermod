"""Loopback-only, synthetic test service. Never serves local files or logs bodies."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

HTML = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Hermod local fixture</title>
<h1>Hermod fixture</h1><main data-thread="REF">
<input type="search" aria-label="Find conversation"><a href="/threads/second">Second fixture conversation</a>
<label>Message<textarea aria-label="Message"></textarea></label>
<label>Receipt<input aria-label="Receipt"></label><button>Send</button>
<div data-submitted=""></div><div role="status" aria-label="Assistant response" data-state="idle"></div>
</main><script>
const main=document.querySelector('main'), status=document.querySelector('[role=status]');
document.querySelector('button').onclick=async()=>{
 const receipt=document.querySelector('[aria-label=Receipt]').value;
 const text=document.querySelector('[aria-label=Message]').value;
 const response=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({receipt,text,thread:main.dataset.thread})});
 if(!response.ok)return;
 document.querySelector('[data-submitted]').dataset.submitted=receipt;
 status.dataset.receipt=receipt;status.dataset.state='streaming';status.textContent='partial';
 if(main.dataset.thread==='fixture:slow')return;
 setTimeout(()=>{status.textContent='Fixture reply: '+text;status.dataset.state='complete';},120);
};</script></html>'''


class FixtureSite:
    def __init__(self, port=0):
        self.receipts = {}
        site = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                name = self.path.rsplit('/', 1)[-1]
                if name not in {'demo', 'second', 'auth', 'changed', 'slow', 'mismatch', 'human'}:
                    self.send_error(404)
                    return
                html = HTML.replace('REF', 'fixture:' + ('other' if name == 'mismatch' else name))
                if name == 'auth':
                    html = '<h1>Sign in required</h1>'
                if name == 'human':
                    html = '<h1>Manual security check</h1>'
                if name == 'changed':
                    html = html.replace('<button>Send</button>', '<button>Unknown action</button>')
                body = html.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                if self.path != '/api/send' or not 0 < length <= 60000:
                    self.send_error(400)
                    return
                value = json.loads(self.rfile.read(length))
                site.receipts.setdefault(value['receipt'], value)
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
