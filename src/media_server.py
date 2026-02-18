from fastapi import FastAPI, Response, HTTPException
# import libzim.reader # Check user environment if available, otherwise mock or comment out for now
import mimetypes
import hashlib

# Note: In a real deployment, ensure libzim is installed: pip install libzim
try:
    from libzim.reader import Archive
    LIBZIM_AVAILABLE = True
except ImportError:
    LIBZIM_AVAILABLE = False
    print("Warning: libzim not found. Media server will run in mock mode.")

app = FastAPI()

# Configuration
ZIM_FILE_PATH = "wikipedia_en_all_maxi.zim" 
# In production, this path should be configurable via env var

class MediaServer:
    def __init__(self, zim_path):
        self.zim_path = zim_path
        self.archive = None
        if LIBZIM_AVAILABLE:
            try:
                self.archive = Archive(zim_path)
            except Exception as e:
                print(f"Failed to load ZIM archive: {e}")

    def get_content(self, path):
        if not self.archive:
            raise Exception("Archive not loaded")
        entry = self.archive.get_entry_by_path(path)
        item = entry.get_item()
        return item.content

# Singleton instance
media_server = MediaServer(ZIM_FILE_PATH)

@app.get("/media/{filename}")
def get_media(filename: str):
    """
    Fetches raw image bytes from the ZIM file.
    Usage: GET /media/Apollo_11.jpg
    """
    # ZIM images are usually in the 'I' or '-' namespace depending on ZIM version
    # The snippet suggests 'I/' namespace
    entry_path = f"I/{filename}"
    
    try:
        if not LIBZIM_AVAILABLE:
             return Response(content=b"Mock Image Data", media_type="image/jpeg")

        content = media_server.get_content(entry_path)
        
        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(filename)
        
        return Response(content=content, media_type=mime_type or "image/jpeg")

    except KeyError:
        raise HTTPException(status_code=404, detail="Image not found in ZIM archive")
    except Exception as e:
        print(f"Error: {e}")
        # In prod, check if it's a 404-like error from libzim or real 500
        if "not found" in str(e).lower():
             raise HTTPException(status_code=404, detail="Image not found")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/commons-link/{filename}")
def redirect_commons(filename: str):
    """
    Helper to get the real Wikimedia Commons URL if needed.
    """
    url = get_commons_url(filename)
    return {"url": url}

def get_commons_url(filename):
    """
    Reconstructs the real Wikimedia Commons URL from a filename.
    """
    filename = filename.replace(" ", "_")
    # Wikipedia md5 structure
    md5_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()
    path_a = md5_hash[0]
    path_ab = md5_hash[0:2]
    
    return f"https://upload.wikimedia.org/wikipedia/commons/{path_a}/{path_ab}/{filename}"
