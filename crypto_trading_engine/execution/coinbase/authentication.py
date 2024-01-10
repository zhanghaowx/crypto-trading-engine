import os
import secrets
import time
from typing import Union

import jwt
from cryptography.hazmat.primitives import serialization


class Authentication:
    def __init__(
        self,
        api_key: Union[str, None] = os.getenv("COINBASE_API_KEY"),
        api_secret: Union[str, None] = os.getenv("COINBASE_API_SECRET"),
    ):
        """
        Initialize the Authentication instance with API credentials for using
        the Coinbase Advanced Trade API.

        See more:
            https://docs.cloud.coinbase.com/advanced-trade-api/docs/rest-api-overview
        """

        assert (
            api_key
        ), "Please correctly set environment variable COINBASE_API_KEY"
        assert (
            api_secret
        ), "Please correctly set environment variable COINBASE_API_SECRET"

        self.api_key = api_key
        self.api_secret = api_secret.replace("\\n", "\n")
        self.service_name = "retail_rest_api_proxy"

    def generate_jwt(self, uri):
        """
        Generates a JWT (JSON Web Token) for an API call. Each JWT expires
        after 2 minutes, after which all requests are unauthenticated. A
        different JWT is needed for each unique API request.

        Args:
            uri: The URI to generate a JWT. Example:
                 ```
                 GET api.coinbase.com/api/v3/brokerage/accounts
                 ```
        Returns:
            A JWT (JSON Web Token)
        """
        private_key_bytes = self.api_secret.encode("utf-8")
        private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None
        )
        jwt_payload = {
            "sub": self.api_key,
            "iss": "coinbase-cloud",
            "nbf": int(time.time()),
            "exp": int(time.time()) + 60,
            "aud": [self.service_name],
            "uri": uri,
        }
        jwt_token = jwt.encode(
            jwt_payload,
            private_key,
            algorithm="ES256",
            headers={"kid": self.api_key, "nonce": secrets.token_hex()},
        )
        return jwt_token

    def generate_authorization_header(self, uri: str):
        return {
            "Authorization": f"Bearer {self.generate_jwt(uri)}",
        }
