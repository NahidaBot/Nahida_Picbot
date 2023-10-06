import io
from PIL import Image


def compress_image(
    input_path: str, output_path: str, target_size_mb: int = 10, quality=100
) -> None:
    """
    Compress an image to the target size (in MB) to upload it.
    """
    # Open the image
    with Image.open(input_path) as img:
        # If the image has an alpha (transparency) channel, convert it to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        MAX_SUM = 10000
        MAX_WIDTH = 2560
        width, height = img.size
        if width + height > MAX_SUM or width > MAX_WIDTH:
            print("resized")
            aspect_ratio = width / height
            width = min(MAX_SUM / (aspect_ratio + 1), MAX_WIDTH)
            height = width / aspect_ratio
            img = img.resize((int(width), int(height)), Image.LANCZOS)

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
