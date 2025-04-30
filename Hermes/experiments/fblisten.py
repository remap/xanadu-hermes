from firebase_admin import credentials, db # pip install firebase-admin
import threading

firebase_config = {
    "authDomain": "xanadu-f5762.firebaseapp.com",
    "databaseURL": "https://xanadu-f5762-default-rtdb.firebaseio.com",
    "projectId": "xanadu-f5762",
    "storageBucket": "xanadu-f5762.firebasestorage.app",
    "messagingSenderId": "675711420129",
    "appId": "1:675711420129:web:6ef145f54f7a22b70ad9a0",
    "measurementId": "G-5H8HVP142B"
}

# Load Firebase credentials
cred = credentials.Certificate("xanadu-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': firebase_config['databaseURL']
})

# https://console.firebase.google.com/u/0/project/xanadu-f5762/database/xanadu-f5762-default-rtdb/data
# Reference the database path to monitor
listenPath = "/dev-xanadu/ch/cue"
ref = db.reference(listenPath)

# Listen for data changes
def firebaseEventListener(event):
    e = { "type": event.event_type, "path" : f"{listenPath}{event.path}", "data": event.data}
    print(e)

# Run the listener in a separate thread
listener_thread = threading.Thread(target=lambda : ref.listen(firebaseEventListener))
listener_thread.daemon = True
listener_thread.start()

# Keep the main thread alive
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Listener stopped.")
