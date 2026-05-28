"""
Profile Cloud Sync.
- Firebase Firestore: metadata + atomic locks (gpm_profiles collection)
- HuggingFace: zip profile data (profiles/{id}.zip)
"""

import json
import logging
import os
import platform
import sys
import tempfile
import time
import traceback
import zipfile

# Fix for Nuitka --windows-disable-console: sys.stderr/stdout are None → tqdm crashes
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")

import firebase_admin
from firebase_admin import credentials, firestore
from huggingface_hub import HfApi, create_repo

# === LOGGING ===
# Exe mode: __file__ points to temp dir, use sys.argv[0] or sys.executable instead
if getattr(sys, 'frozen', False):
    _app_dir = os.path.dirname(sys.executable)
elif sys.argv and not os.path.basename(sys.argv[0]).lower().startswith('python'):
    _app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    _app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_dir = os.path.join(_app_dir, "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "profile_sync.log")

logger = logging.getLogger("profile_sync")
logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)
logger.info(f"=== profile_sync loaded, app_dir={_app_dir}, log={_log_file} ===")

# === WHITELIST: only these files/dirs get zipped ===

INCLUDE_ROOT_FILES = [
    "Local State",
    "First Run",
    "first_party_sets.db",
]

INCLUDE_DEFAULT_FILES = [
    "Preferences",
    "Secure Preferences",
    "Favicons",
    "Favicons-journal",
    "History",
    "History-journal",
    "Login Data",
    "Login Data-journal",
    "Login Data For Account",
    "Login Data For Account-journal",
    "Web Data",
    "Web Data-journal",
    "Shortcuts",
    "Shortcuts-journal",
    "Top Sites",
    "Top Sites-journal",
    "Bookmarks",
    "DIPS",
    "trusted_vault.pb",
    "PreferredApps",
    "BookmarkMergedSurfaceOrdering",
]

INCLUDE_DEFAULT_DIRS = [
    "Network",
    "Local Storage",
    "Session Storage",
    "IndexedDB",
    "Extension State",
    "Extension Rules",
    "Extension Scripts",
    "GPMSoft",
    "blob_storage",
    "Sync Data",
    "shared_proto_db",
]

UPLOAD_RETRIES = 5
RETRY_DELAY = 2

COLLECTION = "gpm_profiles"


def get_machine_id():
    return platform.node() or "unknown"


# ============================================================
# Firebase init (singleton)
# ============================================================

_fb_db = None


def get_firestore_db(service_account_path):
    """Init Firebase and return Firestore client. Singleton."""
    global _fb_db
    if _fb_db is not None:
        return _fb_db
    logger.info(f"Initializing Firebase from {service_account_path} (exists={os.path.isfile(service_account_path)})")
    try:
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred, name="gpm_sync")
    except ValueError:
        pass  # App already exists
    app = firebase_admin.get_app("gpm_sync")
    _fb_db = firestore.client(app)
    logger.info("Firebase initialized OK")
    return _fb_db


# ============================================================
# Firebase profile operations
# ============================================================

def fb_create_profile(db, profile_id, meta):
    """Create profile doc in Firestore. Returns (True, msg) or (False, error)."""
    try:
        doc = {
            "name": meta.get("name", ""),
            "proxy": meta.get("proxy", ""),
            "note": meta.get("note", ""),
            "automation": int(meta.get("automation", 0)),
            "created_at": meta.get("created_at", ""),
            "running_on": "",
            "running_since": None,
            "deleted": False,
        }
        db.collection(COLLECTION).document(profile_id).set(doc)
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_update_profile(db, profile_id, data):
    """
    Atomically update profile metadata only if not running on another machine.
    Returns (True, "OK") or (False, reason).
    """
    doc_ref = db.collection(COLLECTION).document(profile_id)
    transaction = db.transaction()
    machine = get_machine_id()

    @firestore.transactional
    def _update(transaction, doc_ref):
        snap = doc_ref.get(transaction=transaction)
        if not snap.exists:
            # Not on cloud yet — create it
            doc = dict(data)
            doc.setdefault("running_on", "")
            doc.setdefault("running_since", None)
            doc.setdefault("deleted", False)
            transaction.set(doc_ref, doc)
            return True, "OK"
        current = snap.to_dict()
        running = current.get("running_on", "")
        if running and running != machine:
            return False, f"Profile is in use on {running}"
        if current.get("deleted"):
            return False, "Profile has been deleted"
        transaction.update(doc_ref, data)
        return True, "OK"

    try:
        return _update(transaction, doc_ref)
    except Exception as e:
        return False, str(e)


def fb_acquire_lock(db, profile_id, machine_id, meta=None):
    """
    Atomically acquire running lock via Firestore transaction.
    If doc doesn't exist, auto-creates it with meta (for existing local profiles).
    Returns (True, "OK") or (False, "running on MACHINE").
    """
    doc_ref = db.collection(COLLECTION).document(profile_id)
    transaction = db.transaction()

    @firestore.transactional
    def _acquire(transaction, doc_ref):
        snap = doc_ref.get(transaction=transaction)
        if not snap.exists:
            # Profile exists locally but not on cloud — auto-create with lock
            doc = {
                "name": (meta or {}).get("name", ""),
                "proxy": (meta or {}).get("proxy", ""),
                "note": (meta or {}).get("note", ""),
                "automation": int((meta or {}).get("automation", 0)),
                "created_at": (meta or {}).get("created_at", ""),
                "running_on": machine_id,
                "running_since": firestore.SERVER_TIMESTAMP,
                "deleted": False,
            }
            transaction.set(doc_ref, doc)
            return True, "OK"
        data = snap.to_dict()
        if data.get("deleted"):
            return False, "Profile has been deleted"
        current = data.get("running_on", "")
        if current and current != machine_id:
            return False, f"Running on {current}"
        transaction.update(doc_ref, {
            "running_on": machine_id,
            "running_since": firestore.SERVER_TIMESTAMP,
        })
        return True, "OK"

    try:
        return _acquire(transaction, doc_ref)
    except Exception as e:
        return False, str(e)


def fb_get_running_on(db, profile_id):
    """Get the machine_id currently holding the lock. Returns string or None."""
    try:
        snap = db.collection(COLLECTION).document(profile_id).get()
        if not snap.exists:
            return None
        return snap.to_dict().get("running_on", "") or None
    except Exception:
        return None


def fb_release_lock(db, profile_id):
    """Clear running lock. Returns (True, msg) or (False, error)."""
    try:
        db.collection(COLLECTION).document(profile_id).update({
            "running_on": "",
            "running_since": None,
        })
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_request_stop(db, profile_id, requester_machine_id):
    """Request another machine to stop this profile. Returns (True, msg) or (False, error)."""
    try:
        db.collection(COLLECTION).document(profile_id).update({
            "stop_requested_by": requester_machine_id,
            "stop_requested_at": firestore.SERVER_TIMESTAMP,
        })
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_check_stop_request(db, profile_id):
    """Check if someone requested stop for this profile. Returns requester machine_id or None."""
    try:
        snap = db.collection(COLLECTION).document(profile_id).get()
        if not snap.exists:
            return None
        return snap.to_dict().get("stop_requested_by", "") or None
    except Exception:
        return None


def fb_clear_stop_request(db, profile_id):
    """Clear stop request. Returns (True, msg) or (False, error)."""
    try:
        db.collection(COLLECTION).document(profile_id).update({
            "stop_requested_by": "",
            "stop_requested_at": None,
        })
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_force_acquire_lock(db, profile_id, machine_id):
    """Force overwrite running_on — used after timeout. Returns (True, msg) or (False, error)."""
    try:
        db.collection(COLLECTION).document(profile_id).update({
            "running_on": machine_id,
            "running_since": firestore.SERVER_TIMESTAMP,
            "stop_requested_by": "",
            "stop_requested_at": None,
        })
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_delete_profile(db, profile_id):
    """
    Soft-delete profile on Firestore.
    Sets deleted=True and clears running_on (in case of stale lock).
    Returns (True, "OK") or (False, reason).
    """
    try:
        doc_ref = db.collection(COLLECTION).document(profile_id)
        snap = doc_ref.get()
        if not snap.exists:
            return True, "Not on cloud"
        doc_ref.update({"deleted": True, "running_on": "", "running_since": None})
        return True, "OK"
    except Exception as e:
        return False, str(e)


def fb_check_deleted(db, profile_id):
    """Check if profile is soft-deleted. Returns True if deleted."""
    try:
        snap = db.collection(COLLECTION).document(profile_id).get()
        if not snap.exists:
            return False
        return snap.to_dict().get("deleted", False)
    except Exception:
        return False


def fb_sync_profiles(db):
    """
    Query all gpm_profiles docs (including deleted).
    Returns (list_of_dicts, None) or (None, error).
    Each dict has: id, name, proxy, note, automation, created_at, running_on, deleted.
    """
    try:
        docs = db.collection(COLLECTION).get()
        results = []
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            results.append(d)
        return results, None
    except Exception as e:
        return None, str(e)


# ============================================================
# HuggingFace helpers (retry, repo, upload/download zip)
# ============================================================

_hf_api_cache = {}


def _get_api(token):
    """Get cached HfApi instance — avoids repeated whoami calls that trigger rate limit."""
    if token not in _hf_api_cache:
        logger.info(f"Creating HfApi (token={token[:6]}...{token[-4:] if token else 'None'})")
        _hf_api_cache[token] = HfApi(token=token)
    return _hf_api_cache[token]


def _retry(fn, retries=UPLOAD_RETRIES, delay=RETRY_DELAY):
    """Call fn(), retry up to `retries` times on failure."""
    last_err = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            logger.warning(f"Retry {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    logger.error(f"All {retries} retries failed: {last_err}\n{traceback.format_exc()}")
    raise last_err


def _upload_bytes(api, data_bytes, path_in_repo, repo_id):
    """Upload bytes to HF via temp file, with retry."""
    tmp_fd, tmp_path = tempfile.mkstemp()
    try:
        os.write(tmp_fd, data_bytes)
        os.close(tmp_fd)
        _retry(lambda: api.upload_file(
            path_or_fileobj=tmp_path,
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="dataset",
        ))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _delete_file(api, path_in_repo, repo_id):
    """Delete file from HF, with retry."""
    _retry(lambda: api.delete_file(
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
    ))


def ensure_repo(repo_id, token):
    """Check if HF repo exists, create as private if not."""
    try:
        api = _get_api(token)
        try:
            api.dataset_info(repo_id)
            logger.info(f"HF repo '{repo_id}' exists")
        except Exception:
            logger.info(f"Creating HF repo '{repo_id}'...")
            create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True, token=token)
            logger.info(f"HF repo '{repo_id}' created")
        return True, "OK"
    except Exception as e:
        logger.error(f"ensure_repo failed: {e}\n{traceback.format_exc()}")
        return False, str(e)


# ============================================================
# Profile zip/unzip
# ============================================================

def zip_profile(profile_path, output_zip):
    """Zip only whitelisted files from profile_path."""
    try:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in INCLUDE_ROOT_FILES:
                fpath = os.path.join(profile_path, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, fname)

            default_dir = os.path.join(profile_path, "Default")
            if not os.path.isdir(default_dir):
                return True, "No Default dir, zipped root only"

            for fname in INCLUDE_DEFAULT_FILES:
                fpath = os.path.join(default_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, os.path.join("Default", fname))

            for dirname in INCLUDE_DEFAULT_DIRS:
                dirpath = os.path.join(default_dir, dirname)
                if not os.path.isdir(dirpath):
                    continue
                for root, _, files in os.walk(dirpath):
                    for f in files:
                        if f in ("LOCK", "LOG", "LOG.old"):
                            continue
                        full = os.path.join(root, f)
                        arcname = os.path.join("Default", dirname, os.path.relpath(full, dirpath))
                        zf.write(full, arcname)

        return True, output_zip
    except Exception as e:
        return False, str(e)


def unzip_profile(zip_path, profile_path):
    """Extract zip into profile_path, overwriting existing files."""
    try:
        os.makedirs(profile_path, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(profile_path)
        return True, "OK"
    except Exception as e:
        return False, str(e)


# ============================================================
# Profile upload/download (HuggingFace)
# ============================================================

def download_profile(profile_id, profile_path, repo_id, token):
    """Download zip from HF and extract."""
    try:
        logger.info(f"Downloading profile {profile_id} from HF...")
        api = _get_api(token)
        local_zip = api.hf_hub_download(repo_id=repo_id,
                                         filename=f"profiles/{profile_id}.zip",
                                         repo_type="dataset")
        logger.info(f"Downloaded to {local_zip}, extracting to {profile_path}")
        ok, msg = unzip_profile(local_zip, profile_path)
        logger.info(f"Extract result: ok={ok}, msg={msg}")
        return ok, msg
    except Exception as e:
        logger.error(f"download_profile failed: {e}\n{traceback.format_exc()}")
        return False, str(e)


def upload_profile(profile_id, profile_path, repo_id, token):
    """Zip profile and upload to HF, with retry."""
    tmp_zip = None
    try:
        logger.info(f"Uploading profile {profile_id} from {profile_path}...")
        api = _get_api(token)
        tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
        os.close(tmp_fd)

        ok, msg = zip_profile(profile_path, tmp_zip)
        if not ok:
            logger.error(f"Zip failed: {msg}")
            return False, f"Zip failed: {msg}"

        zip_size = os.path.getsize(tmp_zip)
        logger.info(f"Zip created: {tmp_zip} ({zip_size} bytes), uploading...")
        _retry(lambda: api.upload_file(
            path_or_fileobj=tmp_zip,
            path_in_repo=f"profiles/{profile_id}.zip",
            repo_id=repo_id,
            repo_type="dataset",
        ))
        logger.info(f"Upload OK for {profile_id}")
        return True, "OK"
    except Exception as e:
        logger.error(f"upload_profile failed: {e}\n{traceback.format_exc()}")
        return False, str(e)
    finally:
        if tmp_zip:
            try:
                os.unlink(tmp_zip)
            except OSError:
                pass


def delete_profile_zip(profile_id, repo_id, token):
    """Delete profile zip from HF."""
    try:
        api = _get_api(token)
        try:
            _delete_file(api, f"profiles/{profile_id}.zip", repo_id)
        except Exception:
            pass
        return True, "OK"
    except Exception as e:
        return False, str(e)
