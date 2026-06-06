import threading
import os
import re
import time
from flask import Flask, redirect, request, session, url_for, jsonify, copy_current_request_context
from flask_session import Session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["SESSION_TYPE"] = os.environ.get("SESSION_TYPE", "filesystem")

# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_PERMANENT'] = False
Session(app)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# --- MongoDB Setup ---
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["drive_data"]          
links_collection = db["folder_links"]    
# ---------------------

SCOPES = ['https://www.googleapis.com/auth/drive']
REDIRECT_URI = os.getenv("REDIRECT_URI")

copy_status = {
    "status": "idle",
    "message": "",
    "copied_files": 0,
    "total_files": 0
}

def build_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "project_id": os.getenv("GOOGLE_PROJECT_ID"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

@app.route('/')
def index():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Drive2Drive</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background: linear-gradient(to right, #4facfe, #00f2fe);
                color: #333;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .container {
                background: #fff;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                padding: 30px;
                max-width: 500px;
                width: 100%;
                text-align: center;
            }
            h1 {
                color: #4caf50;
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 10px;
                font-size: 16px;
                font-weight: bold;
                color: #555;
            }
            input[type="text"] {
                width: 100%;
                padding: 10px;
                margin-bottom: 20px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            button {
                background: linear-gradient(to right, #4caf50, #8bc34a);
                color: #fff;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
                transition: background 0.3s ease;
            }
            button:hover {
                background: linear-gradient(to right, #43a047, #7cb342);
            }
            a {
                text-decoration: none;
                color: #007bff;
                font-weight: bold;
                margin-top: 20px;
                display: inline-block;
            }
            a:hover {
                text-decoration: underline;
            }
        .footer {
            margin-top: 30px;
            text-align: center;
        }

        .footer img {
            width: 300px;
            border-radius: 50%;
            margin-top: 10px;
            height: 300px;
        }

        .footer h1 {
            font-size: 20px;
            color: #444;
            margin: 0;
        }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to Drive2Drive</h1>
            <form action="/copy" method="post">
                <label for="src_folder">Source Folder Link or ID:</label>
                <input type="text" id="src_folder" name="src_folder" placeholder="Enter Google Drive folder link or ID" required>
                <button type="submit">Start Copy</button>
            </form>
            <p><a href="/status">Check Copy Status</a></p>
             <div class="footer">
        <h1>Created By Mr Shah</h1>
        <img src="https://skillspectrum.vercel.app/Hamza.jpg" alt="Mr Shah">
    </div>
        </div>
    </body>
    </html>
    '''

@app.route('/authorize')
def authorize():
    flow = build_flow()
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    if 'state' not in session:
        return "Session expired. <a href='/'>Try again</a>.", 400
    flow = build_flow()
    flow.fetch_token(authorization_response=request.url)
    session['credentials'] = credentials_to_dict(flow.credentials)
    return redirect(url_for('index'))

@app.route('/status')
def status():
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Copy Status</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background: linear-gradient(to right, #4facfe, #00f2fe);
                color: #333;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }
            .container {
                background: #fff;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                padding: 20px;
                max-width: 500px;
                width: 100%;
                text-align: center;
            }
            h1 {
                color: #4caf50;
                margin-bottom: 20px;
            }
            p {
                margin: 10px 0;
                font-size: 16px;
            }
            .progress-bar-container {
                border: 1px solid #ddd;
                border-radius: 5px;
                width: 100%;
                height: 20px;
                background-color: #f3f3f3;
                overflow: hidden;
                margin: 20px 0;
            }
            .progress-bar {
                height: 100%;
                background: linear-gradient(to right, #4caf50, #8bc34a);
                width: 0%;
                transition: width 0.5s ease;
            }
            a {
                text-decoration: none;
                color: #007bff;
                font-weight: bold;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
        <script>
            function fetchStatus() {
                fetch('/status_json')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('status').innerText = data.status;
                        document.getElementById('message').innerText = data.message;
                        document.getElementById('copied_files').innerText = data.copied_files;
                        document.getElementById('total_files').innerText = data.total_files;
                        document.getElementById('progress_bar').style.width = data.progress + '%';
                    })
                    .catch(error => console.error('Error fetching status:', error));
            }
            window.onload = fetchStatus;
            setInterval(fetchStatus, 2000);
        </script>
    </head>
    <body>
        <div class="container">
            <h1>Copy Status</h1>
            <p><strong>Status:</strong> <span id="status"></span></p>
            <p><strong>Message:</strong> <span id="message"></span></p>
            <p><strong>Copied Files:</strong> <span id="copied_files">0</span> / <span id="total_files">0</span></p>
            <div class="progress-bar-container">
                <div id="progress_bar" class="progress-bar"></div>
            </div>
            <p><a href="/">Go Back to Home</a></p>
        </div>
    </body>
    </html>
    '''

@app.route('/status_json')
def status_json():
    total_files = copy_status.get("total_files", 0)
    copied_files = copy_status.get("copied_files", 0)
    progress = (copied_files / total_files * 100) if total_files > 0 else 0
    return jsonify({
        "status": copy_status.get("status"),
        "message": copy_status.get("message"),
        "copied_files": copied_files,
        "total_files": total_files,
        "progress": round(progress, 2)
    })

@app.route('/copy', methods=['POST'])
def copy():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    # --- Check MongoDB Limit ---
    try:
        existing_links_count = links_collection.count_documents({})
        if existing_links_count >= 2:
            copy_status.update({
                "status": "error",
                "message": "Copy limit reached! You cannot copy more than 2 links.",
                "copied_files": 0,
                "total_files": 0
            })
            return redirect(url_for('status'))
    except Exception as mongo_err:
        print(f"Failed to check MongoDB limit: {mongo_err}")
    # ----------------------------

    # Reset shared state to start a valid transfer
    copy_status.update({
        "status": "in_progress",
        "message": "Initializing...",
        "copied_files": 0,
        "total_files": 0
    })

    src_folder_input = request.form['src_folder']

    # --- Save Link to MongoDB ---
    try:
        links_collection.insert_one({
            "folder_link_or_id": src_folder_input,
            "timestamp": time.time()
        })
    except Exception as mongo_err:
        print(f"Failed to save to MongoDB: {mongo_err}")
    # ----------------------------

    credentials = Credentials(**session['credentials'])
    drive = build('drive', 'v3', credentials=credentials)
    src_id = extract_folder_id(src_folder_input)

    @copy_current_request_context
    def thread_target():
        start_copy(drive, src_id)

    threading.Thread(target=thread_target).start()

    return redirect(url_for('status'))

def start_copy(drive, src_id):
    try:
        copy_status["message"] = "Counting files..."
        total_files = count_files(drive, src_id)
        copy_status["total_files"] = total_files
        copy_status["message"] = f"{total_files} files found. Starting copy..."
        copy_folder_contents(drive, drive, src_id, 'root')
        copy_status["status"] = "done"
        copy_status["message"] = "Copy completed successfully."
    except Exception as e:
        copy_status["status"] = "error"
        copy_status["message"] = str(e)

def copy_folder_contents(src_service, dst_service, src_folder_id, dst_parent_id):
    folder_meta = src_service.files().get(fileId=src_folder_id, fields='name').execute()
    dst_folder_metadata = {
        'name': folder_meta['name'],
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [dst_parent_id]
    }
    dst_folder = dst_service.files().create(body=dst_folder_metadata, fields='id').execute()
    dst_folder_id = dst_folder['id']

    query = f"'{src_folder_id}' in parents and trashed = false"
    items = []
    page_token = None

    while True:
        response = src_service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        items.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            copy_folder_contents(src_service, dst_service, item['id'], dst_folder_id)
        else:
            file_metadata = {'name': item['name'], 'parents': [dst_folder_id]}
            dst_service.files().copy(fileId=item['id'], body=file_metadata).execute()
            copy_status["copied_files"] += 1
            copy_status["message"] = f"Copied {item['name']}"

def count_files(drive, folder_id):
    query = f"'{folder_id}' in parents and trashed = false"
    total = 0
    page_token = None

    while True:
        response = drive.files().list(
            q=query,
            fields="nextPageToken, files(id, mimeType)",
            pageToken=page_token
        ).execute()
        items = response.get('files', [])
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                total += count_files(drive, item['id'])
            else:
                total += 1
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return total

def extract_folder_id(link_or_id):
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', link_or_id)
    return match.group(1) if match else link_or_id.strip()

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

if __name__ == "__main__":
    # This is only fallback for local testing, Gunicorn bypasses this block
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
