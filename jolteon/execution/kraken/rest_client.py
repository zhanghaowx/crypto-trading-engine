import base64
import hashlib
import hmac
import os
import urllib.parse

import requests

from jolteon.core.time.time_manager import time_manager


class KrakenRESTClient:
    API_URL = "https://api.kraken.com"

    def __init__(self):
        assert os.environ.get(
            "KRAKEN_API_KEY"
        ), "Please set the KRAKEN_API_KEY environment variable"
        assert os.environ.get(
            "KRAKEN_API_SECRET"
        ), "Please set the KRAKEN_API_SECRET environment variable"
        self._api_key = os.environ.get("KRAKEN_API_KEY")
        self._api_secret = os.environ.get("KRAKEN_API_SECRET")

    def send_request(self, uri_path: str, data: dict):
        # A nonce is a number that uniquely identifies each call to the REST
        # API private endpoints. A nonce is required for all authenticated
        # calls to the REST API.
        #
        # A nonce is implemented as a counter that must be unique and must
        # increase with each call to the API. For example, assuming a starting
        # nonce value of 0, subsequent valid nonce values would be
        # 1, 2, 3, 4, and so on.
        #
        # Each API key has its own separate nonce, and the nonce value is
        # persistent, which means the most recently used nonce will remain
        # unchanged even if an API key is not used for some time.
        assert not hasattr(data, "nonce"), "Please don't set nonce manually!"
        nonce = str(int(time_manager().now().timestamp() * 1000))
        data["nonce"] = nonce

        headers = {
            "API-Key": self._api_key,
            "API-Sign": self._create_signature(uri_path, data),
        }
        req = requests.post(
            (KrakenRESTClient.API_URL + uri_path), headers=headers, data=data
        )
        return req

    def _create_signature(self, urlpath: str, data: dict) -> str:
        assert "nonce" in data

        post_data = urllib.parse.urlencode(data)
        encoded = (str(data["nonce"]) + post_data).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        mac = hmac.new(
            base64.b64decode(self._api_secret), message, hashlib.sha512
        )
        signature_digest = base64.b64encode(mac.digest())
        return signature_digest.decode()
