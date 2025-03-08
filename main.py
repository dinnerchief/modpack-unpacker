from curseforge import CurseforgeUnauthorized, CurseforgeAuthorized, download_mod_link
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from logger import logger
from shutil import copy2

import asyncio
import time
import json
import sys
import os


async def download_mods(manifest, out_dir, api_key: str | None) -> list[tuple[str, None] | tuple[None, Exception, str, str]]:
    logger.info("Start downloading mods")

    cf = CurseforgeUnauthorized() if api_key is None else CurseforgeAuthorized(api_key)
    
    results = []
    files = manifest["files"]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop = asyncio.get_event_loop()
        tasks = []
        
        for file in files:
            pid = file["projectID"]
            fid = file["fileID"]
            tasks.append(loop.run_in_executor(executor, cf.download_file, pid, fid, out_dir))
        
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
                retry.append(loop.run_in_executor(executor, cf.download_file, pid, fid, out_dir))
            
            tasks = []
            
            if len(retry) > 0:
                tasks = retry
    
    return results


def extract_overrides(zf: ZipFile, dest: str):
    logger.info("Start extracting overrides folder")
    # merge overrides with modpack folder
    try:
        with TemporaryDirectory() as temp_dir:
            for info in zf.filelist:
                if not info.filename.startswith("overrides/"):
                    continue
                
                extract_tmp_path = os.path.join(temp_dir, info.filename[10:]) # len("overrides/") = 10
                extract_path = os.path.join(dest, info.filename[10:])

                # extract file to tmp
                os.makedirs(os.path.dirname(extract_tmp_path), exist_ok=True)
                with open(extract_tmp_path, "wb") as f:
                    f.write(zf.read(info))

                # copy to dest
                os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                copy2(extract_tmp_path, extract_path)
        
        logger.info("overrides folder sucessfull extracted")

    except KeyError as e:
        logger.info("overrides folder not found. Skip")
        pass # pass, if overrides does't exists


async def main(modpack_filepath):
    if not os.path.exists(modpack_filepath):
        logger.error("Path %s does not exists!" % modpack_filepath)
        exit()

    name = os.path.splitext(modpack_filepath)[0]
    name = os.path.basename(name)
    modpack_dir = 'modpacks/' + name
    os.makedirs(modpack_dir, exist_ok=True)

    # logger.info("Extracting %s to folder %s" % (name, modpack_dir))
    
    # if not os.path.exists(modpack_dir):
    #     with ZipFile(modpack_filepath, 'r') as zf:
    #         zf.extractall(modpack_dir)

    mods_dir = os.path.join(modpack_dir, 'mods')
    os.makedirs(mods_dir, exist_ok=True)

    logger.info("Loading manifest")
    with ZipFile(modpack_filepath, 'r') as zf:
        try:
            manifest_json = zf.read('manifest.json')
        except KeyError as e:
            logger.error(e)
            exit()
        manifest = json.loads(manifest_json)


        logger.info(
            "Modpack info:\n" +
            "  Modpack Name:      %s\n" % manifest["name"] +
            "  Modpack Version:   %s\n" % manifest["version"] +
            "  Author:            %s\n" % manifest["author"] +
            "  Minecraft Version: %s\n" % manifest["minecraft"]["version"]
        )


        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            tasks = [
                download_mods(manifest, mods_dir, None),
                loop.run_in_executor(executor, extract_overrides, zf, modpack_dir)
            ]
            err_mods, _ = await asyncio.gather(*tasks)


        if len(err_mods):
            logger.info(
                "This mods has errors:\n" +
                "\n".join([
                    "  Error: %s\n" % str(r[1]) +
                    "  Download Link: %s" % download_mod_link(r[2], r[3])
                    for r in err_mods
                ])
            )


        logger.info("Modpack loaded!")

if __name__ == "__main__":
    if len(sys.argv) < 2 or "-h" in sys.argv or "--help" in sys.argv:
        print("usage: main.py <modpack_path.zip>")
        exit()
    asyncio.run(main(sys.argv[1]))