"""
Intelligently crop all symbol images to remove excess whitespace/transparency
and make them appear more uniform in size.
"""

from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS_DIR = ROOT / "static" / "symbols"

def find_content_bbox(img):
    """Find bounding box of actual content (non-transparent/non-white pixels)"""
    # Convert to numpy array
    arr = np.array(img)
    
    if img.mode == 'RGBA':
        # For RGBA, find pixels that are not fully transparent
        alpha = arr[:, :, 3]
        # Also check if RGB is not white
        rgb = arr[:, :, :3]
        # Consider a pixel as content if it has alpha > 10 and is not pure white
        is_white = np.all(rgb > 240, axis=2)
        has_content = (alpha > 10) & ~is_white
    else:
        # For RGB, find pixels that are not white
        is_white = np.all(arr > 240, axis=2)
        has_content = ~is_white
    
    # Find rows and columns with content
    rows = np.any(has_content, axis=1)
    cols = np.any(has_content, axis=0)
    
    if not np.any(rows) or not np.any(cols):
        # No content found, return full image bounds
        return (0, 0, img.width, img.height)
    
    row_indices = np.where(rows)[0]
    col_indices = np.where(cols)[0]
    
    y_min, y_max = row_indices[0], row_indices[-1] + 1
    x_min, x_max = col_indices[0], col_indices[-1] + 1
    
    return (x_min, y_min, x_max, y_max)


def crop_with_padding(img, bbox, padding_percent=0.1):
    """Crop to bbox and add padding as percentage of content size"""
    x_min, y_min, x_max, y_max = bbox
    
    # Calculate padding
    content_width = x_max - x_min
    content_height = y_max - y_min
    pad_x = int(content_width * padding_percent)
    pad_y = int(content_height * padding_percent)
    
    # Apply padding (clamped to image bounds)
    x_min = max(0, x_min - pad_x)
    y_min = max(0, y_min - pad_y)
    x_max = min(img.width, x_max + pad_x)
    y_max = min(img.height, y_max + pad_y)
    
    return img.crop((x_min, y_min, x_max, y_max))


def process_symbol(path):
    """Process a single symbol file"""
    try:
        img = Image.open(path)
        original_size = img.size
        
        # Convert to RGBA if needed
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Find content bounding box
        bbox = find_content_bbox(img)
        
        # Check if cropping would make a difference
        x_min, y_min, x_max, y_max = bbox
        if (x_min <= 5 and y_min <= 5 and 
            x_max >= img.width - 5 and y_max >= img.height - 5):
            # Already well-cropped
            return None
        
        # Crop with padding
        cropped = crop_with_padding(img, bbox, padding_percent=0.15)
        
        # Save back to same file
        cropped.save(path, 'PNG')
        
        return {
            'file': path.name,
            'original': original_size,
            'cropped': cropped.size,
            'savings': f"{(1 - (cropped.width * cropped.height) / (original_size[0] * original_size[1])) * 100:.1f}%"
        }
    except Exception as e:
        print(f"Error processing {path.name}: {e}")
        return None


def main():
    # Get all PNG files
    png_files = list(SYMBOLS_DIR.glob("*.png"))
    print(f"Found {len(png_files)} PNG files to process\n")
    
    processed = []
    skipped = 0
    
    for path in sorted(png_files):
        result = process_symbol(path)
        if result:
            processed.append(result)
            print(f"✓ {result['file']}: {result['original']} → {result['cropped']} (saved {result['savings']})")
        else:
            skipped += 1
    
    print(f"\n{'='*60}")
    print(f"Processed: {len(processed)} files")
    print(f"Skipped (already optimal): {skipped} files")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
