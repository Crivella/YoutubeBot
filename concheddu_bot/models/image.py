"""This module contains the Image model."""
import asyncio
import hashlib
import io
import logging
import os
import urllib.request as ur_req

import discord
# import aiofiles
from django.db import models
from PIL import Image, ImageFilter

from ..semaphores import SEMAPHORE_DOWNLOAD

logger = logging.getLogger('bot')

IMAGE_DIR = os.getenv('BOT_IMAGE_DIR', './images')

class ImageObj(models.Model):
    """Image model"""
    url = models.CharField(max_length=512, null=True)
    local_path = models.CharField(max_length=512, null=True)
    md5 = models.CharField(max_length=32, null=True)

    date = models.DateTimeField(auto_now_add=True)

    # user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    # server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    # channel = models.ForeignKey('DiscordChannel', on_delete=models.CASCADE)
    # message = models.ForeignKey('DiscordMessage', on_delete=models.CASCADE, null=True)
    # The number of time the image was viewed
    # num_views = models.IntegerField(default=0)

    @staticmethod
    def _md5(fp: io.BytesIO):
        """Calculate the md5 of a file"""
        md5 = hashlib.md5()
        # async with aiofiles.open(file_path, 'rb') as file:
        #     async for chunk in file.iter_chunks(4096):
        #         md5.update(chunk)
        # with open(file_path, 'rb') as file:
        for chunk in iter(lambda: fp.read(4096), b''):
            md5.update(chunk)
        return md5.hexdigest()

    async def save_local(self, fp: io.BytesIO, ext: str):
        """Save the image locally"""
        md5 = ImageObj._md5(fp)
        # dir_path = os.path.join(IMAGE_DIR, md5[:2], md5[2:4])
        dir_path = os.path.join(IMAGE_DIR, md5[:2])
        os.makedirs(dir_path, exist_ok=True)
        local_path = os.path.join(dir_path, f'{md5}{ext}')
        with open(local_path, 'wb') as file:
            file.write(fp.getbuffer())

        self.md5 = md5
        self.local_path = local_path

        await self.asave()

    async def download(self, *, loop=None) -> str:
        """Download the image"""
        if not self.url:
            logger.error('No url to download image')
            return

        if self.local_path and os.path.exists(self.local_path):
            return self.local_path

        try:
            async with SEMAPHORE_DOWNLOAD:
                logger.info(f'Downloading thumbnail {self.url}')
                loop = loop or asyncio.get_event_loop()
                tmp_file, _ =await loop.run_in_executor(None, lambda: ur_req.urlretrieve(self.url))
        except Exception as e:
            logger.error(f'Error downloading thumbnail {self.url}: {e}', exc_info=True)
            return

        ext = os.path.splitext(tmp_file)[1]
        fp = io.BytesIO()
        with open(tmp_file, 'rb') as file:
            fp.write(file.read())
        fp.seek(0)
        await self.save_local(fp, ext)
        os.remove(tmp_file)

        return self.local_path

    @classmethod
    async def save_from_message(cls, message: discord.Message):
        """Save the image from a message"""
        if not message.attachments:
            logger.error('No attachments in message')
            return

        atc = message.attachments[0]
        if atc.content_type != 'image':
            logger.error('Attachment is not an image')
            return
        name = atc.filename
        ext = os.path.splitext(name)[1]
        fp = io.BytesIO()
        await atc.save(fp, seek_begin=True)

        new = cls(url=atc.url)
        await new.save_local(fp, ext)

    async def get_image(self, blur_radius: int = 0) -> io.BytesIO:
        """Apply a box blur to the image"""
        if not self.local_path:
            raise FileNotFoundError('No local path')
        img = Image.open(self.local_path)
        if blur_radius:
            img = img.filter(ImageFilter.BoxBlur(blur_radius))
        fp = io.BytesIO()
        img.save(fp, format='webp')
        fp.seek(0)
        return fp
