#!/bin/python

import os
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import time
import logging
import shutil
from typing import Dict, Set, Tuple

class ComicSyncManager:
    def __init__(self, library_path: str, output_path: str, log_path: str = None):
        """
        Initialize the comic sync manager.
        
        Args:
            library_path (str): Path to Calibre library
            output_path (str): Path to output directory
            log_path (str): Path to log file (optional)
        """
        self.library_path = library_path
        self.output_path = output_path
        self.metadata_cache_file = os.path.join(output_path, '.metadata_cache.json')
        
        # Setup logging
        self.log_path = log_path or os.path.join(output_path, 'sync_log.txt')
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging to both file and console."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_path),
                logging.StreamHandler()
            ]
        )
    
    def _get_metadata_from_db(self, tag: str) -> Dict:
        """Get all comic metadata with the specified tag from Calibre DB."""
        db_path = os.path.join(self.library_path, 'metadata.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = """
                SELECT 
                    books.id,
                    books.title,
                    books.path,
                    series.name AS series_name,
                    books.series_index,
                    data.format,
                    data.name,
                    books.last_modified,
                    books.sort AS title_sort,  -- Adjusted from title_sort to sort
                    books.author_sort,
                    books.timestamp,
                    books.pubdate,
                    data.uncompressed_size
                FROM books
                LEFT JOIN books_series_link ON books.id = books_series_link.book
                LEFT JOIN series ON books_series_link.series = series.id
                JOIN books_tags_link ON books.id = books_tags_link.book
                JOIN tags ON books_tags_link.tag = tags.id
                JOIN data ON books.id = data.book
                WHERE tags.name = ?
                AND (LOWER(data.format) = 'cbr' OR LOWER(data.format) = 'cbz')
                """

        
        cursor.execute(query, (tag,))
        result = {}
        
        for row in cursor.fetchall():
            book_id = row[0]
            if book_id not in result:
                result[book_id] = {
                    'title': row[1],
                    'path': row[2],
                    'series': row[3],
                    'series_index': row[4],
                    'formats': {},
                    'metadata': {
                        'author_sort': row[9],
                        'timestamp': row[10],
                        'pubdate': row[11]
                    }
                }
            result[book_id]['formats'][row[5].lower()] = {
                'name': row[6],
                'last_modified': row[7],
                'size': row[12]
            }
        
        conn.close()
        return result
    
    def _load_metadata_cache(self) -> Dict:
        """Load the previous metadata cache from disk."""
        if os.path.exists(self.metadata_cache_file):
            try:
                with open(self.metadata_cache_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.warning("Corrupted metadata cache file, starting fresh")
                return {}
        return {}
    
    def _save_metadata_cache(self, cache: Dict):
        """Save the current metadata cache to disk."""
        os.makedirs(os.path.dirname(self.metadata_cache_file), exist_ok=True)
        with open(self.metadata_cache_file, 'w') as f:
            json.dump(cache, f, indent=2)
    
    def _get_target_path(self, book_data: Dict, format_type: str) -> str:
        """Generate the target path for a comic file."""
        clean_title = "".join(c for c in book_data['title'] if c.isalnum() or c in (' ', '-', '_')).strip()
        
        if book_data['series']:
            clean_series = "".join(c for c in book_data['series'] if c.isalnum() or c in (' ', '-', '_')).strip()
            target_folder = os.path.join(self.output_path, clean_series)
            if book_data['series_index']:
                clean_title = f"{book_data['series_index']:02.1f} - {clean_title}"
        else:
            target_folder = os.path.join(self.output_path, "No Series")
        
        os.makedirs(target_folder, exist_ok=True)
        return os.path.join(target_folder, f"{clean_title}.{format_type}")
    
    def sync_tag(self, tag: str, max_workers: int = 4):
        """Sync all comics with the specified tag."""
        logging.info(f"Starting sync for tag: {tag}")
        start_time = time.time()
        
        # Get current and cached metadata
        current_metadata = self._get_metadata_from_db(tag)
        cached_metadata = self._load_metadata_cache()
        
        # Track files to process and remove
        to_process = []
        to_remove = set()
        
        # Find files that need updating or adding
        for book_id, book_data in current_metadata.items():
            for format_type, format_data in book_data['formats'].items():
                source_file = os.path.join(self.library_path, book_data['path'], 
                                         f"{format_data['name']}.{format_type}")
                target_file = self._get_target_path(book_data, format_type)
                
                needs_update = True
                if str(book_id) in cached_metadata:
                    cached_book = cached_metadata[str(book_id)]
                    if (format_type in cached_book['formats'] and
                        cached_book['formats'][format_type]['last_modified'] == format_data['last_modified'] and
                        cached_book['metadata'] == book_data['metadata'] and
                        os.path.exists(target_file)):
                        needs_update = False
                
                if needs_update:
                    to_process.append((source_file, target_file, book_id, book_data, format_type))
        
        # Find files to remove
        current_files = {self._get_target_path(book_data, fmt)
                        for book_data in current_metadata.values()
                        for fmt in book_data['formats']}
        
        existing_files = set()
        for root, _, files in os.walk(self.output_path):
            for file in files:
                if file.lower().endswith(('.cbr', '.cbz', '.pdf', '.zip')):
                    existing_files.add(os.path.join(root, file))
        
        to_remove = existing_files - current_files
        
        # Process files concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Copy/update files
            if to_process:
                futures = []
                for item in to_process:
                    futures.append(executor.submit(self._process_file, *item))
                
                for future in futures:
                    future.result()
            
            # Remove files
            if to_remove:
                futures = []
                for file_path in to_remove:
                    futures.append(executor.submit(os.remove, file_path))
                    logging.info(f"Removing: {os.path.basename(file_path)}")
                
                for future in futures:
                    future.result()
        
        # Save new metadata cache
        self._save_metadata_cache({str(k): v for k, v in current_metadata.items()})
        
        # Clean up empty directories
        for root, dirs, files in os.walk(self.output_path, topdown=False):
            for name in dirs:
                dir_path = os.path.join(root, name)
                if not os.listdir(dir_path) and not dir_path.endswith('.git'):
                    os.rmdir(dir_path)
        
        elapsed_time = time.time() - start_time
        logging.info(f"Sync complete for tag '{tag}'! Time taken: {elapsed_time:.2f} seconds")
    
    def _process_file(self, source_file: str, target_file: str, book_id: int, 
                    book_data: Dict, format_type: str):
        """Process a single comic file by creating a symbolic link."""
        try:
            # Remove the target file if it exists, to avoid errors
            if os.path.exists(target_file):
                os.remove(target_file)
            # Create a symbolic link from the source file to the target location
            if LIBRARY_METHOD == 'link':
                os.symlink(source_file, target_file)
                logging.info(f"Symlink created: {os.path.basename(target_file)} -> {source_file}")
            elif LIBRARY_METHOD == 'copy':
                shutil.copy(source_file, target_file)  # This copies the file
                logging.info(f"File copied: {os.path.basename(target_file)} -> {source_file}")
            else:
                logging.error("Invalid LIBRARY_METHOD. Use 'link' or 'copy'.")
        except Exception as e:
            logging.error(f"Error creating symlink for {os.path.basename(source_file)}: {str(e)}")


if __name__ == "__main__":
    # Configuration
    CALIBRE_LIBRARY = "path/to/calibre/library" # Input Calibre library path here
    OUTPUT_DIRECTORY = "path/to/yac/library" # Input YACReaderLibrary path here
    TAGS = ["Comics & Graphic Novels"]  # Add your tags here
    LIBRARY_METHOD = 'copy' # set to 'copy' or 'link'
    
    # Create and run the sync manager
    sync_manager = ComicSyncManager(
        library_path=CALIBRE_LIBRARY,
        output_path=OUTPUT_DIRECTORY
    )
    
    # Sync each tag
    for tag in TAGS:
        sync_manager.sync_tag(tag, max_workers=4)