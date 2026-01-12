"""
Make white/light backgrounds transparent in PNG symbol files.
Keeps black (and near-black) pixels, makes everything else transparent.
"""

from PIL import Image
import os
from pathlib import Path

def make_white_transparent(image_path, output_path=None, threshold=200):
    """
    Convert white/light pixels to transparent, keep dark pixels.
    
    Args:
        image_path: Path to input PNG
        output_path: Path to output PNG (if None, overwrites input)
        threshold: RGB threshold (0-255). Pixels with all RGB values >= threshold become transparent
    """
    if output_path is None:
        output_path = image_path
    
    img = Image.open(image_path)
    img = img.convert("RGBA")
    
    datas = img.getdata()
    new_data = []
    
    for item in datas:
        # If all RGB values are >= threshold, make it transparent
        # This catches white (255,255,255) and light grays
        if item[0] >= threshold and item[1] >= threshold and item[2] >= threshold:
            new_data.append((255, 255, 255, 0))  # Transparent
        else:
            new_data.append(item)  # Keep as is
    
    img.putdata(new_data)
    img.save(output_path, "PNG")
    print(f"Processed: {os.path.basename(image_path)}")

def process_directory(directory, threshold=200):
    """Process all PNG files in a directory."""
    path = Path(directory)
    png_files = list(path.glob("*.png"))
    
    print(f"Found {len(png_files)} PNG files in {directory}")
    print(f"Using threshold: {threshold} (pixels with RGB >= {threshold} will be transparent)")
    print()
    
    for png_file in png_files:
        try:
            make_white_transparent(str(png_file), threshold=threshold)
        except Exception as e:
            print(f"Error processing {png_file.name}: {e}")
    
    print(f"\nDone! Processed {len(png_files)} files.")

if __name__ == "__main__":
    import sys
    
    # Default to symbols directory
    symbols_dir = Path(__file__).parent.parent / "static" / "symbols"
    
    if len(sys.argv) > 1:
        symbols_dir = Path(sys.argv[1])
    
    if len(sys.argv) > 2:
        threshold = int(sys.argv[2])
    else:
        threshold = 200  # Default threshold
    
    print(f"Processing symbols in: {symbols_dir}")
    
    if not symbols_dir.exists():
        print(f"Directory not found: {symbols_dir}")
        sys.exit(1)
    
    # Ask for confirmation
    response = input(f"\nThis will modify all PNG files in {symbols_dir}. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        sys.exit(0)
    
    process_directory(symbols_dir, threshold)
