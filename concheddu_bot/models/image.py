"""This module contains the Image model."""
import asyncio
import hashlib
import io
import logging
import os
import random
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
        fp.seek(0)
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
        fp.seek(0)
        with open(local_path, 'wb') as file:
            file.write(fp.getbuffer())

        self.md5 = md5
        self.local_path = local_path

        await self.asave()

    @classmethod
    async def from_hash(cls, md5: str) -> 'ImageObj':
        """Create an ImageObj from a hash"""
        q = cls.objects.filter(md5=md5)
        if await q.aexists():
            return await q.aget()
        return None

    @classmethod
    async def from_local(cls, local_path: str, force: bool = False) -> 'ImageObj':
        """Create an ImageObj from a local path"""
        # Calculate the md5 of the file
        with open(local_path, 'rb') as file:
            fp = io.BytesIO(file.read())
        fp.seek(0)
        md5 = cls._md5(fp)
        ext = os.path.splitext(local_path)[1]

        # Check if the image already exists
        new, created = await cls.objects.aget_or_create(md5=md5)
        if created or force:
            await new.save_local(fp, ext=ext)

        return new

    @classmethod
    async def from_url(cls, url: str) -> 'ImageObj':
        """Create an ImageObj from a URL"""
        if not url:
            logger.error('No URL provided for ImageObj')
            return None

        # Check if the image already exists
        new, created = await cls.objects.aget_or_create(url=url)
        if created:
            await new.download()

        return new

    async def download(self, *, loop=None) -> str:
        """Download the image"""
        if not self.url:
            logger.error('No url to download image')
            return

        if self.local_path and os.path.exists(self.local_path):
            return self.local_path

        try:
            async with SEMAPHORE_DOWNLOAD:
                logger.info(f'Downloading image {self.url}')
                loop = loop or asyncio.get_event_loop()
                tmp_file, _ = await loop.run_in_executor(None, lambda: ur_req.urlretrieve(self.url))
        except Exception as e:
            logger.error(f'Error downloading image {self.url}: {e}', exc_info=True)
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

    async def get_image_scrambled(self, gx: int = 20, gy: int = 20) -> io.BytesIO:
        """Scramble the image"""
        if not self.local_path:
            raise FileNotFoundError('No local path')
        img = Image.open(self.local_path)
        if gx and gy:
            X = img.size[0]
            Y = img.size[1]
            X -= X % gx
            Y -= Y % gy
            chunks = []
            sx = X // gx
            sy = Y // gy
            for y in range(gy):
                for x in range(gx):
                    chunk = img.crop((x * sx, y * sy, (x + 1) * sx, (y + 1) * sy))
                    chunks.append(chunk)
            random.shuffle(chunks)
            img = Image.new('RGB', (X, Y))
            for i in range(gy):
                for j in range(gx):
                    img.paste(chunks.pop(), (j * sx, i * sy))

        fp = io.BytesIO()
        img.save(fp, format='webp')
        fp.seek(0)
        return fp

    async def get_image_partial_reveal(self, gx: int = 20, gy: int = 20, num: int = 10) -> io.BytesIO:
        """Scramble the image"""
        if not self.local_path:
            raise FileNotFoundError('No local path')
        img = Image.open(self.local_path)
        if num < gx * gy:
            X = img.size[0]
            Y = img.size[1]
            X -= X % gx
            Y -= Y % gy
            chunks = []
            sx = X // gx
            sy = Y // gy
            for y in range(gy):
                for x in range(gx):
                    chunk = img.crop((x * sx, y * sy, (x + 1) * sx, (y + 1) * sy))
                    chunks.append((x*sx, y*sy, chunk))
            todo = random.sample(chunks, num)
            img = Image.new('RGB', (X, Y))
            for x, y, chunk in todo:
                img.paste(chunk, (x, y))

        fp = io.BytesIO()
        img.save(fp, format='webp')
        fp.seek(0)
        return fp
