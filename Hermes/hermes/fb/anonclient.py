from firebase.firebase import firebase as _firebase



#https://firebase.google.com/docs/database/rest/auth#python
import google
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
import uuid
import threading
import logging
class FBAnonClient:
    def __init__(self, credentialFile, dbURL):
        self.logger = logging.getLogger(f"{self.__class__.__name__}")

        # Define the required scopes
        scopes = [
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/firebase.database"
        ]

        # Authenticate a credential with the service account
        credentials = service_account.Credentials.from_service_account_file(
            credentialFile, scopes=scopes)
        # Use the credentials object to authenticate a Requests session.
        # authed_session = AuthorizedSession(credentials)
        # response = authed_session.get(
        #     "https://<DATABASE_NAME>.firebaseio.com/users/ada/name.json")

        # Or, use the token directly, as described in the "Authenticate with an
        # access token" section below. (not recommended)

        # this lib uses rest calls
        self.firebase = _firebase.FirebaseApplication(dbURL)
        uid = uuid.uuid4()
        def refresh_fb_token(firebase, uid):
            # Refresh the token
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            access_token = credentials.token
            expiration_time = credentials.expiry.astimezone()
            # Print the token and expiration time in local timezone
            self.logger.warning(f"Refresh FB Access Token: {access_token[0:25]}... Expiry: {expiration_time}")
            self.firebase.setAccessToken(access_token)
            # Schedule the next refresh in 1 hour
            self.timer = threading.Timer(3600, refresh_fb_token, args=[self.firebase, uid])
            self.timer.start()
        # Start the first refresh
        refresh_fb_token(self.firebase, uid)
    def getFB(self):
        return self.firebase
    def stop(self):
        self.timer.cancel()