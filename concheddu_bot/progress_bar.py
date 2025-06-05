import io

from PIL import GifImagePlugin, Image, ImageDraw

GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_ALWAYS


def get_progress_gif(duration: int, width: int = 200, height: int = 30) -> io.BytesIO:
    """Generate a progress bar gif for the given duration."""
    frames = []

    num_frames = (duration * 4) + 1  # 4 frames per second

    for i in range(num_frames):
        progress = i / (num_frames - 1)
        # print(f"Progress: {progress * 100}%")
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, width * progress, height], fill='blue', outline='red')
        frames.append(img)

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=1000 // 4,
        loop=0
    )

    buffer.seek(0)  # Reset the buffer to the beginning

    return buffer
