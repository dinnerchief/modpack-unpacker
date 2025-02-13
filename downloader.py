from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPResponse
from urllib.request import urlopen
from urllib.parse import urlparse, unquote

from logger import logger

import asyncio
import time
import os

API_URI = 'https://www.curseforge.com/api/v1/'

# async def mod_info(project_id: str, file_id: str):
#     url = API_URI + 'mods/%d/files/%d' % (project_id, file_id)
#     loop = asyncio.get_event_loop()

#     res: HTTPResponse = await loop.run_in_executor(None, urlopen, url, None, 60)
#     return json.loads(res.read())

def download_mod_link(project_id: str, file_id: str):
    return API_URI + 'mods/%d/files/%d/download' % (project_id, file_id)

def download_mod(project_id: str, file_id: str, dest_dir: str):
    url = download_mod_link(project_id, file_id)
    
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
                logger.info("CACHED %s" % dest)
                return dest, None

            logger.info("[projectID: %d] Downloading file %s to %s" % (project_id, res_url, dest))
            
            chunk_size = 1024*16 # 16KB
            with open(dest, 'wb') as f:
                while True:
                    chunk = res.read(chunk_size)
                    if chunk: f.write(chunk)
                    break
            
            return dest, None
    except Exception as err:
        logger.info("[projectID: %d] Error \"%s\"" % (project_id, str(err)))
        return None, err, project_id, file_id

async def download_mods(manifest, out_dir) -> list[tuple[str, None] | tuple[None, Exception, str, str]]:
    results = []
    files = manifest["files"]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop = asyncio.get_event_loop()
        tasks = []
        
        for file in files:
            pid = file["projectID"]
            fid = file["fileID"]
            tasks.append(loop.run_in_executor(executor, download_mod, pid, fid, out_dir))
        
        retry_counters = dict()
        while len(tasks) > 0:
            retry = []
            for result in await asyncio.gather(*tasks):
                if result[1] == None: # if not err
                    results.append(result)
                    continue

                # err = result[1]
                pid = result[2]
                fid = result[3]

                retry_counters[pid] = 1 if retry_counters.get(pid) == None else retry_counters.get(pid) + 1
                if retry_counters[pid] > 2:
                    results.append(result)
                    continue
                
                logger.info("[projectID: %s] Retrying... %d" % (pid, retry_counters.get(pid)))
                time.sleep(1)
                retry.append(loop.run_in_executor(executor, download_mod, pid, fid, out_dir))
            
            tasks = []
            
            if len(retry) > 0:
                tasks = retry
    
    return results