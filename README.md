# Delivery Note Splitter

A Windows GUI program for the scanned delivery-note format used in the supplied PDF.

## What it does

1. Select a PDF.
2. OCR each page.
3. Detect the `DN-xxxxxx` number and the customer in the `To` field.
4. Group pages with the same DN number.
5. Create one PDF per DN.
6. Name each PDF as `DN-000123_Customer_Name.pdf`.
7. Preserve pages with no DN as `NO-DN-1_Customer_Name.pdf`.

Duplicate DN pages are therefore combined into one output PDF.

## Get the Windows EXE

The included GitHub Actions workflow builds `DeliveryNoteSplitter.exe` on Windows and bundles Tesseract OCR, including Arabic OCR data. PyInstaller is used because Windows executables should be built on Windows rather than cross-compiled from Linux.

To build it yourself:

1. Put this project in a GitHub repository.
2. Open **Actions → Build Windows EXE → Run workflow**.
3. Download the `DeliveryNoteSplitter-Windows` artifact.
4. Extract the ZIP and run `DeliveryNoteSplitter.exe`.

You can also build locally on Windows with `build_windows.bat`, but the fully portable OCR bundle is produced by the GitHub Actions workflow.

## OCR limitation

The source PDF is image-based, so the program depends on OCR. The DN number is usually easy to detect because it is printed in the upper-right corner. Customer names, especially handwritten or Arabic names, can require manual checking.
