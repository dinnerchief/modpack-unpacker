from http.client import HTTPResponse
from urllib.request import urlopen
from urllib.parse import urlparse, unquote
from tempfile import TemporaryDirectory
from shutil import copy2

from logger import logger

import asyncio
import hashlib
import json
import os

class HashMismatchError(Exception):
    def __init__(self, *args, loaded_hash, orig_hash):
        super().__init__(*args)
        self.loaded_hash = loaded_hash
        self.orig_hash = orig_hash


def download_mod_link(project_id: str, file_id: str):
    cf = CurseforgeUnauthorized()
    return cf.API_URI + 'mods/%d/files/%d/download' % (project_id, file_id)


class Curseforge:
    async def download_url(self, project_id: str, file_id: str): pass
    async def file_info(self, project_id: str, file_id: str): pass
    async def download_file(self, project_id: str, file_id: str, dest_dir: str): pass


class CurseforgeAuthorized(Curseforge):
    def __init__(self, api_key: str):
        self.API_URI = 'https://api.curseforge.com/v1/'
        self.API_KEY = api_key
        self.timeout = 60
        pass

    async def download_url(self, project_id: str, file_id: str) -> str | None:
        url = self.API_URI + "mods/%d/files/%d/download-url" % (project_id, file_id)
        loop = asyncio.get_event_loop()
        res: HTTPResponse = await loop.run_in_executor(None, urlopen, url, None, self.timeout)
        return json.loads(res.read()).get("data", None)
    
    async def file_info(self, project_id: str, file_id: str):
        url = self.API_URI + "mods/%d/files/%d" % (project_id, file_id)
        loop = asyncio.get_event_loop()
        res: HTTPResponse = await loop.run_in_executor(None, urlopen, url, None, self.timeout)

        data = json.loads(res.read()).get("data", None)
    
        filename: str = data.get("fileName")
        download_url: str = data.get("downloadUrl")
        md5_hash: str | None = data.get("hashes", [])[1].get("value", None)

        return {
            "filename": filename,
            "download_url": download_url,
            "md5_hash": md5_hash
        }
    
    async def download_file(self, project_id: str, file_id: str, dest_dir: str) -> list[tuple[str, None] | tuple[str | None, Exception, str, str]]:
        info = await self.file_info(project_id, file_id)
        url = info.get("download_url")
        filename = info.get("filename")
        md5_hash = info.get("md5_hash")

        try:
            res: HTTPResponse # urllib returns a type depending on the protocol, but by default, it returns an alias of type Any
            with urlopen(url, timeout=60) as res:
                dest = os.path.join(dest_dir, filename)

                # Check cache
                if os.path.exists(dest):
                    if md5_hash is None:
                        logger.info("CACHED %s (without hashsum)" % dest)
                        return dest, None
                    
                    with open(dest, "rb") as f:
                        loaded_md5_hash = hashlib.md5(f.read())
                        
                        if loaded_md5_hash != md5_hash:
                            logger.warning("[projectID: %d] MD5 hash mismatch (loaded: %s, orig: %s)" % (project_id, loaded_md5_hash, md5_hash))
                            return dest, HashMismatchError(loaded_md5_hash, md5_hash), project_id, file_id
                    
                    logger.info("CACHED %s" % dest)
                    return dest, None

                logger.info("[projectID: %d] Downloading file %s to %s" % (project_id, url, dest))
                
                with TemporaryDirectory() as tmp_folder:
                    tmp_dest = os.path.join(tmp_folder, filename)
                    with open(tmp_dest, 'wb') as f:
                        f.write(res.read())
                        
                    # Validate MD5 hash
                    with open(tmp_dest, 'rb') as f:
                        loaded_md5_hash = hashlib.md5(f.read())

                        if loaded_md5_hash != md5_hash:
                            logger.error("[projectID: %d] MD5 hash mismatch (loaded: %s, orig: %s)" % (project_id, loaded_md5_hash, md5_hash))
                            return dest, HashMismatchError(loaded_md5_hash, md5_hash), project_id, file_id

                    copy2(tmp_dest, dest)

                return dest, None
        except Exception as err:
            logger.info("[projectID: %d] Error \"%s\"" % (project_id, str(err)))
            return None, err, project_id, file_id

class CurseforgeUnauthorized(Curseforge):
    def __init__(self):
        self.API_URI = 'https://www.curseforge.com/api/v1/'
        pass

    def download_file(self, project_id: str, file_id: str, dest_dir: str):
        url = self.API_URI + "mods/%d/files/%d/download" % (project_id, file_id)

        logger.info("[projectID: %d] Resolving download url..." % project_id)

        try:
            res: HTTPResponse # urllib returns a type depending on the protocol, but by default, it returns an alias of type Any
            with urlopen(url, timeout=60) as res:

                # After redirects from /download, you reached cdn url with filename
                res_url = res.geturl()
                parsed_url = urlparse(res_url)
                path = unquote(parsed_url.path)
                filename = os.path.basename(path)
                dest = os.path.join(dest_dir, filename)

                if os.path.exists(dest):
                    logger.info("CACHED %s (without hashsum)" % dest)
                    return dest, None

                logger.info("[projectID: %d] Downloading file %s to %s" % (project_id, res_url, dest))
                
                with TemporaryDirectory() as tmp_folder:
                    tmp_dest = os.path.join(tmp_folder, filename)
                    
                    with open(tmp_dest, 'wb') as f:
                        f.write(res.read())
                    copy2(tmp_dest, dest)
                
                return dest, None
        except Exception as err:
            logger.info("[projectID: %d] Error \"%s\"" % (project_id, str(err)))
            return None, err, project_id, file_id
