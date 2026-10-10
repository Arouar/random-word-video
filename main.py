import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
WORDS_FILE = BASE_DIR / "words.txt"

OUTPUT_DIR.mkdir(exist_ok=True)

# Read the words
words = [
    line.strip()
    for line in WORDS_FILE.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
]

if not words:
    raise ValueError("words.txt is empty!")

word = random.choice(words)
print(f"Selected word: {word}")

# Create a black vertical image
width, height = 1080, 1920
image = Image.new("RGB", (width, height), "black")
draw = ImageDraw.Draw(image)

# Load a Windows font
font_path = r"C:\Windows\Fonts\arial.ttf"
font_size = 100
font = ImageFont.truetype(font_path, font_size)

# Fit the word inside the screen
while draw.textbbox((0, 0), word, font=font)[2] > width * 0.88:
    font_size -= 4
    font = ImageFont.truetype(font_path, font_size)

# Center the word
bbox = draw.textbbox((0, 0), word, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]

x = (width - text_width) // 2 - bbox[0]
y = (height - text_height) // 2 - bbox[1]

draw.text((x, y), word, fill="white", font=font)

# Save the image
image_path = OUTPUT_DIR / "frame.png"
image.save(image_path)

# Convert the image into a 5-second video
video_path = OUTPUT_DIR / f"{word}.mp4"

command = [
    "ffmpeg",
    "-y",
    "-hide_banner",
    "-loop", "1",
    "-framerate", "30",
    "-i", str(image_path),
    "-t", "5",
    "-vf", "format=yuv420p",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-movflags", "+faststart",
    str(video_path),
]

subprocess.run(command, check=True)

print(f"Video created successfully: {video_path}")