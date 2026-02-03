import base64
import binascii
import sqlite3
from secrets import token_hex
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
from passlib.context import CryptContext
from starlette import status

from config import DATABASE_PATH

class Authenticator:

    def __init__(self):
        self.db_connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


    def add_team(self, _id: str):
        cursor = self.db_connection.execute("SELECT * FROM teams WHERE id = ?;", (_id,))
        res = cursor.fetchone()

        if res is not None:
            raise RuntimeError(f"Team {_id} already exists")

        token = token_hex(16)
        _ = self.db_connection.execute(
            "INSERT INTO teams (id, token) VALUES (?, ?)",
            (_id, self.pwd_context.hash(token))
        )
        self.db_connection.commit()

        return base64.b64encode(token.encode()).decode()

    def add_admin(self, name: str, password: str):
        _ = self.db_connection.execute(
            "INSERT OR IGNORE INTO admins VALUES (?, ?);",
            (name, self.pwd_context.hash(password)),
        )
        self.db_connection.commit()

    def authenticate_admin(self, name: str, password: str):
        cursor = self.db_connection.execute(
            "SELECT password FROM admins WHERE name = ?;",
            (name,),
        )

        result = cursor.fetchone()
        if result is None:
            return False

        return self.pwd_context.verify(password, result[0])

    def authenticate_team(self, token: str):
        try:
            decoded_token = base64.b64decode(token.encode()).decode()
        except (binascii.Error, UnicodeDecodeError):
            raise RuntimeError("Token is not base64 encoded.")


        cursor = self.db_connection.execute(
            "SELECT id, token FROM teams;",
        )
        res = cursor.fetchall()

        for tup in res:
            if self.pwd_context.verify(decoded_token, tup[1]):
                return tup[0]

        return None


oauth2_scheme = OAuth2AuthorizationCodeBearer(authorizationUrl="auth/verify", tokenUrl="/auth/issue-token")

async def authenticate(token: Annotated[str, Depends(oauth2_scheme)]):
    authenticator = Authenticator()
    try:
        team_id = authenticator.authenticate_team(token)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid."
        )

    return team_id

