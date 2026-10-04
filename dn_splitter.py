import os, re, sys, shutil, subprocess, threading
from pathlib import Path
from collections import OrderedDict
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract

APP_NAME = "Delivery Note Splitter"


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def configure_tesseract():
    bundled = resource_path("tesseract", "tesseract.exe")
    if bundled.exists():
        pytesseract.pytesseract.tesseract_cmd = str(bundled)
        tessdata = bundled.parent / "tessdata"
        if tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
    else:
        # Fall back to PATH / common Windows installation locations.
        candidates = [
            shutil.which("tesseract"),
            r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
            r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
        ]
        for c in candidates:
            if c and Path(c).exists():
                pytesseract.pytesseract.tesseract_cmd = str(c)
                return True
        return False
    return True


def clean_filename(s):
    s = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:150] or "Unknown_Customer"


def normalize_text(s):
    s = s.replace("—", "-").replace("–", "-").replace("_", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def preprocess(img):
    img = ImageOps.grayscale(img)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img


def ocr_page(page):
    # Delivery note number and customer are normally in the upper-right quarter.
    pix = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    w, h = img.size
    crop = img.crop((int(w*0.52), 0, w, int(h*0.43)))
    crop = preprocess(crop)
    text = pytesseract.image_to_string(crop, config="--psm 6", lang="eng+Arabic")
    return normalize_text(text), img


def extract_dn(text):
    patterns = [
        r"\bDN\s*[-#:]?\s*0*(\d{3,})\b",
        r"\bD\s*N\s*[-#:]?\s*0*(\d{3,})\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return f"DN-{int(m.group(1)):06d}"
    return None


def extract_customer(text):
    # Prefer text immediately after a To marker, which is how the source documents are laid out.
    m = re.search(r"\bTO\b\s*[:\-]?\s*(.+?)(?=\b(?:DELIVERY\s+NOTE|DATE|PO\s*NO|SAFE\s+AGENT)\b|$)", text, re.I)
    if m:
        val = m.group(1).strip(" :-")
        val = re.sub(r"\b(?:Delivery\s*Note|Date|PO\s*No|Safe\s*Agent)\b.*$", "", val, flags=re.I).strip(" :-")
        val = re.sub(r"\s*\+?965\s*[0-9\s-]{7,}$", "", val).strip(" :-")
        val = re.sub(r"\s+", " ", val)
        if val and len(val) >= 2 and not re.fullmatch(r"\+?965[0-9\s-]+", val):
            return val

    # Fallback: line after a standalone TO.
    lines = [x.strip() for x in re.split(r"\n+", text) if x.strip()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"TO", line, re.I) and i + 1 < len(lines):
            return lines[i+1]
    return "Unknown Customer"


def safe_key(dn, customer):
    return (dn or "NO-DN", clean_filename(customer))


def split_pdf(input_pdf, output_dir, progress_cb=None, log_cb=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(input_pdf)
    groups = OrderedDict()
    no_dn_counter = 0

    for idx in range(len(doc)):
        page = doc[idx]
        text, _ = ocr_page(page)
        dn = extract_dn(text)
        customer = extract_customer(text)
        if not dn:
            no_dn_counter += 1
            key = (f"NO-DN-{no_dn_counter}", clean_filename(customer))
        else:
            key = safe_key(dn, customer)

        groups.setdefault(key, []).append(idx)
        if log_cb:
            log_cb(f"Page {idx+1}: {dn or 'NO-DN'} | {customer}")
        if progress_cb:
            progress_cb((idx + 1) / len(doc) * 70)

    created = []
    for n, ((dn, customer), pages) in enumerate(groups.items(), 1):
        out = output_dir / f"{dn}_{customer}.pdf"
        out = unique_path(out)
        new_doc = fitz.open()
        for p in pages:
            new_doc.insert_pdf(doc, from_page=p, to_page=p)
        new_doc.save(out, garbage=4, deflate=True)
        new_doc.close()
        created.append(out)
        if progress_cb:
            progress_cb(70 + n / len(groups) * 30)

    doc.close()
    return created


def unique_path(path):
    if not path.exists():
        return path
    i = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x560")
        self.minsize(700, 500)
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.build_ui()
        self.tesseract_ok = configure_tesseract()
        if not self.tesseract_ok:
            self.status_var.set("Tesseract OCR was not found. Use the bundled EXE build or install Tesseract.")

    def build_ui(self):
        pad = {"padx": 16, "pady": 8}
        ttk.Label(self, text="Delivery Note Splitter", font=("Segoe UI", 18, "bold")).pack(anchor="w", **pad)
        ttk.Label(self, text="Split a scanned PDF into one PDF per DN/customer. Duplicate DN pages are combined.").pack(anchor="w", padx=16)

        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=16, pady=16)
        ttk.Label(frm, text="Input PDF:").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(frm, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frm, text="Browse…", command=self.browse_input).grid(row=0, column=2)
        ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(frm, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(frm, text="Browse…", command=self.browse_output).grid(row=1, column=2)
        frm.columnconfigure(1, weight=1)

        self.run_btn = ttk.Button(self, text="Split PDF", command=self.start)
        self.run_btn.pack(anchor="w", padx=16, pady=4)
        ttk.Progressbar(self, variable=self.progress_var, maximum=100).pack(fill="x", padx=16, pady=12)
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", padx=16)

        log_frame = ttk.LabelFrame(self, text="Processing log")
        log_frame.pack(fill="both", expand=True, padx=16, pady=12)
        self.log = tk.Text(log_frame, height=16, wrap="none")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

    def browse_input(self):
        f = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if f:
            self.input_var.set(f)
            if not self.output_var.get():
                self.output_var.set(str(Path(f).with_name(Path(f).stem + "_split")))

    def browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_var.set(d)

    def append_log(self, msg):
        self.after(0, lambda: (self.log.insert("end", msg + "\n"), self.log.see("end")))

    def set_progress(self, value):
        self.after(0, lambda: self.progress_var.set(value))

    def start(self):
        inp = Path(self.input_var.get())
        out = Path(self.output_var.get()) if self.output_var.get() else inp.with_name(inp.stem + "_split")
        if not inp.exists() or inp.suffix.lower() != ".pdf":
            messagebox.showerror(APP_NAME, "Please select a valid PDF file.")
            return
        if not self.tesseract_ok:
            messagebox.showerror(APP_NAME, "OCR engine not found. Please use the bundled Windows EXE build or install Tesseract OCR.")
            return
        self.run_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        self.progress_var.set(0)
        self.status_var.set("Processing…")
        threading.Thread(target=self.worker, args=(inp, out), daemon=True).start()

    def worker(self, inp, out):
        try:
            files = split_pdf(inp, out, self.set_progress, self.append_log)
            self.after(0, lambda: self.status_var.set(f"Done — {len(files)} PDF(s) created in {out}"))
            self.after(0, lambda: messagebox.showinfo(APP_NAME, f"Done.\n\nCreated {len(files)} PDF(s).\n\nOutput:\n{out}"))
        except Exception as e:
            self.after(0, lambda: self.status_var.set("Failed"))
            self.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
        finally:
            self.after(0, lambda: self.run_btn.configure(state="normal"))


if __name__ == "__main__":
    App().mainloop()
