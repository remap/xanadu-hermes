
import subprocess
import asyncio
import logging

async def convert_exr_to_png(filepath_in, filepath_out):
    logger = logging.getLogger()
    await asyncio.sleep(0)
    command = [
        "magick",
        filepath_in,
        "-alpha", "off",
        "-colorspace", "sRGB",
        "-gamma", "2.2",
        "-sigmoidal-contrast", "5x50%",
        "-resize", "512x512>",
        filepath_out
    ]
    logger.info(f"convert_exr_to_png, {filepath_in}, {filepath_out}")
    try:
        # Run the command and capture output
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,  # Capture standard output
            stderr=subprocess.PIPE,  # Capture standard error
            text=True,  # Decode output to string
            check=True  # Raise exception if command fails
        )
        # Print the captured output
        if len(result.stdout.strip() )> 0: logger.debug(f"convert_exr_to_png output: {result.stdout}" )
        if len(result.stderr.strip() )> 0: logger.error(f"convert_exr_to_png errors: f{result.stderr}")
    except subprocess.CalledProcessError as e:
        # Handle errors
        logger.error(f"convert_exr_to_png error occurred: {e.stderr}")