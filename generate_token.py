import os
import google_auth_oauthlib.flow

# Path to your client secrets file downloaded from Google Cloud Console
CLIENT_SECRETS_FILE = "client_sec.json"
# Scope that allows uploading to YouTube (you can add more scopes if needed)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube'
    ]

def get_and_save_token(token_file):
    # Run the OAuth flow using a local server; this will open your browser
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Save the credentials to the token file
    with open(token_file, "w") as f:
        f.write(creds.to_json())
    print(f"Token saved to {token_file}")

if __name__ == '__main__':
    token_file = input("Enter token file name (e.g. token.json): ").strip()
    get_and_save_token(token_file)
