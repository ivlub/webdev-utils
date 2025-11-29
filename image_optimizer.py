#!/usr/bin/env python3
"""
Image Optimizer Script
----------------------
Crawls through the repository, finds all JPG/JPEG/PNG images,
compresses and converts them to WebP format, then updates all
references in HTML and PHP files.

Usage:
    python image_optimizer.py [options]

Options:
    --quality, -q    WebP quality (1-100, default: 85)
    --dry-run, -d    Preview changes without applying them
    --backup, -b     Create backup of original images
    --verbose, -v    Show detailed output
    --delete-originals  Delete original images after conversion
"""

import os
import sys
import argparse
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library is required.")
    print("Install it with: pip install Pillow")
    sys.exit(1)


# Configuration
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
CODE_EXTENSIONS = {'.html', '.htm', '.php', '.css', '.js', '.jsx', '.tsx', '.vue', '.svelte', '.md', '.markdown'}
EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', '.env', 'vendor', 'dist', 'build'}


def get_script_directory() -> Path:
    """Get the directory where this script is located."""
    return Path(__file__).resolve().parent


def find_images(root_dir: Path) -> List[Path]:
    """Find all JPG, JPEG, and PNG images in the directory tree."""
    images = []
    
    for item in root_dir.rglob('*'):
        # Skip excluded directories
        if any(excluded in item.parts for excluded in EXCLUDE_DIRS):
            continue
        
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(item)
    
    return images


def find_code_files(root_dir: Path) -> List[Path]:
    """Find all HTML, PHP, and other code files that might reference images."""
    code_files = []
    
    for item in root_dir.rglob('*'):
        # Skip excluded directories
        if any(excluded in item.parts for excluded in EXCLUDE_DIRS):
            continue
        
        if item.is_file() and item.suffix.lower() in CODE_EXTENSIONS:
            code_files.append(item)
    
    return code_files


def convert_to_webp(image_path: Path, quality: int = 85, backup: bool = False) -> Tuple[Path, bool]:
    """
    Convert an image to WebP format.
    
    Returns:
        Tuple of (new_path, success)
    """
    webp_path = image_path.with_suffix('.webp')
    
    try:
        # Create backup if requested
        if backup:
            backup_path = image_path.with_suffix(image_path.suffix + '.backup')
            if not backup_path.exists():
                import shutil
                shutil.copy2(image_path, backup_path)
        
        # Open and convert image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for PNG with transparency, use RGBA)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # Keep alpha channel for WebP
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            
            # Save as WebP
            img.save(webp_path, 'WEBP', quality=quality, method=6)
        
        return webp_path, True
        
    except Exception as e:
        print(f"  Error converting {image_path}: {e}")
        return webp_path, False


def get_relative_path_variants(image_path: Path, root_dir: Path) -> Set[str]:
    """
    Generate different path variants that might be used in code files.
    """
    variants = set()
    
    # Get the relative path from root
    try:
        rel_path = image_path.relative_to(root_dir)
    except ValueError:
        rel_path = image_path
    
    # Original filename
    filename = image_path.name
    
    # Add various path formats
    rel_str = str(rel_path).replace('\\', '/')
    
    variants.add(filename)  # Just the filename
    variants.add(rel_str)   # Relative path with forward slashes
    variants.add('./' + rel_str)  # With ./
    variants.add('/' + rel_str)   # With leading /
    
    # Also add Windows-style paths (in case they're used)
    variants.add(str(rel_path))
    
    return variants


def update_references_in_file(
    file_path: Path, 
    image_mappings: Dict[str, str],
    root_dir: Path,
    dry_run: bool = False,
    verbose: bool = False
) -> int:
    """
    Update image references in a single file.
    
    Returns:
        Number of replacements made
    """
    try:
        # Try different encodings
        content = None
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return 0
        
        original_content = content
        replacements = 0
        
        # Replace each old image reference with new WebP reference
        for old_name, new_name in image_mappings.items():
            # Create pattern that matches the old filename with common path prefixes
            # Escape special regex characters in filename
            old_escaped = re.escape(old_name)
            
            # Pattern to match image references in various contexts
            # Handles: src="...", url(...), href="...", etc.
            patterns = [
                # Match in quotes (single or double)
                (rf'(["\'])([^"\']*?)({old_escaped})(["\'])', rf'\1\2{new_name}\4'),
                # Match in url()
                (rf'(url\s*\(\s*)(["\']?)([^)]*?)({old_escaped})(["\']?\s*\))', rf'\1\2\3{new_name}\5'),
                # Match in markdown
                (rf'(\!\[[^\]]*\]\s*\()([^)]*?)({old_escaped})(\))', rf'\1\2{new_name}\4'),
            ]
            
            for pattern, replacement in patterns:
                new_content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)
                if count > 0:
                    content = new_content
                    replacements += count
        
        # Write updated content if changes were made
        if content != original_content:
            if not dry_run:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            if verbose:
                print(f"  Updated {file_path}: {replacements} replacement(s)")
        
        return replacements
        
    except Exception as e:
        print(f"  Error processing {file_path}: {e}")
        return 0


def get_file_size_str(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(
        description='Convert images to WebP and update references in code files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('-q', '--quality', type=int, default=85,
                        help='WebP quality (1-100, default: 85)')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='Preview changes without applying them')
    parser.add_argument('-b', '--backup', action='store_true',
                        help='Create backup of original images')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show detailed output')
    parser.add_argument('--delete-originals', action='store_true',
                        help='Delete original images after successful conversion')
    parser.add_argument('--path', type=str, default=None,
                        help='Path to scan (default: script directory)')
    
    args = parser.parse_args()
    
    # Validate quality
    if not 1 <= args.quality <= 100:
        print("Error: Quality must be between 1 and 100")
        sys.exit(1)
    
    # Get root directory
    if args.path:
        root_dir = Path(args.path).resolve()
    else:
        root_dir = get_script_directory()
    
    if not root_dir.exists():
        print(f"Error: Directory does not exist: {root_dir}")
        sys.exit(1)
    
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Image Optimizer")
    print(f"{'=' * 50}")
    print(f"Scanning: {root_dir}")
    print(f"Quality: {args.quality}")
    print()
    
    # Find all images
    print("Finding images...")
    images = find_images(root_dir)
    
    if not images:
        print("No JPG, JPEG, or PNG images found.")
        return
    
    print(f"Found {len(images)} image(s) to convert")
    print()
    
    # Convert images
    print("Converting images to WebP...")
    converted = []
    failed = []
    total_original_size = 0
    total_new_size = 0
    image_mappings = {}  # Maps old filename to new filename
    
    for image_path in images:
        if args.verbose:
            print(f"  Processing: {image_path.name}")
        
        original_size = image_path.stat().st_size
        total_original_size += original_size
        
        if args.dry_run:
            webp_path = image_path.with_suffix('.webp')
            converted.append((image_path, webp_path))
            image_mappings[image_path.name] = webp_path.name
            continue
        
        webp_path, success = convert_to_webp(image_path, args.quality, args.backup)
        
        if success:
            new_size = webp_path.stat().st_size
            total_new_size += new_size
            converted.append((image_path, webp_path))
            image_mappings[image_path.name] = webp_path.name
            
            if args.verbose:
                savings = ((original_size - new_size) / original_size) * 100
                print(f"    {get_file_size_str(original_size)} -> {get_file_size_str(new_size)} ({savings:.1f}% smaller)")
        else:
            failed.append(image_path)
    
    print(f"\nConverted: {len(converted)} image(s)")
    if failed:
        print(f"Failed: {len(failed)} image(s)")
    
    if not args.dry_run and converted:
        savings = ((total_original_size - total_new_size) / total_original_size) * 100 if total_original_size > 0 else 0
        print(f"Total size: {get_file_size_str(total_original_size)} -> {get_file_size_str(total_new_size)} ({savings:.1f}% smaller)")
    
    print()
    
    # Update references in code files
    print("Updating references in code files...")
    code_files = find_code_files(root_dir)
    
    if not code_files:
        print("No HTML, PHP, or other code files found.")
    else:
        print(f"Scanning {len(code_files)} code file(s)...")
        
        total_replacements = 0
        files_updated = 0
        
        for code_file in code_files:
            replacements = update_references_in_file(
                code_file, 
                image_mappings, 
                root_dir,
                args.dry_run,
                args.verbose
            )
            if replacements > 0:
                total_replacements += replacements
                files_updated += 1
        
        print(f"\nUpdated {files_updated} file(s) with {total_replacements} replacement(s)")
    
    # Delete originals if requested
    if args.delete_originals and not args.dry_run and converted:
        print("\nDeleting original images...")
        deleted = 0
        for original_path, webp_path in converted:
            if webp_path.exists():
                try:
                    original_path.unlink()
                    deleted += 1
                    if args.verbose:
                        print(f"  Deleted: {original_path.name}")
                except Exception as e:
                    print(f"  Error deleting {original_path}: {e}")
        print(f"Deleted {deleted} original image(s)")
    
    print()
    print("Done!")
    
    if args.dry_run:
        print("\nThis was a dry run. No changes were made.")
        print("Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
