
from PIL import Image
import os

file_path = r"Z:\spine sorter v257\test_files_from_collegues\him\output 3\images\piggy_bank\jpeg\butterfly\butterfly_00.png"

try:
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
    else:
        im = Image.open(file_path)
        print(f"Format: {im.format}")
        print(f"Mode: {im.mode}")
        if im.mode == 'RGBA':
            alpha = im.split()[-1]
            extrema = alpha.getextrema()
            print(f"Alpha extrema: {extrema}")
            if extrema[0] < 255:
                print("Image has transparency.")
            else:
                print("Image is fully opaque.")
        else:
            print("Image does not have an alpha channel (likely opaque).")
except Exception as e:
    print(f"Error: {e}")
