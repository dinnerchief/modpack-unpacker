from zipfile import ZipFile
from downloader import download_mods, download_mod_link
from logger import logger

import asyncio
import json
import sys
import os
import re

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

        logger.info("Start loading mods")
        results = await download_mods(manifest, mods_dir)
        err_mods = list(filter(lambda r: r[1], results)) # all, where has err

        logger.info("Extracting \"overrides/\"")
        # merge overrides with modpack folder
        try:
            for info in zf.filelist:
                if not info.filename.startswith("overrides/"):
                    continue
                extract_path = os.path.join(modpack_dir, info.filename[10:]) # len("overrides/") = 10
                os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                with open(extract_path, "wb") as f:
                    f.write(zf.read(info))
        except KeyError as e:
            logger.info("overrides folder not found. Skip")
            pass # pass, if overrides does't exists

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