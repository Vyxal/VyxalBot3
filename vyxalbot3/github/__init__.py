from datetime import datetime
from typing import Any, cast

from aiohttp import ClientSession
from gidgethub.aiohttp import GitHubAPI
from gidgethub.apps import get_jwt as get_github_jwt

from vyxalbot3.util import autocache


class AppGitHubAPI(GitHubAPI):
    def __init__(
        self, session: ClientSession, account: str, app_id: str, private_key: str
    ):
        super().__init__(session, account)
        self.app_id = app_id
        self.private_key = private_key

    @autocache
    async def app_token(self):
        jwt = get_github_jwt(app_id=self.app_id, private_key=self.private_key)
        async for installation in self.getiter("/app/installations", jwt=jwt):
            if installation["account"]["login"] == self.requester:
                token_payload = cast(
                    dict[str, Any],
                    await self.post(
                        f"/app/installations/{installation["id"]}/access_tokens",
                        data=b"",
                        jwt=jwt,
                    ),
                )
                return (
                    datetime.fromisoformat(token_payload["expires_at"]),
                    token_payload["token"],
                )
        raise Exception(f"Could not find installation named {self.requester}")
