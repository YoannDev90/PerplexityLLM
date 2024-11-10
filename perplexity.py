import json
import os
import random
import threading
import time
import uuid
from typing import Dict, Iterable

import requests
import websocket

class Perplexity:
    def __init__(self, email: str = None):
        self.session = requests.Session()
        self.user_agent = {
            "User-Agent": "Ask/2.9.1/2406 (iOS; iPhone; Version 17.1) isiOSOnMac/false",
            "X-Client-Name": "Perplexity-iOS",
            "X-App-ApiClient": "ios"
        }
        self.session.headers.update(self.user_agent)
        
        self.email = email
        if email and ".perplexity_session" in os.listdir():
            self._recover_session(email)
        else:
            self._init_session_without_login()
            if email:
                self._login(email)
        
        self.t = self._get_t()
        self.sid = self._get_sid()
        self.n = 1
        self.base = 420
        self.queue = []
        self.finished = True
        self.last_uuid = None
        self.frontend_session_id = str(uuid.uuid4())
        
        assert self._ask_anonymous_user(), "Échec de la demande anonyme"
        
        self.ws = self._init_websocket()
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.start()
        self._auth_session()
        
        while not (self.ws.sock and self.ws.sock.connected):
            time.sleep(0.01)

    def _recover_session(self, email: str):
        with open(".perplexity_session", "r") as f:
            perplexity_session = json.loads(f.read())
        if email in perplexity_session:
            self.session.cookies.update(perplexity_session[email])
        else:
            self._login(email, perplexity_session)

    def _login(self, email: str, ps: dict = None):
        self.session.post(
            url="https://www.perplexity.ai/api/auth/signin-email",
            data={"email": email}
        )
        email_link = input("Collez le lien reçu par email : ")
        self.session.get(email_link)
        
        if ps is None:
            ps = {}
        ps[email] = self.session.cookies.get_dict()
        with open(".perplexity_session", "w") as f:
            f.write(json.dumps(ps))

    def _init_session_without_login(self):
        self.session.get(f"https://www.perplexity.ai/search/{uuid.uuid4()}")
        self.session.headers.update(self.user_agent)

    def _auth_session(self):
        self.session.get("https://www.perplexity.ai/api/auth/session")

    def _get_t(self):
        return format(random.getrandbits(32), "08x")

    def _get_sid(self):
        response = self.session.get(
            f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}"
        )
        return json.loads(response.text[1:])["sid"]

    def _ask_anonymous_user(self):
        response = self.session.post(
            f"https://www.perplexity.ai/socket.io/?EIO=4&transport=polling&t={self.t}&sid={self.sid}",
            data='40{"jwt":"anonymous-ask-user"}'
        )
        return response.text == "OK"

    def _start_interaction(self):
        self.finished = False
        if self.n == 9:
            self.n = 0
            self.base *= 10
        else:
            self.n += 1
        self.queue = []

    def _get_cookies_str(self):
        return "; ".join([f"{k}={v}" for k, v in self.session.cookies.get_dict().items()])

    def _init_websocket(self):
        def on_open(ws):
            ws.send("2probe")
            ws.send("5")

        def on_message(ws, message):
            if message == "2":
                ws.send("3")
            elif not self.finished:
                if message.startswith("42"):
                    content = json.loads(message[2:])[1]
                    if "mode" in content and content["mode"] == "copilot":
                        content["copilot_answer"] = json.loads(content["text"])
                    elif "mode" in content:
                        content.update(json.loads(content["text"]))
                        content.pop("text")
                    
                    if (not content.get("final", False)) or content.get("status") == "completed":
                        self.queue.append(content)
                    
                    if content.get("status") == "completed":
                        self.last_uuid = content.get("uuid")
                        self.finished = True
                elif message.startswith("43"):
                    message = json.loads(message[3:])[0]
                    if ("uuid" in message and message["uuid"] != self.last_uuid) or "uuid" not in message:
                        self.queue.append(message)
                        self.finished = True

        return websocket.WebSocketApp(
            f"wss://www.perplexity.ai/socket.io/?EIO=4&transport=websocket&sid={self.sid}",
            header=self.user_agent,
            cookie=self._get_cookies_str(),
            on_open=on_open,
            on_message=on_message,
            on_error=lambda ws, err: print(f"Erreur WebSocket : {err}")
        )

    def _s(self, query: str, mode: str = "concise", search_focus: str = "internet",
           attachments: list = None, language: str = "en-GB", in_page: str = None, in_domain: str = None):
        assert self.finished, "Recherche déjà en cours"
        assert mode in ["concise", "copilot"], "Mode invalide"
        assert len(attachments or []) <= 4, "Trop de pièces jointes : maximum 4"
        assert search_focus in ["internet", "scholar", "writing", "wolfram", "youtube", "reddit"], "Focus de recherche invalide"

        if in_page:
            search_focus = "in_page"
        if in_domain:
            search_focus = "in_domain"

        self._start_interaction()

        ws_message = f"{self.base + self.n}" + json.dumps([
            "perplexity_ask",
            query,
            {
                "version": "2.1",
                "source": "default",
                "frontend_session_id": self.frontend_session_id,
                "language": language,
                "timezone": "CET",
                "attachments": attachments or [],
                "search_focus": search_focus,
                "frontend_uuid": str(uuid.uuid4()),
                "mode": mode,
                "in_page": in_page,
                "in_domain": in_domain
            }
        ])

        self.ws.send(ws_message)

    def search(self, query: str, mode: str = "concise", search_focus: str = "internet",
               attachments: list = None, language: str = "en-GB", timeout: float = 30,
               in_page: str = None, in_domain: str = None) -> Iterable[Dict]:
        self._s(query, mode, search_focus, attachments, language, in_page, in_domain)
        start_time = time.time()

        while (not self.finished) or self.queue:
            if timeout and time.time() - start_time > timeout:
                self.finished = True
                yield {"error": "timeout"}
                return

            if self.queue:
                yield self.queue.pop(0)

    def search_sync(self, query: str, mode: str = "concise", search_focus: str = "internet",
                    attachments: list = None, language: str = "en-GB", timeout: float = 30,
                    in_page: str = None, in_domain: str = None) -> dict:
        self._s(query, mode, search_focus, attachments, language, in_page, in_domain)
        start_time = time.time()

        while not self.finished:
            if timeout and time.time() - start_time > timeout:
                self.finished = True
                return {"error": "timeout"}

        return self.queue.pop(-1) if self.queue else {"error": "no_result"}

    def close(self):
        self.ws.close()
        if self.email:
            with open(".perplexity_session", "r") as f:
                perplexity_session = json.loads(f.read())
            perplexity_session[self.email] = self.session.cookies.get_dict()
            with open(".perplexity_session", "w") as f:
                f.write(json.dumps(perplexity_session))
