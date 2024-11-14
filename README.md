# calibre2yac
Transfer comics in Calibre Library to series-separated YACReaderLibrary format

## Summary
I created this repository as I prefer managing both my books and comics in one place using [Calibre](https://calibre-ebook.com/), but don't like using it to read. For comic reading across my tablets and for reading on a computer, I love using [YACReader](https://yacreader.com/). In order to get the best of both worlds I created this script.

This queries the Calibre database with `sqlite3` to pull all files with a certain tag (I use 'Comics & Graphic Novels') and output them in a target directory that is separated by series instead of by author. I then have this script to run automatically every day to sync any books that go in/get removed from Calibre.

You will have the option to either copy or symlink to the original files. The only reason I would recommend copying the library (given the extra storage it takes up) is if you want to run the YACReaderLibraryServer on a home computer and access the library from *another* computer using YACReaderLibrary. If you are using symlinks, you will not be able to access the books.

If you just want to use mobile (phone, iPad, etc.) to access the YACReaderLibrary Server, using symlinks is my recommended method as all functionality is maintained.

## Features

-  Sync comic files based on tags from a Calibre library.
-  Supports both copying files and creating symbolic links.
-  Caches metadata to avoid unnecessary file operations (books will not be re-copied/re-linked)
-  If book is removed from the Calibre Library, it will also be removed from the YACReaderLibrary

## Installation

1. Clone the repository or download the script file.
2. Ensure you have Python 3.x installed on your system.

## Usage

1. Configure the following parameters in the `if __name__ == "__main__":` section at the bottom of the script:

   ```python
   CALIBRE_LIBRARY = "/path/to/your/calibre_library"  # Path to your Calibre library
   OUTPUT_DIRECTORY = "/path/to/your/comic_library"    # Path to the output directory
   TAGS = ["Your Tag Here"]                             # List of tags to sync
   LIBRARY_METHOD = 'link'                              # Choose 'copy' or 'link'
    ```
2. Via terminal within the project directory:

    ```bash
    python3 sync_libraries.py
    ```
