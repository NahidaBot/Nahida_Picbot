import io
import logging
import PIL.Image
from db import session
from entities import Image
from telegram import Message

logger = logging.getLogger(__name__)

MAX_SIDE = 2560

def compress_image(
    input_path: str, output_path: str, target_size_mb: int = 10, quality=100
) -> None:
    """
    Compress an image to the target size (in MB) to upload it.
    """
    # Open the image
    with PIL.Image.open(input_path) as img:
        # If the image has an alpha (transparency) channel, convert it to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        width, height = img.size
        if (max_side := max(height, width)) > MAX_SIDE:
            logger.info("meet limits. resized.")
            scale_factor = 2560 / max_side
            img = img.resize(
                (int(width * scale_factor), int(height * scale_factor)),
                PIL.Image.LANCZOS,
            )

        # Check if the image size is already acceptable
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG", quality=quality)
        size = img_byte_arr.tell() / (1024 * 1024)  # Convert to MB

        # While the image size is larger than the target, reduce the quality
        while size > target_size_mb and quality > 10:
            print("size=" + str(size))
            quality -= 5
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="JPEG", quality=quality)
            size = img_byte_arr.tell() / (1024 * 1024)  # Convert to MB

        # Save the compressed image
        with open(output_path, "wb") as f_out:
            f_out.write(img_byte_arr.getvalue())


def is_within_size_limit(input_path: str) -> bool:
    import os
    MAX_FILE_SIZE = 10 * 1024 * 1024

    size = os.path.getsize(input_path)
    if size >= MAX_FILE_SIZE:
        return False

    with PIL.Image.open(input_path) as img:
        width, height = img.size
        if max(height, width) > MAX_SIDE:
            return False
    return True


def check_duplication(pid: int | str) -> Image | None:
    image = session.query(Image).filter_by(pid=pid, post_by_guest=False).first()
    logger.debug(image)
    return image

def check_duplication_via_url(url: str) -> Image | None:
    image = session.query(Image).filter_by(url=url, post_by_guest=False).first()
    logger.debug(image)
    return image


def unmark_deduplication(pid: int | str) -> None:
    """
    反标记
    直接删除匹配 pid 的项 (
    """
    images_to_delete = session.query(Image).filter(Image.pid == int(pid)).all()

    # 删除查询到的数据
    for image in images_to_delete:
        session.delete(image)

    # 提交更改
    session.commit()


def find_url(message: Message) -> list[str]:
    logger.debug(message.reply_to_message)
    logger.debug(message.reply_to_message.entities)
    entities = message.reply_to_message.caption_entities
    urls: list[str] = []
    for entity in entities:
        if entity.type == "text_link" or entity.type == "url":
            urls.append(entity.url)
    return urls
