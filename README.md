This tool extracts spoken dialogue from movie script pdfs and saves them in csv format.

It relies on the pdfminer library to run.  You can install the pdfminer library from https://github.com/euske/pdfminer/

Usage:

To use, place all the pdfs you want to convert in one folder, then run

scriptreader.py SCRIPT_FOLDER

It will convert all .pdf's in this folder into .csv's containing dialogue.  Csv files will be saved in the same folder.

If you omit the SCRIPT_FOLDER argument, then the script will run in the current folder.

