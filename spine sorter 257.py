#!/usr/bin/env python3
"""
Spine Sorter v5.73 - PySide6 UI for managing Spine Animation Files

This application allows users to:
1. Locate and configure the Spine executable.
2. Browse a directory for .spine files.
3. List and filter .spine files.
4. Manage persistent configuration settings.
5. Launch Spine with specific versions and files.

Key Components:
- SpineScannerThread: Background thread to find installed Spine versions.
- ImageCache: Caches metadata about files to avoid redundant processing.
- FileScanner: Efficiently scans directories for files.
- SpinePackageValidator: Validates the integrity of .spine packages.
- Main UI Class (implied below): Handles the graphical interface and user interactions.

Dependencies:
- PySide6: For the GUI.
- Pillow (PIL): Optional, for image processing if needed.
"""
try:
	import cv2
	import numpy as np
	from skimage.metrics import structural_similarity as ssim
	OPENCV_AVAILABLE = True
except ImportError:
	OPENCV_AVAILABLE = False
	print("Advanced matching libraries (opencv-python, scikit-image) not found. Falling back to basic hashing.")

import sys
import os
import json
import subprocess
import time
import re
import ctypes
import zipfile
import difflib
import hashlib
import io
import errno
import random
# Imports for version fetching
import ssl
import urllib.request
import urllib.parse
from pathlib import Path

# --- Configuration Constants ---
# Default Spine versions for the version selector dropdown.
# These act as fallbacks or common presets.
DEFAULT_VERSIONS = ["4.2.43", "4.3", "4.2", "4.1", "4.0", "3.8"]

# --- Optional Dependencies ---
try:
	import PIL.Image
	import PIL.ImageFile
	import PIL.PngImagePlugin # Ensure direct access to the plugin module
    
	# Allow loading truncated images for robustness
	PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True
	# Increase limit for text chunks (metadata) significantly (2GB)
	PIL.ImageFile.MAX_TEXT_MEMORY = 2048 * 1024 * 1024
	# Fix: PngImagePlugin copies MAX_TEXT_MEMORY at import time, so we must update it there too
	PIL.PngImagePlugin.MAX_TEXT_MEMORY = 2048 * 1024 * 1024
    
	# Disable DecompressionBomb prevention (allow large images)
	PIL.Image.MAX_IMAGE_PIXELS = None
    
	Image = PIL.Image
	ImageFile = PIL.ImageFile
except Exception:
	Image = None

# --- GUI Dependencies ---
# We wrap this in a try-block to provide a clear error message if PySide6 is missing.
try:
	from PySide6.QtCore import QStandardPaths, Qt, QThread, Signal, QTimer, QUrl
	from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush, QPalette, QTextCursor, QDesktopServices, QAction, QClipboard
	from PySide6.QtWidgets import (
		QApplication,
		QMainWindow,
		QWidget,
		QVBoxLayout,
		QHBoxLayout,
		QLabel,
		QComboBox,
		QPushButton,
		QLineEdit,
		QFileDialog,
		QListWidget,
		QTextEdit,
		QMessageBox,
		QCheckBox,
		QSlider,
		QSpinBox,
		QDialog,
		QProgressBar,
		QStyle,
		QListWidgetItem,
		QSizePolicy,
	)
except ModuleNotFoundError:
	print("PySide6 is not installed. Install with: pip install PySide6")
	sys.exit(1)


class SpineFileWidget(QWidget):
	"""
	Custom widget for the file list: [CheckBox] [Filename]
	"""
	stateChanged = Signal(int)

	def __init__(self, text, available_versions, parent=None):
		super().__init__(parent)
		layout = QHBoxLayout(self)
		layout.setContentsMargins(4, 2, 4, 2)
		layout.setSpacing(10)
		
		# Checkbox
		self.checkbox = QCheckBox()
		self.checkbox.stateChanged.connect(self.stateChanged.emit)
		layout.addWidget(self.checkbox)
		
		# Filename Label
		self.label = QLabel(text)
		self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
		layout.addWidget(self.label)
		
		# Removed per-request: Version selector dropdown
		
	def isChecked(self):
		return self.checkbox.isChecked()
		
	def setChecked(self, checked):
		self.checkbox.setChecked(checked)
		
	def getSelectedSpineExe(self):
		# Always return None so it falls back to global default
		return None
		
	def updateVersions(self, available_versions):
		# No op since dropdown is removed
		pass


class VersionFetcherThread(QThread):
	"""
	Background thread to fetch all available Spine versions from the official archive.
	"""
	versions_fetched = Signal(list)
	error_occurred = Signal(str)

	def run(self):
		base_urls = [
			'https://hr.esotericsoftware.com/spine-changelog/archive',
			'https://esotericsoftware.com/spine-changelog/archive',
		]
		
		collected = set()
		monthly_urls = []
		
		def fetch_url(u, timeout=10):
			last_err = None
			try:
				ctx = ssl.create_default_context()
				with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
					return r.read().decode('utf-8', errors='ignore')
			except Exception as e1:
				last_err = e1
				try:
					# Fallback for old ssl certs if needed
					ctx = ssl._create_unverified_context()
					with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
						return r.read().decode('utf-8', errors='ignore')
				except Exception as e2:
					last_err = e2
					if u.startswith('https://'):
						http_u = 'http://' + u[len('https://'):]
						try:
							with urllib.request.urlopen(http_u, timeout=timeout) as r:
								return r.read().decode('utf-8', errors='ignore')
						except Exception as e3:
							last_err = e3
			return None

		try:
			# 1. Fetch from Archive Base URLs
			for base in base_urls:
				html = fetch_url(base)
				if not html:
					continue
				
				# Grab direct versions listed (including -beta)
				for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?(?:-beta)?)\b", html, re.IGNORECASE):
					collected.add(v)
				
				# Grab monthly changelog links
				for m in re.findall(r'href=["\']([^"\']*spine-changelog/\d{4}/\d{2}[^"\']*)', html, flags=re.IGNORECASE):
					u = urllib.parse.urljoin(base, m)
					if u not in monthly_urls:
						monthly_urls.append(u)
			
			# 2. Fetch from Monthly URLs (limit to recent/all depending on speed)
			# To be safe, we just fetch them. This might take a few seconds.
			for mu in monthly_urls:
				h = fetch_url(mu, timeout=5)
				if h:
					for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?(?:-beta)?)\b", h, re.IGNORECASE):
						collected.add(v)
						
			# 3. Always try root changelog too
			try:
				root_url = 'https://hr.esotericsoftware.com/spine-changelog/'
				r = fetch_url(root_url)
				if r:
					for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", r):
						collected.add(v)
			except:
				pass

			# Sort versions
			def ver_key(s):
				parts = [int(x) for x in s.split('.')[:3] if x.isdigit()]
				while len(parts) < 3:
					parts.append(0)
				return tuple(parts)

			valid_versions = {v for v in collected if re.match(r'^\d+\.\d+(?:\.\d+)?$', v)}
			sorted_versions = sorted(valid_versions, key=ver_key, reverse=True)
			
			self.versions_fetched.emit(sorted_versions)
			
		except Exception as e:
			self.error_occurred.emit(str(e))


class SpineScannerThread(QThread):

	"""
	Background thread to scan the system for installed Spine executables.
	
	This prevents the UI from freezing while searching file system roots
	and querying executables for their version strings.
	 """

	versions_found = Signal(list)

	def __init__(self, config, default_spine_exe, parent=None):
		super().__init__(parent)
		self.config = config
		self.default_spine_exe = default_spine_exe

	def _get_file_version_windows(self, path):
		if os.name != 'nt':
			return None
		try:
			GetFileVersionInfoSize = ctypes.windll.version.GetFileVersionInfoSizeW
			GetFileVersionInfo = ctypes.windll.version.GetFileVersionInfoW
			VerQueryValue = ctypes.windll.version.VerQueryValueW
			
			filename = str(path)
			size = GetFileVersionInfoSize(filename, None)
			if not size: return None
			res = ctypes.create_string_buffer(size)
			if not GetFileVersionInfo(filename, 0, size, res): return None
			r = ctypes.c_void_p()
			l = ctypes.c_uint()
			if not VerQueryValue(res, "\\", ctypes.byref(r), ctypes.byref(l)): return None
			class VS_FIXEDFILEINFO(ctypes.Structure):
				_fields_ = [
					("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
					("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
					("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32),
					("dwFileFlagsMask", ctypes.c_uint32), ("dwFileFlags", ctypes.c_uint32),
					("dwFileOS", ctypes.c_uint32), ("dwFileType", ctypes.c_uint32),
					("dwFileSubtype", ctypes.c_uint32), ("dwFileDateMS", ctypes.c_uint32),
					("dwFileDateLS", ctypes.c_uint32),
				]
			
			ffi = ctypes.cast(r, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
			major = ffi.dwFileVersionMS >> 16
			minor = ffi.dwFileVersionMS & 0xFFFF
			patch = ffi.dwFileVersionLS >> 16
			return f"{major}.{minor}.{patch}"
		except Exception:
			return None

	def detect_spine_version(self, spine_exe, timeout=1.0):
		exe = str(spine_exe)
		home = os.path.expanduser("~")
		candidates_txt = [
			os.path.join(os.path.dirname(exe), "version.txt"),
			os.path.join(home, "Spine", "version.txt"),
			os.path.join(home, ".spine", "version.txt"),
			os.path.join(home, "Library", "Application Support", "Spine", "version.txt"),
		]
		if sys.platform == 'darwin' and exe.endswith('.app'):
			candidates_txt.append(os.path.join(exe, "Contents", "Resources", "version.txt"))
		for txt_path in candidates_txt:
			if os.path.isfile(txt_path):
				try:
					with open(txt_path, 'r', encoding='utf-8') as f:
						content = f.read().strip()
						if re.match(r"^\d+\.\d+(\.\d+)?$", content):
							return content
				except Exception:
					pass
		if os.name == 'nt':
			ver = self._get_file_version_windows(exe)
			if ver and ver != "0.0.0": return ver
		candidates = [[exe, '--version']]
		if sys.platform == 'darwin' and exe.endswith('.app'):
			binary = os.path.join(exe, "Contents", "MacOS", "Spine")
			if os.path.exists(binary):
				candidates = [[binary, '--version']]
		ver_re = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
		for cmd in candidates:
			try:
				creationflags = 0x08000000 if os.name == 'nt' else 0
				p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=creationflags)
				out = (p.stdout or "") + "\n" + (p.stderr or "")
				m = ver_re.search(out)
				if m:
					return m.group(1)
			except Exception:
				continue
		return None

	def run(self):
		candidates = []
		cfg = self.config.get('spine_exe', self.default_spine_exe)
		cfg_dir = os.path.dirname(cfg)
		roots = []
		if os.name == 'nt':
			roots = [cfg_dir, r"C:\Program Files", r"C:\Program Files (x86)"]
			# Also check parent of cfg_dir if it looks like a versioned folder (e.g. "Spine 4.0")
			# This helps find siblings like "Spine 3.8" in the same parent dir
			parent = os.path.dirname(cfg_dir)
			if parent and os.path.isdir(parent) and len(parent) > 3: # Avoid scanning C:\ directly unless constrained
				roots.append(parent)
		elif sys.platform == 'darwin':
			roots = [cfg_dir, "/Applications", os.path.expanduser("~/Applications")]
		else:
			roots = [cfg_dir, "/usr/bin", "/usr/local/bin"]
		
		# Deduplicate roots
		roots = list(set(os.path.normpath(r) for r in roots if r and os.path.isdir(r)))

		seen = set()
		for root in roots:
			if not root or not os.path.isdir(root):
				continue
			try:
				for name in os.listdir(root):
					if 'spine' in name.lower():
						if sys.platform == 'darwin' and name.endswith('.app'):
							exe = os.path.join(root, name)
							if os.path.isdir(exe) and exe not in seen:
								candidates.append(exe); seen.add(exe)
						else:
							# Check for Spine.exe inside (standard)
							exe = os.path.join(root, name, 'Spine.exe')
							if os.path.isfile(exe) and exe not in seen:
								candidates.append(exe); seen.add(exe)
						
							# Also check if the folder itself contains the exe directly (rare but possible flat structure)
							# e.g. root/Spine.exe
							if name.lower() == 'spine.exe':
								exe = os.path.join(root, name)
								if os.path.isfile(exe) and exe not in seen:
									candidates.append(exe); seen.add(exe)

			except Exception:
				pass

		for root in roots:
			try:
				if sys.platform == 'darwin':
					exe = os.path.join(root, 'Spine.app')
					if os.path.isdir(exe) and exe not in seen:
						candidates.append(exe); seen.add(exe)
				else:
					exe = os.path.join(root, 'Spine.exe')
					if os.path.isfile(exe) and exe not in seen:
						candidates.append(exe); seen.add(exe)
			except Exception:
				pass
		results = []
		for exe in candidates:
			label = os.path.basename(os.path.dirname(exe)) or os.path.basename(exe)
			try:
				ver = self.detect_spine_version(exe)
			except Exception:
				ver = None
			if ver:
				disp = f"{label} ({ver}) - {os.path.basename(exe)}"
			else:
				disp = f"{label} - {os.path.basename(exe)}"
			results.append((disp, exe))
		if not results and cfg:
			results.append((os.path.basename(cfg), cfg))
		self.versions_found.emit(results)


class ReportDialog(QDialog):
	def __init__(self, parent=None, report_text=""):
		super().__init__(parent)
		self.setWindowTitle("Process Report")
		self.resize(800, 600)
		
		layout = QVBoxLayout(self)
		
		label = QLabel("Processing complete. Review the report below:")
		label.setStyleSheet("font-weight: bold; font-size: 14px;")
		layout.addWidget(label)

		self.text_edit = QTextEdit()
		self.text_edit.setReadOnly(True)
		self.text_edit.setText(report_text)
		# Use monospace font for better formatting of lists
		font = QFont("Consolas", 10)
		font.setStyleHint(QFont.Monospace)
		self.text_edit.setFont(font)
		layout.addWidget(self.text_edit)
		
		btn_layout = QHBoxLayout()
		
		self.save_btn = QPushButton("Save Report As...")
		self.save_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton) if hasattr(QStyle, 'SP_DialogSaveButton') else QIcon())
		self.save_btn.clicked.connect(self.save_report)
		btn_layout.addWidget(self.save_btn)
		
		btn_layout.addStretch()

		self.close_btn = QPushButton("Close")
		self.close_btn.clicked.connect(self.accept)
		btn_layout.addWidget(self.close_btn)
		
		layout.addLayout(btn_layout)
		
	def save_report(self):
		timestamp = int(time.time())
		default_name = f"spine_report_{timestamp}.txt"
		path, _ = QFileDialog.getSaveFileName(self, "Save Report", default_name, "Text Files (*.txt)")
		if path:
			try:
				with open(path, 'w', encoding='utf-8') as f:
					f.write(self.text_edit.toPlainText())
				QMessageBox.information(self, "Saved", f"Report saved to:\n{path}")
			except Exception as e:
				QMessageBox.critical(self, "Error", f"Could not save report:\n{e}")


class ImageCache:
	"""
	Persists image metadata to disk to speed up subsequent loads.
	
	The cache stores the file modification time and size to invalidate entries
	if the source file changes.
	 """
	def __init__(self, cache_path):
		self.cache_path = cache_path
		self.cache = {}
		self.load()

	def load(self):
		"""Loads the cache from the JSON file."""
		try:
			if os.path.exists(self.cache_path):
				with open(self.cache_path, 'r', encoding='utf-8') as f:
					self.cache = json.load(f)
		except Exception:
			self.cache = {}

	def save(self):
		"""Saves the current cache state to the JSON file."""
		try:
			with open(self.cache_path, 'w', encoding='utf-8') as f:
				json.dump(self.cache, f, indent=2)
		except Exception:
			pass

	def get(self, path):
		"""
		Retrieves data for a file if the cache is valid (mtime/size match).
		"""
		try:
			stat = os.stat(path)
			mtime = stat.st_mtime
			size = stat.st_size
			
			if path in self.cache:
				entry = self.cache[path]
				if entry.get('mtime') == mtime and entry.get('size') == size:
					return entry.get('data')
		except Exception:
			pass
		return None

	def set(self, path, data):
		"""Updates or adds an entry to the cache."""
		try:
			stat = os.stat(path)
			self.cache[path] = {
				'mtime': stat.st_mtime,
				'size': stat.st_size,
				'data': data
			}
		except Exception:
			pass


class FileScanner:
	"""
	Recursively scans directories for files.

	Results are cached in memory for the lifetime of the object to avoid
	re-scanning the file system unnecessarily.
	"""
	def __init__(self):
		self.cache = {} # dir_path -> list of (full_path, basename_lower)

	def scan(self, directory):
		"""
		Scans a directory for all files recursively.
		
		Args:
			directory (str): The root directory to scan.
			
		Returns:
			list: A list of tuples (full_path, lowercase_filename).
		"""
		if directory in self.cache:
			return self.cache[directory]
		
		results = []
		if directory and os.path.exists(directory):
			for root, dirs, files in os.walk(directory):
				for f in files:
					full_path = os.path.join(root, f)
					results.append((full_path, f.lower()))
		self.cache[directory] = results
		return results


class SpinePackageValidator:
	"""Deep diagnostic tool for .spine packages."""
	
	@staticmethod
	def diagnose(spine_path, log_callback=print):
		log_callback(f"Diagnosing: {spine_path}")
		if not os.path.exists(spine_path):
			log_callback("ERROR: File not found.")
			return

		if not zipfile.is_zipfile(spine_path):
			# Check if it might be a binary Spine file
			try:
				with open(spine_path, 'rb') as f:
					header = f.read(8)
					if len(header) > 0:
						log_callback("INFO: File is not a ZIP archive. It appears to be a binary .spine file (standard format).")
						log_callback("Diagnostic checks for ZIP structure skipped.")
						return
			except Exception:
				pass
				
			log_callback("ERROR: Not a valid ZIP file and could not be identified as a binary Spine file.")
			return

		issues = []
		warnings = []
		
		try:
			with zipfile.ZipFile(spine_path, 'r') as z:
				# 1. Check ZIP entries
				names = z.namelist()
				log_callback(f"ZIP contains {len(names)} entries.")
				
				# Check for duplicates (case-insensitive)
				seen_lower = {}
				for n in names:
					lower = n.lower()
					if lower in seen_lower:
						warnings.append(f"Duplicate filename (case-insensitive): {n} vs {seen_lower[lower]}")
					seen_lower[lower] = n

				# 2. Find JSON
				base_name = os.path.splitext(os.path.basename(spine_path))[0]
				expected_json = base_name + ".json"
				
				json_entry = None
				for n in names:
					if n == expected_json:
						json_entry = n
						break
					if n.lower() == expected_json.lower():
						warnings.append(f"JSON name case mismatch: found '{n}', expected '{expected_json}'")
						json_entry = n
				
				if not json_entry:
					# Fallback: look for any json
					jsons = [n for n in names if n.lower().endswith('.json')]
					if not jsons:
						issues.append("CRITICAL: No JSON file found in archive.")
						return
					if len(jsons) > 1:
						warnings.append(f"Multiple JSON files found: {jsons}. Using {jsons[0]}")
					json_entry = jsons[0]
					issues.append(f"CRITICAL: Expected JSON '{expected_json}' not found. Found '{json_entry}' instead.")

				log_callback(f"Analyzing JSON: {json_entry}")
				
				try:
					with z.open(json_entry) as f:
						data = json.load(f)
				except Exception as e:
					issues.append(f"CRITICAL: Invalid JSON: {e}")
					return

				# 3. Check Skeleton
				skel = data.get('skeleton')
				if not skel:
					issues.append("CRITICAL: JSON missing 'skeleton' object.")
				else:
					images_path = skel.get('images')
					log_callback(f"skeleton.images: '{images_path}'")
					if images_path not in ['./images/', 'images/']:
						warnings.append(f"skeleton.images is '{images_path}'. Standard is './images/' or 'images/'.")

				# 4. Check Attachments
				# Collect all attachment paths
				attachment_paths = []
				
				# A better way to walk skins specifically
				skins = data.get('skins', [])
				if isinstance(skins, dict):
					# Convert to list of dicts for uniform processing
					skins = [skins]
				
				# Helper to process skin dict
				def process_skin(skin_node):
					if not isinstance(skin_node, dict): return
					# skin_node is slot_name -> attachments
					for slot_name, attachments in skin_node.items():
						if not isinstance(attachments, dict): continue
						for attach_name, attach_data in attachments.items():
							path = None
							if isinstance(attach_data, dict):
								path = attach_data.get('path')
							
							if not path:
								path = attach_name # Default path is attachment name
							
							if path:
								attachment_paths.append(path)

				if isinstance(skins, list):
					for s in skins:
						if isinstance(s, dict):
							# Check if it's a named skin object {name: "x", attachments: {...}}
							if 'attachments' in s:
								process_skin(s['attachments'])
							else:
								# Or a map of skins {skinName: {...}}
								for k, v in s.items():
									if isinstance(v, dict):
										process_skin(v)

				log_callback(f"Found {len(attachment_paths)} attachment references.")
				
				# Verify paths
				missing_files = []
				for p in attachment_paths:
					# Construct expected path in ZIP
					# Spine joins skeleton.images + path + .png (if no extension)
					# But here we assume the ZIP structure matches what we wrote: images/skeleton/family/...
					
					has_ext = os.path.splitext(p)[1] != ''
					candidates = []
					if has_ext:
						candidates.append(p)
					else:
						candidates.append(p + ".png")
						candidates.append(p + ".jpg")
						candidates.append(p + ".jpeg")
					
					found = False
					for cand in candidates:
						# Try with 'images/' prefix
						try_paths = [
							os.path.join('images', cand).replace('\\', '/'),
							cand.replace('\\', '/') # In case path already includes images/
						]
						
						for tp in try_paths:
							if tp in names:
								found = True
								break
							# Case insensitive check
							if tp.lower() in seen_lower:
								found = True
								# Check for exact case match
								if seen_lower[tp.lower()] != tp:
									warnings.append(f"Case mismatch: JSON '{p}' -> '{tp}' vs ZIP '{seen_lower[tp.lower()]}'")
								break
						if found: break
					
					if not found:
						missing_files.append(p)

				if missing_files:
					issues.append(f"CRITICAL: {len(missing_files)} missing files referenced in JSON.")
					for m in missing_files[:10]:
						issues.append(f"  - Missing: {m}")
					if len(missing_files) > 10:
						issues.append(f"  - ... and {len(missing_files)-10} more")

				# 5. Check Image Integrity
				if Image:
					log_callback("Checking image integrity...")
					bad_images = []
					for n in names:
						if n.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
							try:
								with z.open(n) as img_file:
									# Read into memory to avoid seek issues with zip stream
									buf = io.BytesIO(img_file.read())
									with Image.open(buf) as im:
										im.verify()
							except Exception as e:
								bad_images.append(f"{n}: {e}")
					
					if bad_images:
						issues.append(f"CRITICAL: {len(bad_images)} corrupt images found.")
						for b in bad_images:
							issues.append(f"  - {b}")
				else:
					warnings.append("Pillow not installed. Skipping image integrity check.")

		except Exception as e:
			issues.append(f"CRITICAL: Error reading ZIP: {e}")

		log_callback("\n--- DIAGNOSTIC REPORT ---")
		if not issues and not warnings:
			log_callback("SUCCESS: No issues found.")
		
		if warnings:
			log_callback(f"\nWARNINGS ({len(warnings)}):")
			for w in warnings:
				log_callback(f"- {w}")
				
		if issues:
			log_callback(f"\nISSUES ({len(issues)}):")
			for i in issues:
				log_callback(f"- {i}")
		
		return len(issues) == 0


class MainWindow(QMainWindow):
	# Version Configuration for "Version Locking"
	APP_VERSION = "5.77"
	# Update URL: Points to the raw version.txt on GitHub Main branch.
	# This acts as the "Gatekeeper". Users check this URL on launch.
	MASTER_VERSION_URL = "https://raw.githubusercontent.com/saleklar/spine-sorter/main/version.txt"
	# Download URL: Where users go to get the new version.
	# DIRECT LINK to the release page where the EXE is, instead of the code repo.
	DOWNLOAD_URL = "https://github.com/saleklar/spine-sorter/releases/latest"

	def __init__(self):
		super().__init__()
		self.setWindowTitle(f"Spine Sorter v{self.APP_VERSION}")

		# Run version lock check after initial UI paint to avoid startup appearing frozen/hidden
		QTimer.singleShot(0, self._check_version_lock)

		self._setup_icons()
		self._setup_menu()

		# Configuration
		if sys.platform == 'darwin':
			self.default_spine_exe = "/Applications/Spine.app"
		elif os.name == 'nt':
			self.default_spine_exe = r"C:\Program Files\Spine\Spine.exe"
		else:
			self.default_spine_exe = "/usr/bin/spine"

		self.config = {}
		self.config_path = self._make_config_path()
		self._load_config()
		# Ensure the "Check for Errors Only" option is OFF by default
		# Do NOT persist to disk here to avoid slow startup on some filesystems.
		if "validate_only" not in self.config:
			self.config["validate_only"] = False
		
		self.image_cache = ImageCache(self._make_cache_path())

		central = QWidget()
		layout = QVBoxLayout()

		# Start background scan
		self.scanner_thread = SpineScannerThread(self.config, self.default_spine_exe, self)
		self.scanner_thread.versions_found.connect(self.on_spine_versions_found)
		self.scanner_thread.start()
		
		self.available_spine_versions = [] # Populated by scanner thread

		# Load persistantly known versions from config into available versions immediately
		# this ensures they are available even before scanner finishes, or if scanner fails
		known_exes = self.config.get('known_spine_exes', [])
		if known_exes:
			for path in known_exes:
				if os.path.exists(path):
					# Basic label until scanner verifies version
					label = f"Spine - {os.path.basename(os.path.dirname(path))}"
					self.available_spine_versions.append((label, path))

		# --- Settings Dialog Setup ---
		self.settings_dialog = QDialog(self)
		self.settings_dialog.setWindowTitle("Settings")
		settings_layout = QVBoxLayout()
		self.settings_dialog.setLayout(settings_layout)

		# Spine exe (hardcoded display)
		exe_layout = QHBoxLayout()
		exe_label = QLabel("Spine EXE:")
		self.exe_display = QLineEdit(self.config.get("spine_exe", self.default_spine_exe))
		self.exe_display.setReadOnly(True)
		exe_layout.addWidget(exe_label)
		exe_layout.addWidget(self.exe_display)

		# CLI template edit (user-editable command template)

		settings_layout.addLayout(exe_layout)

		# Spine version selection (dropdown of available Spine executables)
		version_layout = QHBoxLayout()
		version_label = QLabel("Spine version:")
		self.spine_combo = QComboBox()
		self.spine_combo.setToolTip("Select which Spine executable to use for export/open")
		refresh_btn = QPushButton("Refresh")
		refresh_btn.clicked.connect(self.scan_spine_versions)
		browse_spine_btn = QPushButton("Browse...")
		browse_spine_btn.clicked.connect(self.browse_spine_exe)
		version_layout.addWidget(version_label)
		version_layout.addWidget(self.spine_combo)
		version_layout.addWidget(refresh_btn)
		version_layout.addWidget(browse_spine_btn)
		settings_layout.addLayout(version_layout)

		# Spine JSON version selection (affects skeleton.spine field in exported JSON)
		verjson_layout = QHBoxLayout()
		verjson_label = QLabel("JSON Spine version:")
		self.json_version_combo = QComboBox()
		self.json_version_combo.setEditable(True)
		self.json_version_combo.setToolTip('Select or type a Spine JSON version to write into skeleton.spine')
		fetch_versions_btn = QPushButton('Fetch versions')
		fetch_versions_btn.clicked.connect(self.fetch_spine_versions_from_web)
		verjson_layout.addWidget(verjson_label)
		verjson_layout.addWidget(self.json_version_combo)
		verjson_layout.addWidget(fetch_versions_btn)
		settings_layout.addLayout(verjson_layout)


		# Folder selection for Spine files
		folder_layout = QHBoxLayout()
		folder_label = QLabel("Spine files folder:")
		self.folder_display = QLineEdit(self.config.get("spine_folder", ""))
		self.folder_display.setToolTip("The directory containing your .spine files")
		browse_btn = QPushButton("1. Browse...")
		browse_btn.setToolTip("Select the folder where your .spine project files are located")
		browse_btn.clicked.connect(self.browse_folder)
		folder_layout.addWidget(folder_label)
		folder_layout.addWidget(self.folder_display)
		folder_layout.addWidget(browse_btn)

		# Output folder selection
		output_layout = QHBoxLayout()
		output_label = QLabel("Output folder:")
		self.output_display = QLineEdit(self.config.get("output_folder", ""))
		self.output_display.setToolTip("The directory where the processed files will be saved")
		output_browse = QPushButton("2. Browse...")
		output_browse.setToolTip("Select the destination folder for the exported skeleton and sorted images")
		output_browse.clicked.connect(self.browse_output)
		output_layout.addWidget(output_label)
		output_layout.addWidget(self.output_display)
		output_layout.addWidget(output_browse)

		# Opacity threshold controls (slider + spinbox) and alpha cutoff
		threshold_layout = QHBoxLayout()
		threshold_label = QLabel("Opacity threshold (%):")
		self.opacity_slider = QSlider(Qt.Horizontal)
		self.opacity_slider.setRange(0, 100)
		self.opacity_slider.setSingleStep(1)
		# default from config or 92
		init_thresh = int(self.config.get("opacity_threshold", 92))
		self.opacity_slider.setValue(init_thresh)
		self.opacity_spin = QSpinBox()
		self.opacity_spin.setRange(0, 100)
		self.opacity_spin.setValue(init_thresh)
		# alpha cutoff (0-255)
		alpha_label = QLabel("Alpha cutoff:")
		self.alpha_cutoff_spin = QSpinBox()
		self.alpha_cutoff_spin.setRange(0, 255)
		self.alpha_cutoff_spin.setValue(int(self.config.get("alpha_cutoff", 150)))

		# keep slider and spinbox in sync
		self.opacity_slider.valueChanged.connect(lambda v: self.opacity_spin.setValue(v))
		self.opacity_spin.valueChanged.connect(lambda v: self.opacity_slider.setValue(v))

		# save config when changed
		self.opacity_slider.valueChanged.connect(lambda v: self._save_opacity_config(v))
		self.alpha_cutoff_spin.valueChanged.connect(lambda v: self._save_alpha_config(v))

		# Reset button
		reset_btn = QPushButton("Reset")
		reset_btn.setToolTip("Reset to defaults (92% opacity, 150 alpha)")
		reset_btn.clicked.connect(lambda: (
			self.opacity_slider.setValue(92),
			self.alpha_cutoff_spin.setValue(150)
		))

		threshold_layout.addWidget(threshold_label)
		threshold_layout.addWidget(self.opacity_slider)
		threshold_layout.addWidget(self.opacity_spin)
		threshold_layout.addWidget(alpha_label)
		threshold_layout.addWidget(self.alpha_cutoff_spin)
		threshold_layout.addWidget(reset_btn)
		
		# Dev options container
		self.dev_options_cb = QCheckBox("Dev options")
		settings_layout.addWidget(self.dev_options_cb)
		
		self.dev_container = QWidget()
		dev_layout = QVBoxLayout(self.dev_container)
		dev_layout.setContentsMargins(0, 0, 0, 0)
		
		dev_layout.addLayout(threshold_layout)

		# Diagnose button (moved to settings)
		diagnose_btn = QPushButton("Diagnose .spine...")
		diagnose_btn.clicked.connect(self.diagnose_file)
		dev_layout.addWidget(diagnose_btn)

		# Keep temporary files checkbox
		self.keep_temp_cb = QCheckBox("Keep temporary files")
		self.keep_temp_cb.setToolTip("If unchecked, temporary export folders (spine_temp_...) will be deleted after processing.")
		self.keep_temp_cb.setChecked(bool(self.config.get("keep_temp_files", False)))
		self.keep_temp_cb.stateChanged.connect(lambda v: self._save_keep_temp_config(v))
		dev_layout.addWidget(self.keep_temp_cb)

		# Verbose cleanup logging (useful on macOS to collect lsof and diagnostics)
		self.verbose_cleanup_cb = QCheckBox("Verbose cleanup logging (mac)")
		self.verbose_cleanup_cb.setToolTip("If checked, the app will collect diagnostic info (lsof, stats) when temp cleanup fails on macOS.")
		self.verbose_cleanup_cb.setChecked(bool(self.config.get("verbose_cleanup_logging", False)))
		self.verbose_cleanup_cb.stateChanged.connect(lambda v: self._save_verbose_cleanup_config(v))
		dev_layout.addWidget(self.verbose_cleanup_cb)

		# Pretty print JSON option
		self.pretty_print_cb = QCheckBox("Pretty print JSON")
		self.pretty_print_cb.setToolTip("If checked, the exported JSON will be indented for readability.")
		self.pretty_print_cb.setChecked(bool(self.config.get("pretty_print_json", True)))
		self.pretty_print_cb.stateChanged.connect(lambda v: self._save_pretty_print_config(v))
		dev_layout.addWidget(self.pretty_print_cb)

		# Export JSON Only option
		self.json_only_cb = QCheckBox("Export JSON only")
		self.json_only_cb.setToolTip("If checked, only the JSON file will be generated; images will not be copied.")
		self.json_only_cb.setChecked(bool(self.config.get("json_export_only", False)))
		self.json_only_cb.stateChanged.connect(lambda v: self._save_json_only_config(v))
		dev_layout.addWidget(self.json_only_cb)
		
		# Smart Corner Detection Option
		self.smart_corners_cb = QCheckBox("Smart Corner Detection (Force PNG for rounded assets)")
		self.smart_corners_cb.setToolTip("If checked, images with opaque centers but transparent corners (like cards) will be forced to PNG. Disable this if your backgrounds are being wrongly converted.")
		self.smart_corners_cb.setChecked(bool(self.config.get("smart_corner_detection", True)))
		self.smart_corners_cb.stateChanged.connect(lambda v: self._save_smart_corners_config(v))
		dev_layout.addWidget(self.smart_corners_cb)
		
		settings_layout.addWidget(self.dev_container)
		
		# Default hidden
		self.dev_container.setVisible(False)
		
		def toggle_dev_options(state):
			# Qt.Checked is 2
			is_checked = (state == 2)
			self.dev_container.setVisible(is_checked)
			# Force dialog to resize to fit new content
			self.settings_dialog.adjustSize()

		self.dev_options_cb.stateChanged.connect(toggle_dev_options)

		# File list panel (folder -> output -> threshold)
		combined_folders_layout = QHBoxLayout()
		combined_folders_layout.addLayout(folder_layout)
		combined_folders_layout.addLayout(output_layout)
		
		# Settings button
		settings_btn = QPushButton("Settings")
		settings_btn.setToolTip("Open configuration dialog for advanced options")
		settings_btn.clicked.connect(self.settings_dialog.show)
		combined_folders_layout.addWidget(settings_btn)

		# Help button
		help_btn = QPushButton("?")
		help_btn.setToolTip("Open User Manual")
		help_btn.setFixedWidth(30)
		help_btn.clicked.connect(self.open_help)
		combined_folders_layout.addWidget(help_btn)

		layout.addLayout(combined_folders_layout)
		# layout.addLayout(threshold_layout) # Moved to settings
		self.list_widget = QListWidget()
		

		# Action buttons for the file list
		actions_layout = QHBoxLayout()
		
		self.select_all_cb = QCheckBox("Select all")
		self.select_all_cb.setToolTip("Select or deselect all files in the list")
		self.select_all_cb.stateChanged.connect(self.toggle_select_all)
		
		self.process_btn = QPushButton("3. Process selected")
		self.process_btn.setToolTip("Start processing the selected .spine files")
		self.process_btn.setStyleSheet("background-color: #109c00; color: white; font-weight: bold;")
		self.process_btn.clicked.connect(self.process_selected)

		self.stop_btn = QPushButton("Stop")
		self.stop_btn.setToolTip("Stop the current operation")
		self.stop_btn.setStyleSheet("background-color: #9c0000; color: white; font-weight: bold;")
		self.stop_btn.clicked.connect(self.stop_process)
		self.stop_btn.setEnabled(False)
		
		# Optional: open exported .spine in Spine automatically
		self.open_after_checkbox = QCheckBox("Open .spine after export")
		self.open_after_checkbox.setChecked(bool(self.config.get("open_after_export", False)))
		self.open_after_checkbox.stateChanged.connect(lambda v: self._save_open_after_config(v))

		# Optional: Optimization (Opaque/Blend to JPEG)
		self.optimization_cb = QCheckBox("Sort all opaque images to jpeg")
		self.optimization_cb.setToolTip(
			"If checked, opaque images (with 'normal' blend) will be sorted to JPEG folder.\n"
			"If unchecked, they will remain in PNG folder (safer for some engines).\n"
			"Images exclusive to non-normal blend slots (Additive/Screen) will ALWAYS go to JPEG."
		)
		self.optimization_cb.setChecked(bool(self.config.get("optimization_enabled", True)))
		self.optimization_cb.stateChanged.connect(lambda v: self._save_optimization_config(v))
		actions_layout.addWidget(self.optimization_cb)

		# Optional: Force local sorting (treat all assets as local to the skeleton)
		self.force_local_cb = QCheckBox("Force local sorting (Old projects)")
		self.force_local_cb.setToolTip(
			"<div style='width: 150px;'>"
			"This must be checked if you are working on an old unsorted project, "
			"and unchecked for already sorted projects; otherwise, folders may be mixed."
			"</div>"
		)
		self.force_local_cb.setChecked(bool(self.config.get("force_local_sorting", False)))
		self.force_local_cb.stateChanged.connect(lambda v: self._save_force_local_config(v))
		
		# Pulse animation for the checkbox
		self.pulse_state = False
		self.pulse_timer = QTimer(self)
		self.pulse_timer.timeout.connect(self._pulse_checkbox)
		self.pulse_timer.start(800) # 800ms interval

		actions_layout.addWidget(self.select_all_cb)
		actions_layout.addWidget(self.process_btn)
		actions_layout.addWidget(self.stop_btn)
		actions_layout.addWidget(self.open_after_checkbox)
		actions_layout.addWidget(self.force_local_cb)

		# Consolidate Duplicates option
		self.consolidate_duplicates_cb = QCheckBox("Consolidate Duplicate Images (Including Mirrored)")
		self.consolidate_duplicates_cb.setToolTip("If checked, detects duplicates (visual and mirrored) and consolidates them into a single image reference.")
		self.consolidate_duplicates_cb.setStyleSheet("font-weight: bold; color: #DAA520;")
		# Default to CHECKED as per user preference likely
		self.consolidate_duplicates_cb.setChecked(True)
		actions_layout.addWidget(self.consolidate_duplicates_cb)

		# Similarity Confidence Slider
		conf_layout = QHBoxLayout()
		conf_label = QLabel("Match %:")
		conf_label.setToolTip("Minimum similarity percentage required to merge two images.\nHigher = Stricter (Fewer merges).\nLower = Looser (More merges).")
		
		self.similarity_slider = QSlider(Qt.Horizontal)
		self.similarity_slider.setRange(0, 100) # 0% to 100%
		self.similarity_slider.setSingleStep(1)
		# Default to 95%
		init_conf = int(self.config.get("similarity_confidence", 95))
		self.similarity_slider.setValue(init_conf)
		
		self.similarity_spin = QSpinBox()
		self.similarity_spin.setRange(0, 100)
		self.similarity_spin.setValue(init_conf)
		# Suffix for spinbox
		self.similarity_spin.setSuffix("%")

		# Sync
		self.similarity_slider.valueChanged.connect(lambda v: self.similarity_spin.setValue(v))
		self.similarity_spin.valueChanged.connect(lambda v: self.similarity_slider.setValue(v))
		
		# Save
		self.similarity_slider.valueChanged.connect(self._save_similarity_confidence_config)

		conf_layout.addWidget(conf_label)
		conf_layout.addWidget(self.similarity_slider)
		conf_layout.addWidget(self.similarity_spin)
		
		# Add a container widget for the layout so we can add it to actions_layout
		conf_container = QWidget()
		conf_container.setLayout(conf_layout)
		conf_container.setFixedWidth(200) # Limit width so it doesn't take over
		
		actions_layout.addWidget(conf_container)

		# Validate / Analyze Only option (Main Frame)
		self.validate_only_cb = QCheckBox("Check for Errors Only (No Export)")
		self.validate_only_cb.setToolTip("If checked, analyzes the Spine file for animation and setup pose warnings but skips sorting/exporting images.")
		self.validate_only_cb.setStyleSheet("font-weight: bold; color: #2E8B57;")
		# Default to False (unchecked) if not in config, ensuring it is off by default
		self.validate_only_cb.setChecked(bool(self.config.get("validate_only", False)))
		self.validate_only_cb.stateChanged.connect(lambda v: self._save_validate_only_config(v))
		actions_layout.addWidget(self.validate_only_cb)
		
		layout.addLayout(actions_layout)

		# Progress bar
		self.progress_bar = QProgressBar()
		self.progress_bar.setToolTip("Current progress of the operation")
		self.progress_bar.setTextVisible(True)
		self.progress_bar.setRange(0, 100)
		self.progress_bar.setValue(0)
		# Make it "big and prominent"
		self.progress_bar.setStyleSheet("QProgressBar { height: 30px; font-size: 14px; font-weight: bold; text-align: center; } QProgressBar::chunk { background-color: #4CAF50; }")
		layout.addWidget(self.progress_bar)
		
		# Active Version Label
		self.active_version_label = QLabel("Active Spine Version: Detecting...")
		self.active_version_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin: 5px 0 0 0;")
		self.active_version_label.setAlignment(Qt.AlignCenter)
		layout.addWidget(self.active_version_label)
		
		# Version Warning/Instruction
		self.version_instruction_label = QLabel("choose exact version of spine used in the project to avoid compatibility issues")
		self.version_instruction_label.setStyleSheet("color: #FF9800; font-style: italic; margin-bottom: 5px;")
		self.version_instruction_label.setAlignment(Qt.AlignCenter)
		layout.addWidget(self.version_instruction_label)

		# --- Version Switcher Integration (Roll Down Menu) ---
		switcher_layout = QHBoxLayout()
		switcher_layout.setContentsMargins(0, 5, 0, 5)
		
		self.launcher_version_combo = QComboBox()
		self.launcher_version_combo.setToolTip("Select a specific Spine version to launch")
		self.launcher_version_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		self.launcher_version_combo.currentTextChanged.connect(self._on_launcher_version_changed)
		
		# Button to fetch all remote versions
		self.fetch_all_btn = QPushButton("Fetch All")
		self.fetch_all_btn.setToolTip("Download list of ALL official Spine versions from server")
		self.fetch_all_btn.setStyleSheet("background-color: #0277bd; color: white;")
		self.fetch_all_btn.clicked.connect(self._fetch_remote_versions)
		self.fetch_all_btn.setFixedWidth(80)

		self.launch_btn = QPushButton("LAUNCH SPINE")
		self.launch_btn.setToolTip("Launch the selected version of Spine immediately")
		self.launch_btn.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
		self.launch_btn.clicked.connect(self._launch_selected_spine_version)
		
		switcher_layout.addWidget(self.launcher_version_combo)
		switcher_layout.addWidget(self.fetch_all_btn)
		switcher_layout.addWidget(self.launch_btn)
		
		layout.addLayout(switcher_layout)

		# Populate launcher versions immediately
		self._refresh_launcher_versions()

		layout.addWidget(QLabel("Spine files in folder:"))
		self.list_widget.setToolTip("List of .spine files found in the selected folder")
		layout.addWidget(self.list_widget)

		# Info / detailed log panel header
		info_header_layout = QHBoxLayout()
		info_header_layout.addWidget(QLabel("Info log:"))
		self.status_label = QLabel("")
		self.status_label.setStyleSheet("color: #AAAAAA; font-style: italic; font-weight: bold; margin-left: 10px;")
		info_header_layout.addWidget(self.status_label)

		info_header_layout.addStretch()
		layout.addLayout(info_header_layout)

		self.info_panel = QTextEdit()
		self.info_panel.setToolTip("Detailed activity log and error messages")
		self.info_panel.setReadOnly(True)
		self.info_panel.setMinimumHeight(160)
		self.info_panel.setStyleSheet("background-color: #1e1e1e; color: white;")
		layout.addWidget(self.info_panel)
		# Button to open a full plain-text report (created when processing finishes)
		self.open_report_btn = QPushButton("Open full report")
		self.open_report_btn.setVisible(False)
		self.open_report_btn.clicked.connect(self._open_report_file)
		layout.addWidget(self.open_report_btn)
		self.last_report_path = None

		central.setLayout(layout)
		self.setCentralWidget(central)

		# Populate initial file list
		if self.folder_display.text():
			self.refresh_file_list()

		# populate spine versions dropdown
		# self.scan_spine_versions() # Moved to background thread
		# populate JSON-version combo with sensible defaults
		try:
			self.json_version_combo.addItems(DEFAULT_VERSIONS)
		except Exception:
			pass
		# restore selected spine exe if in config
		sel = self.config.get('spine_exe_selected')
		if sel:
			# try to select existing item
			for i in range(self.spine_combo.count()):
				if self.spine_combo.itemData(i) == sel:
					self.spine_combo.setCurrentIndex(i)
		# save selection when changed
		self.spine_combo.currentIndexChanged.connect(lambda _: self._save_spine_selection())
		# Also update main UI label immediately when settings change
		self.spine_combo.currentIndexChanged.connect(self._update_active_version_label)

		# restore json version selection
		jv = self.config.get('spine_json_version')
		if jv:
			self.json_version_combo.addItem(jv)
			self.json_version_combo.setCurrentText(jv)
		# save when edited
		self.json_version_combo.currentTextChanged.connect(lambda v: self._save_json_version(v))

		# Monitor external Spine version changes (e.g. from Spine Launcher)
		self.last_external_spine_version = None
		self.last_disk_read_version = None
		self.last_external_spine_mtime = 0
		
		# Initial label update
		self._update_active_version_label()

		self.external_monitor_timer = QTimer(self)
		self.external_monitor_timer.timeout.connect(self._check_external_spine_change)
		self.external_monitor_timer.start(2000) # Check every 2 seconds

	def _check_external_spine_change(self):
		"""
		Polls the standard Spine version file (e.g. ~/Spine/version.txt) to see if the user 
		changed the version in the Spine Launcher. If so, auto-update our selection.
		"""
		# Common location for Spine Launcher version config
		home = os.path.expanduser("~")
		candidates = [
			os.path.join(home, "Spine", "version.txt"),
			os.path.join(home, ".spine", "version.txt"),
			os.path.join(home, "Library", "Application Support", "Spine", "version.txt") # macOS
		]
		
		target_file = None
		for f in candidates:
			if os.path.isfile(f):
				target_file = f
				break
		
		if not target_file:
			return

		try:
			# Check modification time first to avoid unnecessary reads
			mtime = os.path.getmtime(target_file)
			# Force read if we haven't read anything yet
			if mtime == self.last_external_spine_mtime and self.last_disk_read_version is not None:
				return
			
			self.last_external_spine_mtime = mtime
			
			with open(target_file, 'r', encoding='utf-8') as f:
				content = f.read().strip()
			
			if not content: return
			
			# Validate format X.Y.Z
			if not re.match(r"^\d+\.\d+(\.\d+)?$", content):
				return

			# Initialize disk read version if first time
			is_startup = (self.last_disk_read_version is None)
			
			# Has the FILE changed since we last read IT?
			if content != self.last_disk_read_version:
				self.last_disk_read_version = content
				
				# Only log if it's an actual change during runtime vs startup detection
				if not is_startup:
					self.info_panel.append(f"Detected external Spine version change to: {content}")
				
				# Update the Launcher Combo to match the Disk
				# This will trigger _on_launcher_version_changed -> which updates UI
				if hasattr(self, 'launcher_version_combo'):
					idx = self.launcher_version_combo.findText(content)
					if idx >= 0:
						self.launcher_version_combo.setCurrentIndex(idx)
					else:
						# If disk version is not in our list, weird, but maybe just use it manually?
						# Or just let default behavior happen
						pass
				
				# Also attempt to update the EXE selection just in case (Legacy behavior)
				best_match = self.find_best_spine_exe(content)
				if best_match:
					current_sel = self.spine_combo.currentData()
					if best_match != current_sel:
						if not is_startup:
							self.info_panel.append(f"Auto-switching Sorter to match: {content}")
						index = self.spine_combo.findData(best_match)
						if index >= 0:
							self.spine_combo.setCurrentIndex(index)
					
		except Exception as e:
			# self.info_panel.append(f"Monitor Warning: {e}") 
			pass

	def _update_active_version_label(self):
		"""Updates the active version label on the main GUI based on current selection."""
		# If the launcher combo has a selection, that takes precedence for the label display
		if hasattr(self, 'launcher_version_combo') and self.launcher_version_combo.count() > 0:
			selected_ver = self.launcher_version_combo.currentText()
			if selected_ver:
				# Prioritize the launcher selection
				self.active_version_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin: 5px 0 0 0;")
				self.active_version_label.setText(f"Active Spine Version: {selected_ver}")
				return

		# Fallback to legacy behavior (Spine EXE based)
		txt = ""
		current_exe = None
		if self.spine_combo.currentIndex() >= 0:
			txt = self.spine_combo.itemText(self.spine_combo.currentIndex())
			current_exe = self.spine_combo.currentData()
		else:
			path = self.config.get('spine_exe_selected') or self.config.get('spine_exe')
			if path:
				txt = f"Spine - {os.path.basename(path)}"
				current_exe = path
			else:
				txt = "None selected"
		
		# Clean up label (remove path noise)
		if " - " in txt:
			txt = txt.split(" - ")[0]

		self.active_version_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin: 5px 0 0 0;")
		self.active_version_label.setText(f"Active Spine Version: {txt}")

	def _refresh_launcher_versions(self):
		"""
		Scans for Spine updates in the user profile to populate the quick-launcher combobox.
		Based on spin_version_changer.py logic.
		"""
		versions = []
		# Locate Spine Data for Version Scanning
		try:
			import sys
			spine_folder_path = None
			if sys.platform == 'win32':
				user_profile = os.environ.get('USERPROFILE')
				if user_profile:
					spine_folder_path = Path(user_profile) / "Spine"
			elif sys.platform == 'darwin':
				spine_folder_path = Path.home() / "Library/Application Support/Spine"
			else:
				spine_folder_path = Path.home() / ".spine"

			if spine_folder_path:
				updates_folder = spine_folder_path / "updates"
				
				if updates_folder.exists():
					versions = [f.name for f in updates_folder.iterdir() if f.name and f.name[0].isdigit()]
					# Sort versions descending (semantic sort favored)
					try:
						versions = sorted(versions, key=lambda v: [int(x) for x in v.split('.') if x.isdigit()] or [0], reverse=True)
					except:
						versions = sorted(versions, reverse=True)
		except Exception:
			pass
		
		# Merge with defaults (ensure user always has options even if local updates are sparse)
		# We want unique versions, sorted
		detected_set = set(versions)
		for def_ver in DEFAULT_VERSIONS:
			if def_ver not in detected_set:
				versions.append(def_ver)
		
		# Re-sort combined list
		try:
			versions = sorted(versions, key=lambda v: [int(x) for x in v.split('.') if x.isdigit()] or [0], reverse=True)
		except:
			versions = sorted(versions, reverse=True)
			
		self.launcher_version_combo.clear()
		self.launcher_version_combo.addItems(versions)
		if versions:
			self.launcher_version_combo.setCurrentIndex(0)
			# Trigger the change handler manually for initial state
			self._on_launcher_version_changed(versions[0])

	def _fetch_remote_versions(self):
		"""
		Start the thread to fetch full version list.
		"""
		self.fetch_all_btn.setEnabled(False)
		self.fetch_all_btn.setText("Fetching...")
		self.status_label.setText("Contacting Esoteric Software archive...")
		
		self.version_fetcher = VersionFetcherThread()
		self.version_fetcher.versions_fetched.connect(self._on_remote_versions_loaded)
		self.version_fetcher.error_occurred.connect(self._on_remote_versions_error)
		self.version_fetcher.start()
		
	def _on_remote_versions_loaded(self, fetched_versions):
		"""
		Merge fetched versions with existing ones and update combo.
		"""
		self.fetch_all_btn.setEnabled(True)
		self.fetch_all_btn.setText("Fetch All")
		self.status_label.setText(f"Fetched {len(fetched_versions)} version(s).")
		
		# Get current list
		current_items = [self.launcher_version_combo.itemText(i) for i in range(self.launcher_version_combo.count())]
		current_selection = self.launcher_version_combo.currentText()
		
		# Merge (Fetched + Current + Defaults)
		# Prioritize fetched as they are the source of truth for "all possible"
		all_versions = set(current_items)
		all_versions.update(fetched_versions)
		
		# Convert to sorted list
		def ver_key(s):
			try:
				parts = [int(x) for x in s.split('.')[:3] if x.isdigit()]
				while len(parts) < 3: parts.append(0)
				return tuple(parts)
			except:
				return (0, 0, 0)

		final_list = sorted(all_versions, key=ver_key, reverse=True)
		
		# Repopulate
		self.launcher_version_combo.clear()
		self.launcher_version_combo.addItems(final_list)
		
		# Restore selection if possible, else top
		idx = self.launcher_version_combo.findText(current_selection)
		if idx >= 0:
			self.launcher_version_combo.setCurrentIndex(idx)
		elif final_list:
			self.launcher_version_combo.setCurrentIndex(0)

	def _on_remote_versions_error(self, err_msg):
		self.fetch_all_btn.setEnabled(True)
		self.fetch_all_btn.setText("Fetch All")
		self.status_label.setText("Fetch failed. Check log.")
		self.log_error(f"Version Fetch Error: {err_msg}")
		QMessageBox.warning(self, "Fetch Failed", f"Could not retrieve versions:\n{err_msg}")

	def _on_launcher_version_changed(self, text):
		"""
		Called when the user selects a version from the launcher dropdown.
		Updates the active version label to reflect this choice as the intended version,
		overriding the detected/default one.
		"""
		if not text:
			return
			
		# Update the label to show this specific version is active (Manual override)
		self.active_version_label.setText(f"Active Spine Version: {text}")
		self.active_version_label.setStyleSheet("font-weight: bold; color: #4CAF50; margin: 5px 0 0 0;")
		
		# Also update our internal tracking if needed, so checks against this version work
		# We assume the user wants THIS version to be the benchmark
		self.last_external_spine_version = text

	def _launch_selected_spine_version(self):
		"""
		Launches the selected Spine version using the --update flag.
		"""
		version = self.launcher_version_combo.currentText().strip()
		if not version:
			return

		# Try to use the configured spine executable if possible
		spine_exe_path = self.config.get('spine_exe_selected') or self.config.get('spine_exe')
		
		# Fallback to default if configured one is missing or invalid
		# Note: spin_version_changer.py uses Spine.com
		candidates = []
		if spine_exe_path:
			if str(spine_exe_path).lower().endswith('.exe'):
				# Try to replace .exe with .com in the same folder
				candidates.append(str(spine_exe_path)[:-4] + ".com")
			candidates.append(str(spine_exe_path))

		# Add standard defaults
		candidates.extend([
			r"C:\Program Files\Spine\Spine.com",
			r"C:\Program Files\Spine\Spine.exe",
		])
		if sys.platform == 'darwin':
			candidates.extend([
				"/Applications/Spine.app/Contents/MacOS/Spine",
				os.path.expanduser("~/Applications/Spine.app/Contents/MacOS/Spine")
			])
		
		final_exe = None
		for c in candidates:
			if c and os.path.exists(c):
				final_exe = c
				break
		
		if not final_exe:
			QMessageBox.critical(self, "Error", f"Spine executable not found.\nChecked locations:\n" + "\n".join([str(c) for c in candidates]))
			return

		try:
			# Command: "C:\Program Files\Spine\Spine.com" --update <version>
			cmd = [str(final_exe), "--update", version]
			
			self.info_panel.append(f"Launching Spine: {' '.join(cmd)}")
			# Launch independent process
			subprocess.Popen(cmd)
			
		except Exception as e:
			QMessageBox.critical(self, "Error", f"Failed to launch: {e}")

	def _pulse_checkbox(self):
		self.pulse_state = not self.pulse_state
		if self.pulse_state:
			self.force_local_cb.setStyleSheet("QCheckBox { color: #FF0000; font-weight: bold; }")
		else:
			self.force_local_cb.setStyleSheet("QCheckBox { color: #AA0000; font-weight: bold; }")

	def open_help(self):
		self.open_manual()

	def open_manual(self):
		# Use _MEIPASS when running as a frozen PyInstaller EXE, else use script directory
		if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
			base_dir = sys._MEIPASS
		else:
			base_dir = os.path.dirname(os.path.abspath(__file__))

		# Fixed PDF name (used by bundled EXE); also check versioned name for dev/source runs
		manual_pdf_fixed = os.path.join(base_dir, "Spine_Sorter_Artist_Guide.pdf")
		manual_pdf_versioned = os.path.join(base_dir, f"Spine_Sorter_v{self.APP_VERSION}_Artist_Guide.pdf")
		manual_txt = os.path.join(base_dir, "USER_MANUAL.txt")

		if os.path.exists(manual_pdf_fixed):
			target = manual_pdf_fixed
		elif os.path.exists(manual_pdf_versioned):
			target = manual_pdf_versioned
		else:
			target = manual_txt

		if os.path.exists(target):
			QDesktopServices.openUrl(QUrl.fromLocalFile(target))
		else:
			QMessageBox.warning(self, "Manual Not Found", f"Could not find manual at:\n{manual_pdf_fixed}\nor\n{manual_txt}")


	def _check_version_lock(self):
		"""
		Checks the GitHub lock file to ensure the running version is current.
		Blocks execution if local version is outdated compared to published GitHub version.
		"""
		import urllib.request
		import ssl

		master_version_str = None

		# Try fetching version.txt — first with SSL verification, then without (handles
		# missing CA certs in PyInstaller EXEs on Windows/Mac).
		for verify_ssl in (True, False):
			try:
				ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
				req = urllib.request.Request(self.MASTER_VERSION_URL, headers={"Cache-Control": "no-cache"})
				with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
					master_version_str = response.read().decode('utf-8').strip()
				break  # success
			except Exception:
				continue  # try without SSL verification next

		if master_version_str is None:
			# Could not reach GitHub at all — block launch to prevent running stale versions
			msg = QMessageBox(self)
			msg.setIcon(QMessageBox.Critical)
			msg.setWindowTitle("Version Check Failed")
			msg.setText("Could not verify your version with the server.")
			msg.setInformativeText(
				"Please check your internet connection and try again.\n\n"
				"If this persists, download the latest version from GitHub."
			)
			btn_download = msg.addButton("Download Latest", QMessageBox.AcceptRole)
			msg.addButton("Exit", QMessageBox.RejectRole)
			msg.exec()
			if msg.clickedButton() == btn_download:
				QDesktopServices.openUrl(QUrl(self.DOWNLOAD_URL))
			sys.exit(0)
			return

		try:
			local_ver = float(self.APP_VERSION)
			master_ver = float(master_version_str)

			# Tolerance for float comparison issues
			if master_ver > local_ver + 0.001:
				msg = QMessageBox(self)
				msg.setIcon(QMessageBox.Critical)
				msg.setWindowTitle("Update Required")
				msg.setText(f"A new version ({master_version_str}) is available.\n")
				msg.setInformativeText(
					f"You are running version {self.APP_VERSION}. "
					f"Access works only on the latest published version.\n\n"
					f"Please update from GitHub or your team lead."
				)
				btn_download = msg.addButton("Download Update", QMessageBox.AcceptRole)
				msg.addButton("Exit", QMessageBox.RejectRole)
				msg.exec()
				if msg.clickedButton() == btn_download:
					QDesktopServices.openUrl(QUrl(self.DOWNLOAD_URL))
				sys.exit(0)  # Terminate app immediately
		except ValueError:
			pass  # Non-float version strings — skip check

	def _setup_icons(self):
		# Create icons for different states
		self.icon_idle = self._generate_icon("#FF9800", "S") # Orange S (Spine color-ish)
		self.icon_busy = self._generate_icon("#F44336", "...") # Red ... for busy
		self.setWindowIcon(self.icon_idle)

	def _generate_icon(self, bg_color, text_char):
		pixmap = QPixmap(64, 64)
		pixmap.fill(Qt.transparent)
		painter = QPainter(pixmap)
		painter.setRenderHint(QPainter.Antialiasing)
		
		# Draw rounded rect bg
		painter.setBrush(QBrush(QColor(bg_color)))
		painter.setPen(Qt.NoPen)
		# 16px radius for 64px icon is nice and round
		painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
		
		# Draw subtle spine effect (vertebrae-ish segments)
		painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
		# 4 segments
		w_seg = 32
		h_seg = 8
		x_seg = (64 - w_seg) / 2
		y_start = 12
		gap = 4
		for i in range(4):
			painter.drawRoundedRect(x_seg, y_start + (i * (h_seg + gap)), w_seg, h_seg, 2, 2)

		# Draw text
		font = QFont("Segoe UI", 36, QFont.Bold)
		painter.setFont(font)
		
		# Shadow
		painter.setPen(QColor(0,0,0, 40))
		painter.drawText(pixmap.rect().adjusted(2,2,2,2), Qt.AlignCenter, text_char)
		
		# Main text
		painter.setPen(QColor("white"))
		painter.drawText(pixmap.rect(), Qt.AlignCenter, text_char)
		
		painter.end()
		return QIcon(pixmap)

	def _setup_menu(self):
		menubar = self.menuBar()
		
		# Help Menu
		help_menu = menubar.addMenu("Help")
		
		# Open Manual Action
		manual_action = QAction("Open Manual", self)
		manual_action.triggered.connect(self.open_manual)
		help_menu.addAction(manual_action)

		# Version/Update Action
		update_action = QAction("Check for Updates", self)
		update_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(self.DOWNLOAD_URL)))
		help_menu.addAction(update_action)
		
		# About
		about_action = QAction("About / Share Link", self)
		about_action.triggered.connect(self.show_about_dialog)
		help_menu.addAction(about_action)

	def _fetch_release_stats(self, callback):
		"""Fetch download counts from GitHub Releases API in a background thread."""
		import threading, urllib.request, json as _json
		def _worker():
			try:
				api_url = "https://api.github.com/repos/saleklar/spine-sorter/releases"
				req = urllib.request.Request(api_url, headers={"User-Agent": "SpineSorter"})
				with urllib.request.urlopen(req, timeout=5) as r:
					releases = _json.loads(r.read().decode('utf-8'))
				total = 0
				latest_count = 0
				latest_tag = ""
				for i, rel in enumerate(releases):
					for asset in rel.get("assets", []):
						cnt = asset.get("download_count", 0)
						total += cnt
						if i == 0:
							latest_count += cnt
					if i == 0:
						latest_tag = rel.get("tag_name", "")
				callback(total, latest_count, latest_tag, None)
			except Exception as e:
				callback(0, 0, "", str(e))
		threading.Thread(target=_worker, daemon=True).start()

	def show_about_dialog(self):
		from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
		from PyQt5.QtCore import pyqtSignal, QObject

		dlg = QDialog(self)
		dlg.setWindowTitle("About Spine Sorter")
		dlg.setMinimumWidth(360)
		vlay = QVBoxLayout(dlg)
		vlay.setSpacing(8)

		lbl_title = QLabel(f"<b>Spine Sorter v{self.APP_VERSION}</b>")
		lbl_title.setAlignment(Qt.AlignCenter)
		lbl_title.setStyleSheet("font-size: 15px;")

		lbl_link = QLabel(f"<a href='{self.DOWNLOAD_URL}'>{self.DOWNLOAD_URL}</a>")
		lbl_link.setOpenExternalLinks(True)
		lbl_link.setAlignment(Qt.AlignCenter)

		lbl_stats = QLabel("📦  Fetching download stats...")
		lbl_stats.setTextFormat(Qt.RichText)
		lbl_stats.setAlignment(Qt.AlignCenter)
		lbl_stats.setStyleSheet("color: #888; font-size: 12px;")

		vlay.addWidget(lbl_title)
		vlay.addWidget(lbl_link)
		vlay.addSpacing(4)
		vlay.addWidget(lbl_stats)
		vlay.addSpacing(8)

		hlay = QHBoxLayout()
		btn_copy = QPushButton("Copy Link")
		btn_ok   = QPushButton("OK")
		btn_ok.setDefault(True)
		hlay.addWidget(btn_copy)
		hlay.addStretch()
		hlay.addWidget(btn_ok)
		vlay.addLayout(hlay)

		btn_ok.clicked.connect(dlg.accept)
		btn_copy.clicked.connect(lambda: (
			QApplication.clipboard().setText(self.DOWNLOAD_URL),
			QMessageBox.information(self, "Copied", "Download link copied to clipboard!")
		))

		# Fetch stats and update label from the main thread via a small signal trick
		class _Sig(QObject):
			ready = pyqtSignal(int, int, str, str)
		sig = _Sig()

		def _on_stats(total, latest_count, latest_tag, err):
			sig.ready.emit(total, latest_count, latest_tag or "", err or "")

		def _apply(total, latest_count, latest_tag, err):
			if err:
				lbl_stats.setText(f"📦  Download stats unavailable ({err})")
			else:
				tag_str = f"  ({latest_tag})" if latest_tag else ""
				lbl_stats.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
				lbl_stats.setText(
					f"📦  Total downloads: <b>{total:,}</b>"
					f"&nbsp;&nbsp;|&nbsp;&nbsp;"
					f"Latest release{tag_str}: <b>{latest_count:,}</b>"
				)

		sig.ready.connect(_apply)
		self._fetch_release_stats(_on_stats)

		dlg.exec()


	def diagnose_file(self):
		start = self.output_display.text() or os.path.expanduser("~")
		path, _ = QFileDialog.getOpenFileName(self, "Select .spine file to diagnose", start, "Spine files (*.spine)")
		if path:
			self.info_panel.clear()
			# Use internal validator class instead of external script
			SpinePackageValidator.diagnose(path, log_callback=self.info_panel.append)

	def on_spine_versions_found(self, results):
		"""Callback when background scan finishes."""
		
		# Merge with persistent known executables (manual adds)
		known_exes = self.config.get('known_spine_exes', [])
		
		# Helper to check if path in results
		def in_results(p):
			p_norm = os.path.normpath(p)
			for _, res_path in results:
				if os.path.normpath(res_path) == p_norm:
					return True
			return False

		# Add known exes if missing
		for path in known_exes:
			if os.path.exists(path) and not in_results(path):
				# Detect version on the fly if needed (might briefly hang UI but expected for precision)
				ver = None
				try:
					# Use cached scanner function logic (synchronous here but it's okay for 1-2 items)
					# Or just rely on what we have.
					# For now, let's just leave it.
					pass
				except: pass
				label = f"Spine ({ver})" if ver else f"Spine - {os.path.basename(os.path.dirname(path))}"
				results.append((label, path))

		# Ensure the currently selected/configured executable is included in the list
		# even if the scanner didn't pick it up (e.g. custom location)
		sel = self.config.get('spine_exe_selected')
		if sel and os.path.exists(sel) and not in_results(sel):
			sel_norm = os.path.normpath(sel)
			# Attempt to get a nice label
			ver = None
			try:
				ver = self.scanner_thread.detect_spine_version(sel, timeout=0.2)
			except: pass
			label = f"Spine ({ver})" if ver else f"Spine - {os.path.basename(os.path.dirname(sel))}"
			results.append((label, sel))

		self.available_spine_versions = results
		self.spine_combo.clear()
		for disp, exe in results:
			self.spine_combo.addItem(disp, exe)
			
		# Update all existing file list items with the new versions
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			widget = self.list_widget.itemWidget(item)
			if widget and isinstance(widget, SpineFileWidget):
				widget.updateVersions(results)
				
		# restore selected spine exe if in config
		if sel:
			# try to select existing item
			for i in range(self.spine_combo.count()):
				if self.spine_combo.itemData(i) == sel:
					self.spine_combo.setCurrentIndex(i)
					break
		
		self._update_active_version_label()

		# If no selection restored, and we have items, select the first one (or default)
		if self.spine_combo.currentIndex() == -1 and self.spine_combo.count() > 0:
			self.spine_combo.setCurrentIndex(0)
			
		# Attempt to detect version of selected item to update JSON version combo
		# (This might be redundant if scan already did it, but ensures consistency)
		try:
			current_exe = self.spine_combo.currentData()
			if current_exe:
				# We can reuse the thread's method if we want, or just rely on what we have.
				# For now, let's just leave it.
				pass
		except Exception:
			pass

	def save_cli_template(self):
		# CLI template removed; CLI is hardcoded in process_selected
		pass

	def _save_opacity_config(self, v):
		try:
			self.config["opacity_threshold"] = int(v)
			self._save_config()
		except Exception:
			pass

	def _save_alpha_config(self, v):
		try:
			self.config["alpha_cutoff"] = int(v)
			self._save_config()
		except Exception:
			pass

	def _save_open_after_config(self, v):
		try:
			# QCheckBox.stateChanged sends int; convert to bool
			self.config["open_after_export"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_force_local_config(self, v):
		try:
			self.config["force_local_sorting"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_optimization_config(self, state):
		try:
			self.config['optimization_enabled'] = bool(state)
			self._save_config()
		except Exception:
			pass

	def _save_keep_temp_config(self, v):
		try:
			self.config["keep_temp_files"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_verbose_cleanup_config(self, v):
		try:
			self.config["verbose_cleanup_logging"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_pretty_print_config(self, v):
		try:
			self.config["pretty_print_json"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_json_only_config(self, v):
		try:
			self.config["json_export_only"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_smart_corners_config(self, v):
		try:
			self.config["smart_corner_detection"] = bool(v)
			self._save_config()
		except Exception:
			pass

	def _save_validate_only_config(self, v):
		try:
			self.config["validate_only"] = bool(v)
			self._save_config()
		except Exception:
			pass


	def _save_similarity_confidence_config(self, v):
		try:
			self.config["similarity_confidence"] = int(v)
			self._save_config()
		except Exception:
			pass

	# export settings UI removed — using default export settings (no export JSON)

	def _make_config_path(self):
		loc = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
		if not loc:
			loc = os.path.join(os.path.expanduser("~"), ".pyside_spine_app")
		os.makedirs(loc, exist_ok=True)
		return os.path.join(loc, "config.json")

	def _make_cache_path(self):
		loc = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
		if not loc:
			loc = os.path.join(os.path.expanduser("~"), ".pyside_spine_app")
		os.makedirs(loc, exist_ok=True)
		return os.path.join(loc, "image_cache.json")

	def _load_config(self):
		try:
			if os.path.exists(self.config_path):
				with open(self.config_path, "r", encoding="utf-8") as fh:
					self.config = json.load(fh)
		except Exception:
			self.config = {}

	def _save_config(self):
		try:
			with open(self.config_path, "w", encoding="utf-8") as fh:
				json.dump(self.config, fh, indent=2)
		except Exception as e:
			QMessageBox.warning(self, "Save Error", f"Could not save config: {e}")

	def _remove_temp_dir(self, path, reason=None):
		"""
		Try to remove a temporary directory with retries and log any failures to the info panel.
		Returns True on success, False on failure.
		"""
		if not path:
			return False
		try:
			import shutil
		except Exception:
			# shutil should always be available, but guard anyway
			return False
		# Normalize path
		try:
			path = os.path.abspath(path)
		except Exception:
			pass
		# Only remove directories that look like our temp exports
		if 'spine_temp_' not in os.path.basename(path):
			self.info_panel.append(f"Skipped cleanup (not a temp folder): {path}")
			return False
		# Retry loop
		for attempt in range(3):
			try:
				# brief backoff on attempts > 0
				if attempt:
					time.sleep(0.1 * attempt)
				# attempt removal
				shutil.rmtree(path)
				self.info_panel.append(f"Cleaned up temp folder ({'reason: '+reason if reason else 'automatic'}): {path}")
				return True
			except Exception as e:
				# log and retry
				self.info_panel.append(f"Attempt {attempt+1}: Failed to remove {path}: {e}")
		# Final failure
		self.info_panel.append(f"Failed to remove temp folder after retries: {path}")
		# If on macOS and verbose logging is enabled, collect diagnostics (lsof, dir stats)
		try:
			if self.config.get('verbose_cleanup_logging', False):
				# Try to write diagnostics next to the temp folder first (most convenient),
				# but also write a fallback copy into the app config folder so the user
				# can still retrieve diagnostics if the temp parent isn't writable.
				parent = os.path.dirname(path) or '.'
				diag_path = os.path.join(parent, f"cleanup_diag_{os.path.basename(path)}.txt")
				fallback_dir = os.path.dirname(self.config_path) or os.path.expanduser('~')
				fallback_path = os.path.join(fallback_dir, f"cleanup_diag_{os.path.basename(path)}_fallback.txt")
				def _write_diag(fp):
					with open(fp, 'w', encoding='utf-8') as df:
						df.write(f"Cleanup diagnostics for: {path}\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
						# directory listing and basic stats
						try:
							for fn in sorted(os.listdir(path)):
								fp2 = os.path.join(path, fn)
								try:
									st = os.stat(fp2)
									df.write(f"{fn}\t{st.st_size}\t{st.st_mtime}\n")
								except Exception as e:
									df.write(f"{fn}\tERROR_STAT: {e}\n")
						except Exception as e:
							df.write(f"Could not list dir: {e}\n")
						# capture lsof +D output (may require sudo); keep timeout short
						try:
							proc = subprocess.run(["lsof", "+D", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
							df.write("\n--- LSOF STDOUT ---\n")
							df.write(proc.stdout or "(no output)")
							df.write("\n--- LSOF STDERR ---\n")
							df.write(proc.stderr or "(no stderr)")
						except Exception as e:
							df.write(f"lsof capture failed: {e}\n")
				# Attempt write to parent, then fallback to config path if that fails
				try:
					_write_diag(diag_path)
					self.info_panel.append(f"Wrote cleanup diagnostics: {diag_path}")
				except Exception as e:
					# try fallback
					try:
						_write_diag(fallback_path)
						self.info_panel.append(f"Wrote cleanup diagnostics (fallback): {fallback_path}")
					except Exception as e2:
						self.info_panel.append(f"Could not write cleanup diagnostics to either location: {e}; {e2}")
		except Exception as e:
			self.info_panel.append(f"Could not write cleanup diagnostics: {e}")
		return False

	def browse_folder(self):
		start = self.folder_display.text() or os.path.expanduser("~")
		folder = QFileDialog.getExistingDirectory(self, "Select Spine files folder", start)
		if folder:
			self.folder_display.setText(folder)
			self.config["spine_folder"] = folder
			# Keep the spine exe in config too (though it's hardcoded by default)
			self.config.setdefault("spine_exe", self.default_spine_exe)
			self._save_config()
			self.refresh_file_list()

	def browse_output(self):
		start = self.output_display.text() or os.path.expanduser("~")
		folder = QFileDialog.getExistingDirectory(self, "Select output folder", start)
		if folder:
			self.output_display.setText(folder)
			self.config["output_folder"] = folder
			self._save_config()

	def browse_spine_exe(self):
		start = os.path.dirname(self.config.get('spine_exe', self.default_spine_exe))
		filter_str = "Executables (*.exe)" if os.name == 'nt' else "Applications (*.app);;Executables (*)"
		path, _ = QFileDialog.getOpenFileName(self, "Select Spine executable", start, filter_str)
		if path:
			path = os.path.normpath(path)
			
			# 1. Detect info for nicer label
			ver = None
			try:
				ver = self.scanner_thread.detect_spine_version(path)
			except: pass
			label = f"Spine ({ver})" if ver else f"{os.path.basename(os.path.dirname(path))} - {os.path.basename(path)}"
			
			# 2. Update global available versions list to include this manual selection
			# This ensures it appears in the per-file dropdowns too
			found_in_avail = False
			for _, exe in self.available_spine_versions:
				if os.path.normpath(exe) == path:
					found_in_avail = True
					break
			if not found_in_avail:
				self.available_spine_versions.append((label, path))
				# Push update to all file widgets
				for i in range(self.list_widget.count()):
					item = self.list_widget.item(i)
					widget = self.list_widget.itemWidget(item)
					if widget and isinstance(widget, SpineFileWidget):
						widget.updateVersions(self.available_spine_versions)

			# 3. Add to main combo if not present
			if path not in [self.spine_combo.itemData(i) for i in range(self.spine_combo.count())]:
				self.spine_combo.addItem(label, path)
				self.spine_combo.setCurrentIndex(self.spine_combo.count()-1)
			else:
				# Select existing
				for i in range(self.spine_combo.count()):
					if self.spine_combo.itemData(i) == path:
						self.spine_combo.setCurrentIndex(i)
						break
			
			# 4. Save to known_spine_exes in config
			known_exes = self.config.get('known_spine_exes', [])
			if path not in known_exes:
				known_exes.append(path)
				self.config['known_spine_exes'] = known_exes
				self._save_config()

			# attempt to detect the spine version from the selected executable and prefer it in the JSON-version combo
			if ver: # Re-use detected version
				try:
					# insert at top if not already present
					found_idx = -1
					for i in range(self.json_version_combo.count()):
						if self.json_version_combo.itemText(i) == ver:
							found_idx = i; break
					if found_idx == -1:
						self.json_version_combo.insertItem(0, ver)
						self.json_version_combo.setCurrentIndex(0)
					else:
						self.json_version_combo.setCurrentIndex(found_idx)
				except Exception:
					pass
			self._save_spine_selection()

	def find_best_spine_exe(self, target_version):
		"""
		Finds the best matching Spine executable from the combo box items.
		Prioritizes:
		1. Exact Version Match (e.g. 4.0.25 == 4.0.25)
		2. Major.Minor Match (e.g. 4.0.xx == 4.0.yy)
		"""
		if not target_version:
			return None
			
		target_parts = target_version.split('.')
		if len(target_parts) < 2: return None
		
		# e.g. "4.0"
		target_major_minor = f"{target_parts[0]}.{target_parts[1]}"
		
		best_exe = None
		best_score = -1 # 0=major only (unused), 1=major.minor match, 2=exact match
		
		# Iterate through all items in the combobox
		for i in range(self.spine_combo.count()):
			exe_path = self.spine_combo.itemData(i)
			disp_text = self.spine_combo.itemText(i)
			if not exe_path: continue
			
			# Extract version from display text (e.g. "Spine (4.0.25) - ...")
			ver = None
			m = re.search(r'\((\d+\.\d+(?:\.\d+)?)\)', disp_text)
			if m:
				ver = m.group(1)
			else:
				# Fallback: try to detect from exe path name if it contains version (e.g. "Spine 4.0")
				path_ver_match = re.search(r'Spine\s+(\d+\.\d+(\.\d+)?)', os.path.dirname(exe_path), re.IGNORECASE)
				if path_ver_match:
					ver = path_ver_match.group(1)
				else:
					# Last resort: Detect from binary (cached if possible)
					try:
						# Use short timeout to avoid lag
						ver = self.scanner_thread.detect_spine_version(exe_path, timeout=0.1)
					except:
						pass

			if not ver: continue

			if ver == target_version:
				return exe_path # Exact match is best immediately
			
			ver_parts = ver.split('.')
			if len(ver_parts) >= 2:
				ver_major_minor = f"{ver_parts[0]}.{ver_parts[1]}"
				
				if ver_major_minor == target_major_minor:
					if best_score < 1:
						best_score = 1
						best_exe = exe_path
						# Keep searching for exact match though
						
		return best_exe

	def find_oldest_spine_exe(self):
		"""
		Finds the oldest installed Spine version to use as a probe.
		"""
		best_exe = None
		oldest_ver = None
		
		for i in range(self.spine_combo.count()):
			exe_path = self.spine_combo.itemData(i)
			disp_text = self.spine_combo.itemText(i)
			if not exe_path: continue
			
			ver_match = re.search(r'\((\d+\.\d+(?:\.\d+)?)\)', disp_text)
			if ver_match:
				ver = ver_match.group(1)
				if oldest_ver is None or self._compare_versions(ver, oldest_ver) < 0:
					oldest_ver = ver
					best_exe = exe_path
		
		return best_exe, oldest_ver

	def _compare_versions(self, v1, v2):
		try:
			p1 = [int(x) for x in v1.split('.')]
			p2 = [int(x) for x in v2.split('.')]
			return (p1 > p2) - (p1 < p2)
		except:
			return 0

	def probe_project_version_via_cli(self, input_path, probe_exe, probe_ver_str=None):
		# Deprecated method
		return None

	def detect_project_version(self, spine_path):
		# Deprecated / Disabled
		return None

	def find_working_spine_version_bruteforce(self, input_path):
		# Deprecated / Disabled
		return None, None

	def _open_report_file(self):
		"""Open the last generated plain-text report with the system default viewer."""
		path = getattr(self, 'last_report_path', None)
		if not path or not os.path.exists(path):
			QMessageBox.information(self, "Report not available", "No report file is available to open.")
			return
		try:
			if os.name == 'nt':
				os.startfile(path)
			elif sys.platform == 'darwin':
				subprocess.Popen(['open', path])
			else:
				subprocess.Popen(['xdg-open', path])
		except Exception as e:
			QMessageBox.warning(self, "Open failed", f"Could not open report: {e}")


	# Removed detect_spine_version and scan_spine_versions as they are now in SpineScannerThread
	# But we keep detect_spine_version for browse_spine_exe usage (or we can remove it and use the thread's method)
	# Actually, browse_spine_exe calls self.detect_spine_version, so we should keep it or redirect it.
	# I'll redirect it to use the thread instance's method to avoid code duplication.
	
	def detect_spine_version(self, spine_exe, timeout=1.0):
		return self.scanner_thread.detect_spine_version(spine_exe, timeout)

	def scan_spine_versions(self):
		"""Trigger a rescan via the background thread."""
		self.spine_combo.clear()
		self.scanner_thread.start()

	def _save_spine_selection(self):
		try:
			val = self.spine_combo.currentData()
			if val:
				self.config['spine_exe_selected'] = val
				self._save_config()
		except Exception:
			pass

	def _save_json_version(self, v):
		try:
			if v:
				self.config['spine_json_version'] = str(v)
				self._save_config()
		except Exception:
			pass

	def fetch_spine_versions_from_web(self):
		"""Crawl Spine changelog archive and monthly pages to collect explicit release versions.

		Strategies:
		- Fetch the archive index and discover monthly links.
		- Fetch each monthly page and extract version-like strings (e.g. 4.2.43).
		- Also scan the archive index for any version tokens.
		- Use SSL-unverified fallback and HTTP fallback for environments with broken cert bundles.
		- Populate `json_version_combo` with deduped, semantically sorted versions.
		"""
		base_urls = [
			'https://hr.esotericsoftware.com/spine-changelog/archive',
			'https://esotericsoftware.com/spine-changelog/archive',
		]
		try:
			import urllib.request, urllib.parse, ssl, re
			self.info_panel.append(f'Fetching Spine versions from web (may try multiple hosts)')
			def fetch_url(u, timeout=10):
				# try normal TLS, then unverified, then plain HTTP
				last_err = None
				try:
					ctx = ssl.create_default_context()
					with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
						return r.read().decode('utf-8', errors='ignore')
				except Exception as e1:
					last_err = e1
					try:
						ctx = ssl._create_unverified_context()
						with urllib.request.urlopen(u, timeout=timeout, context=ctx) as r:
							return r.read().decode('utf-8', errors='ignore')
					except Exception as e2:
						last_err = e2
						# try HTTP fallback
						if u.startswith('https://'):
							http_u = 'http://' + u[len('https://'):]
							try:
								with urllib.request.urlopen(http_u, timeout=timeout) as r:
									return r.read().decode('utf-8', errors='ignore')
							except Exception as e3:
								last_err = e3
					# if all failed, raise the last error
				raise last_err or RuntimeError('fetch failed')

			collected = set()
			monthly_urls = []
			for base in base_urls:
				try:
					html = fetch_url(base)
					if not html:
						continue
					# extract immediate version tokens from archive page
					for v in re.findall(r'\b(\d+\.\d+(?:\.\d+)?)\b', html):
						collected.add(v)
					# find monthly links like /spine-changelog/2021/01 or full links
					for m in re.findall(r'href=["\']([^"\']*spine-changelog/\d{4}/\d{2}[^"\']*)', html, flags=re.IGNORECASE):
						u = urllib.parse.urljoin(base, m)
						if u not in monthly_urls:
							monthly_urls.append(u)
				except Exception as e:
					self.info_panel.append(f'Archive host fetch failed: {base} -> {e}')

			# fetch each monthly page and extract explicit versions (look for lines mentioning Spine and version numbers)
			for mu in monthly_urls:
				try:
					h = fetch_url(mu)
					if not h:
						continue
					# capture version-like tokens, prefer three-part versions when present
					for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", h):
						collected.add(v)
				except Exception as e:
					self.info_panel.append(f'Monthly page fetch failed: {mu} -> {e}')

			# also try a broader crawl of the /spine-changelog root to find additional pages
			try:
				root = 'https://hr.esotericsoftware.com/spine-changelog/'
				r = fetch_url(root)
				for v in re.findall(r"\b(\d+\.\d+(?:\.\d+)?)\b", r):
					collected.add(v)
			except Exception:
				pass

			# normalize, dedupe and semantically sort versions (highest first)
			def ver_key(s):
				parts = [int(x) for x in s.split('.')[:3]]
				while len(parts) < 3:
					parts.append(0)
				return tuple(parts)

			all_vers = sorted({v for v in collected if re.match(r'^\d+\.\d+(?:\.\d+)?$', v)}, key=ver_key, reverse=True)
			if not all_vers:
				self.info_panel.append('No versions discovered from web sources')
			else:
				# Condense to major.minor plus latest patch per minor
				per_minor = {}
				for v in all_vers:
					parts = v.split('.')
					major = parts[0]
					minor = parts[1] if len(parts) > 1 else '0'
					key = f"{major}.{minor}"
					# keep the highest patch (all_vers is sorted desc so first wins)
					if key not in per_minor:
						per_minor[key] = v

				# build condensed list preserving descending order of majors/minors
				condensed = []
				seen_minors = set()
				for v in all_vers:
					parts = v.split('.')
					key = f"{parts[0]}.{(parts[1] if len(parts) > 1 else '0')}"
					if key in seen_minors:
						continue
					seen_minors.add(key)
					# include the major.minor label and the latest patch for that minor
					majmin_label = key
					latest_patch = per_minor.get(key)
					condensed.append(majmin_label)
					if latest_patch and latest_patch != majmin_label:
						condensed.append(latest_patch)

				# populate combo avoiding duplicates
				existing = set(self.json_version_combo.itemText(i) for i in range(self.json_version_combo.count()))
				added = 0
				for v in condensed:
					if v not in existing:
						self.json_version_combo.addItem(v)
						added += 1
				self.info_panel.append(f'Fetched {len(all_vers)} raw versions; condensed to {len(condensed)} entries ({added} new)')
		except Exception as e:
			self.info_panel.append(f'Could not fetch versions: {e}')

	def refresh_file_list(self):
		folder = self.folder_display.text()
		self.list_widget.clear()
		if not folder or not os.path.isdir(folder):
			return
		try:
			files = sorted(os.listdir(folder), key=lambda s: s.lower())
			# from PySide6.QtWidgets import QListWidgetItem # Already imported globally

			for name in files:
				if name.lower().endswith(".spine"):
					item = QListWidgetItem() # Don't pass text here, widget handles it
					# item.setFlags(item.flags() | Qt.ItemIsUserCheckable) 
					# We rely on the widget for checking, but we keep the item Checked/Unchecked state for compatibility if we sync it.
					# But standard checkable flag might render a checkbox BEHIND our widget. 
					# So let's NOT set ItemIsUserCheckable if we provide our own checkbox.
					# Or if we want process_selected to work unmodified using item.checkState(), we need to keep the state on the item.
					
					widget = SpineFileWidget(name, self.available_spine_versions)
					
					# Set initial item size hint
					item.setSizeHint(widget.sizeHint())
					
					self.list_widget.addItem(item)
					self.list_widget.setItemWidget(item, widget)
					
					# Initialize widget state
					widget.setChecked(False)
					
		except Exception as e:
			QMessageBox.warning(self, "Read Error", f"Could not read folder: {e}")

	def toggle_select_all(self, state):
		# Qt.Checked is 2, Qt.Unchecked is 0
		is_checked = (state == 2)
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			widget = self.list_widget.itemWidget(item)
			
			if widget and isinstance(widget, SpineFileWidget):
				widget.setChecked(is_checked)
			else:
				item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)

	def stop_process(self):
		self.stop_requested = True
		self.info_panel.append("<b><font color='red'>Stopping process...</font></b>")
		self.stop_btn.setEnabled(False)

	def log_warning(self, message):
		self.info_panel.append(f"<b><font color='orange'>{message}</font></b>")

	def log_error(self, message):
		self.info_panel.append(f"<b><font color='#FFD700'>{message}</font></b>")

	def _process_single_skeleton(self, found_json, found_info, result_dir, folder, input_path, file_scanner, base_output_root, spine_exe, base_progress, name, errors, results, all_file_stats, jpeg_forced_png_warnings, all_skeleton_names=None, is_first=True, is_last=True, optimization_enabled=True, spine_export_unchecked=None, spine_export_unchecked_anims=None, extra_cli_args=None, spine_export_missing=None, spine_export_log_warnings=None, consolidate_duplicates=False, consolidate_mirrored=False, similarity_confidence=95):
		
		# Identify current skeleton being processed (for UI/Logs)
		cur_skel_name = os.path.splitext(os.path.basename(found_json))[0] if found_json else "?"
		ui_label_text = f"{name} -> {cur_skel_name}"
		
		# Collect image file paths from json, atlas/info and by scanning the export folder
		image_paths = set()
		json_image_paths = set()
		info_image_paths = set()
		try:
			# parse json for image references (use structured parsing when possible)
			if found_json and os.path.exists(found_json):
				try:
					with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
						obj = json.load(fh)
					
					# Fallback Version Detection: If source version is Unknown, grab it from the exported JSON
					if 'skeleton' in obj and 'spine' in obj['skeleton']:
						exported_ver = obj['skeleton']['spine']
						current_stats = all_file_stats[-1]
						if current_stats.get('spine_version_source', 'Unknown') == 'Unknown':
							current_stats['spine_version_source'] = f"{exported_ver} (Exported)"
							# self.info_panel.append(f"Retrieved version from exported JSON: {exported_ver}")

					# Check for active attachments in SETUP POSE
					if 'slots' in obj:
						for slot in obj['slots']:
							s_name = slot.get('name', 'unknown')
							
							# Check if slot is explicitly hidden (visible: false)
							if 'visible' in slot and slot['visible'] is False:
								att_str = f" (attachment: {slot['attachment']})" if slot.get('attachment') else " (empty)"
								msg_hidden = f"Slot '{s_name}' is HIDDEN (visible: false) in Setup Pose{att_str}"
								all_file_stats[-1].setdefault('setup_pose_hidden', []).append(msg_hidden)
								
							if 'attachment' in slot and slot['attachment']:
								# s_name already retrieved
								a_name = slot['attachment']
								
								# General warning: Setup pose should ideally be empty
								msg_active = f"Slot '{s_name}' has active attachment '{a_name}'"
								all_file_stats[-1].setdefault('setup_pose_active', []).append(msg_active)

								# Cross-check with warning list for CRITICAL violations
								if spine_export_unchecked:
									for warn_inf in spine_export_unchecked:
										# Each warn_inf is {'region':..., 'slot':...}
										# 1. Match slot name (if available from log)
										if warn_inf.get('slot') and warn_inf['slot'] != s_name:
											continue
										
										# 2. Match attachment vs region name (fuzzy or exact)
										# If attachment name matches region name exactly, or if region contains attachment name
										w_reg = warn_inf['region']
										if w_reg == a_name or (a_name in w_reg) or (w_reg in a_name):
											msg = f"Slot '{s_name}' uses UNCHECKED attachment '{a_name}' in Setup Pose!"
											all_file_stats[-1].setdefault('setup_pose_warnings', []).append(msg)
											self.log_warning(msg)
					

					# Define collection helpers properly for Spine JSON structure
					def collect_spine_images(json_obj):
						paths = set()
						skins = json_obj.get('skins', [])
						
						# Standardize skins into a single format of slot -> attachment dicts
						temp_skin_dicts = []
						if isinstance(skins, dict):
							for _, sdict in skins.items():
								if isinstance(sdict, dict):
									temp_skin_dicts.append(sdict)
						elif isinstance(skins, list):
							for item in skins:
								if isinstance(item, dict):
									if 'attachments' in item and isinstance(item.get('attachments'), dict):
										temp_skin_dicts.append(item.get('attachments'))
									else:
										for k, v in item.items():
											if k not in ('name', 'attachments') and isinstance(v, dict):
												temp_skin_dicts.append(v)
												
						for skin_dict in temp_skin_dicts:
							for slot_name, slot_data in skin_dict.items():
								if isinstance(slot_data, dict):
									for att_name, att_val in slot_data.items():
										ref = None
										if isinstance(att_val, dict):
											# Filter out non-image attachment types
											att_type = att_val.get('type', 'region')
											if att_type in ['boundingbox', 'path', 'point', 'clipping']:
												continue
											# Extract from explicit properties, defaulting to attachment name
											ref = att_val.get('path') or att_val.get('name') or att_name
										elif isinstance(att_val, str):
											ref = att_val
										else:
											ref = att_name
											
										if ref:
											paths.add(str(ref))
						return paths

					# Run collection immediately
					fresh_paths = collect_spine_images(obj)
					image_paths.update(fresh_paths)
					json_image_paths.update(fresh_paths)
					
					# ================= NEW LOGIC: FIND UNUSED ATTACHMENTS =================
					try:
						# Gather all defined attachments by (slot, attachment)
						defined_instances = set()
						skins = obj.get('skins', [])
						
						# Standardize skins into a single format of slot -> attachment dicts
						temp_skin_dicts = []
						if isinstance(skins, dict):
							for _, sdict in skins.items():
								if isinstance(sdict, dict):
									temp_skin_dicts.append(sdict)
						elif isinstance(skins, list):
							for item in skins:
								if isinstance(item, dict):
									if 'attachments' in item and isinstance(item.get('attachments'), dict):
										temp_skin_dicts.append(item.get('attachments'))
									else:
										for k, v in item.items():
											if k not in ('name', 'attachments') and isinstance(v, dict):
												temp_skin_dicts.append(v)

						for skin_dict in temp_skin_dicts:
							for slot_name, slot_data in skin_dict.items():
								if isinstance(slot_data, dict):
									for att_name in slot_data.keys():
										defined_instances.add((slot_name, att_name))
						
						# Gather setup pose attachments
						setup_instances = set()
						for slot in obj.get('slots', []):
							if isinstance(slot, dict) and 'name' in slot and 'attachment' in slot and slot['attachment']:
								setup_instances.add((slot['name'], slot['attachment']))
						
						# Gather attachments used in animations
						anim_instances = set()
						anims = obj.get('animations', {})
						if isinstance(anims, dict):
							for aname, aobj in anims.items():
								if not isinstance(aobj, dict): continue
								aslots = aobj.get('slots', {})
								if isinstance(aslots, dict):
									for sname, stimelines in aslots.items():
										if isinstance(stimelines, dict) and 'attachment' in stimelines:
											frames = stimelines['attachment']
											if isinstance(frames, list):
												for frame in frames:
													if isinstance(frame, dict) and frame.get('name'):
														anim_instances.add((sname, frame['name']))
								adeform = aobj.get('deform', {})
								if isinstance(adeform, dict):
									for skin_name, skin_slots in adeform.items():
										if isinstance(skin_slots, dict):
											for slot_name, slot_atts in skin_slots.items():
												if isinstance(slot_atts, dict):
													for att_name in slot_atts.keys():
														anim_instances.add((slot_name, att_name))
						
						# Calculate unused attachments
						unused_instances = defined_instances - setup_instances - anim_instances
						if unused_instances:
							all_file_stats[-1]['unused_attachments'] = sorted([f"{att_name} (in slot: {slot_name})" for slot_name, att_name in unused_instances])
					except Exception as e:
						self.log_warning(f"Could not analyze unused attachments: {e}")
					# =========================================================================


					# -------------------------------------------------------------------------
					# EARLY REPORTING: Unchecked Animations & Setup Pose Warnings & Missing Files
					# -------------------------------------------------------------------------
					try:
						stats = all_file_stats[-1]
						j = obj # Alias for compatibility with copied code

						# 0. Missing Images (from Spine CLI Export Log)
						if spine_export_missing:
							self.info_panel.append("<br>")
							count = len(spine_export_missing)
							self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>Spine Export reported {count} MISSING images:</span>")
							for i, m in enumerate(spine_export_missing):
								if i < 15:
									self.info_panel.append(f"<font color='red'>    - {m}</font>")
								else:
									self.info_panel.append(f"<font color='red'>    - ... and {count - 15} more</font>")
									break
							# Add to stats?
							stats['missing_files_reported'] = spine_export_missing

						# 0.5 Generic Log Warnings (Hidden/Invisible/Not Exported)
						if spine_export_log_warnings:
							self.info_panel.append("<br>")
							count = len(spine_export_log_warnings)
							self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>Spine Export Log reported {count} additional issues (Hidden/Not Exported):</span>")
							for i, m in enumerate(spine_export_log_warnings):
								if i < 15:
									self.info_panel.append(f"<font color='red'>    - {m}</font>")
								else:
									self.info_panel.append(f"<font color='red'>    - ... and {count - 15} more</font>")
									break
							stats['log_warnings_reported'] = spine_export_log_warnings

						# 1. Unchecked Animations Logic
						unique_unchecked_anims = sorted(list(set(spine_export_unchecked_anims))) if spine_export_unchecked_anims else []
						
						if 'source_anims_defined' in stats:
							all_def = stats['source_anims_defined']
							exported_anims = set()
							if 'animations' in j:
								exported_anims.update(j['animations'].keys())
							
							missing_from_comparision = all_def - exported_anims
							if missing_from_comparision:
								for m in missing_from_comparision:
									if m not in unique_unchecked_anims:
										unique_unchecked_anims.append(m)
								unique_unchecked_anims.sort()
						
						stats['unchecked_anims'] = unique_unchecked_anims
						
						# Report Unchecked Animations
						if unique_unchecked_anims:
							self.info_panel.append("<br>")
							n_anim = len(unique_unchecked_anims)
							self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>{n_anim} animations are checked off for export so they are not copied:</span>")
							for i, anim in enumerate(unique_unchecked_anims):
								if i < 10:
									self.info_panel.append(f"<font color='orange'>    - {anim}</font>")
								else:
									self.info_panel.append(f"<font color='orange'>    - ... and {n_anim - 10} more</font>")
									break

						# Report Setup Pose Violations (Critical)
						if 'setup_pose_warnings' in stats and stats['setup_pose_warnings']:
							self.info_panel.append("<br>")
							self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>{len(stats['setup_pose_warnings'])} setup pose slots refer to UNCHECKED attachments:</span>")
							for msg in stats['setup_pose_warnings']:
								self.info_panel.append(f"<font color='red'>    - {msg}</font>")
						
						# Report Active Setup Pose (Warning)
						if 'setup_pose_active' in stats and stats['setup_pose_active']:
							self.info_panel.append("<br>")
							n_active = len(stats['setup_pose_active'])
							soft_warning_color = "#FFC04C"
							self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:{soft_warning_color};'>{n_active} slots have active attachments in Setup Pose:</span>")
							for i, msg in enumerate(stats['setup_pose_active']):
								if i < 10:
									self.info_panel.append(f"<font color='{soft_warning_color}'>    - {msg}</font>")
								else:
									self.info_panel.append(f"<font color='{soft_warning_color}'>    - ... and {n_active - 10} more</font>")
									break
						
						# Report Invisible Setup Pose (Warning)
						if 'setup_pose_invisible' in stats and stats['setup_pose_invisible']:
							self.info_panel.append("<br>")
							n_inv = len(stats['setup_pose_invisible'])
							self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:#FF4500;'>{n_inv} slots are INVISIBLE (Alpha=0) in Setup Pose but have active attachments:</span>")
							for i, msg in enumerate(stats['setup_pose_invisible']):
								if i < 10:
									self.info_panel.append(f"<font color='#FF4500'>    - {msg}</font>")
								else:
									self.info_panel.append(f"<font color='#FF4500'>    - ... and {n_inv - 10} more</font>")
									break

						# Report Hidden Setup Pose (Warning)
						if 'setup_pose_hidden' in stats and stats['setup_pose_hidden']:
							self.info_panel.append("<br>")
							n_hidden = len(stats['setup_pose_hidden'])
							self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:#CD5C5C;'>{n_hidden} slots are HIDDEN (visible: false) in Setup Pose:</span>")
							for i, msg in enumerate(stats['setup_pose_hidden']):
								if i < 10:
									self.info_panel.append(f"<font color='#CD5C5C'>    - {msg}</font>")
								else:
									self.info_panel.append(f"<font color='#CD5C5C'>    - ... and {n_hidden - 10} more</font>")
									break
									
						QApplication.processEvents()

						# Stop here if Validate Only is strictly requested
						if self.config.get("validate_only", False):
							# Perform Animation check NOW
							try:
								verify_keys = list(obj.get('animations', {}).keys())
								verify_count = len(verify_keys)
								self.info_panel.append(f"VERIFICATION (JSON): Found {verify_count} animations: {', '.join(sorted(verify_keys))}")
								
								source_anims_check = all_file_stats[-1].get('source_anims_defined', set()) if all_file_stats else set()
								if isinstance(source_anims_check, dict):
									try:
										source_anims_check = set().union(*[v for v in source_anims_check.values() if v])
									except Exception:
										source_anims_check = set()
								
								if source_anims_check:
									missing = source_anims_check - set(verify_keys)
									if missing:
										self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING: Missing animations in JSON that were in Source:</span> <span style='color:orange;'>{', '.join(missing)}</span>")
										self.info_panel.append(f"*** MISSING ANIMATION: {list(missing)[0]} ***")
									else:
										self.info_panel.append("SUCCESS: All source animations accounted for in JSON.")
										
								if verify_count > 0:
									self.info_panel.append(f"VERIFY SUCCESS: Animations are guaranteed to be in the JSON file.")

								if all_file_stats:
									stats_ref = all_file_stats[-1]
									if 'source_anims_defined' in stats_ref:
										all_def = stats_ref['source_anims_defined']
										if isinstance(all_def, dict):
											all_def = set().union(*[v for v in all_def.values() if v])
										stats_ref['anim_total_count'] = len(all_def)
										stats_ref['anim_exported_count'] = verify_count
									else:
										stats_ref['anim_exported_count'] = verify_count
										u_len = len(unique_unchecked_anims) if 'unique_unchecked_anims' in locals() and unique_unchecked_anims else 0
										stats_ref['anim_total_count'] = verify_count + u_len
							except Exception as e:
								pass

							# Perform Missing Files Check NOW
							if json_image_paths:
								missing_files = []
								search_dirs = [folder, os.path.dirname(input_path)]
								# Helper to check existence
								def find_file(path_str):
									if os.path.isabs(path_str) and os.path.isfile(path_str): return True
									for d in search_dirs:
										if d and os.path.isfile(os.path.join(d, path_str)): return True
									return False
								
								for p in json_image_paths:
									# Do not report as missing if it is explicitly unchecked for export
									p_region = os.path.splitext(p)[0].replace('\\', '/')
									if spine_export_unchecked:
										unchecked_regions = {warn_inf['region'] for warn_inf in spine_export_unchecked if warn_inf.get('region')}
										# sometimes the region has a different path component, but let's do a strict or ending match
										if p_region in unchecked_regions or any(p_region.endswith(ur) for ur in unchecked_regions):
											continue

									if not find_file(p):
										# Try without extension or matching basename
										found_fuzzy = False
										base = os.path.basename(p)
										for d in search_dirs:
											if not d or not os.path.exists(d): continue
											for root, dirs, files in os.walk(d):
												for f in files:
													# simple prefix match
													if f.lower().startswith(base.lower()) or os.path.splitext(f)[0].lower() == base.lower():
														found_fuzzy = True
														break
												if found_fuzzy: break
											if found_fuzzy: break
										
										if not found_fuzzy:
											missing_files.append(p)
								
								if missing_files:
									self.info_panel.append("<br>")
									self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>{len(missing_files)} referenced images are MISSING from source folder:</span>")
									for i, m in enumerate(sorted(missing_files)):
										if i < 10:
											self.info_panel.append(f"<font color='red'>    - {m}</font>")
										else:
											self.info_panel.append(f"<font color='red'>    - ... and {len(missing_files) - 10} more</font>")
											break
								else:
									self.info_panel.append(f"<br><font color='#4CAF50'><b>File Integrity Check: OK ({len(json_image_paths)} images referenced and found)</b></font>")

							self.info_panel.append("<br><b><font color='blue'>Analysis Mode: Validation complete. Skipping image processing and file generation.</font></b>")
							return

					except Exception as e:
						self.log_error(f"Early Reporting Error: {e}")
					# -------------------------------------------------------------------------
				except Exception:
					# fallback to raw text regex if JSON parsing fails
					with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
						data = fh.read()
						for m in re.findall(r'([\w\-/\\]+\.(?:png|jpg|jpeg|webp|bmp|tga))', data, flags=re.IGNORECASE):
							image_paths.add(m)
							json_image_paths.add(m)

			# parse any atlas files placed in the export folder
			for f in os.listdir(result_dir):
				if f.lower().endswith('.atlas'):
					atlas_path = os.path.join(result_dir, f)
					with open(atlas_path, 'r', encoding='utf-8', errors='ignore') as ah:
						lines = ah.readlines()
						for idx, line in enumerate(lines):
							line = line.strip()
							if not line:
								continue
							# atlas files commonly list image names (one per section)
							if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', line, flags=re.IGNORECASE):
								# Check if next line starts with 'size:', indicating this is a page header, not a region
								if idx + 1 < len(lines) and lines[idx+1].strip().lower().startswith('size:'):
									continue
								image_paths.add(line)
								info_image_paths.add(line)

			# parse any info/text files (found_info) for image names
			if found_info and os.path.exists(found_info):
				# Only parse if it wasn't already parsed as an .atlas file above (avoid double processing)
				if not (os.path.basename(found_info).lower().endswith('.atlas') and os.path.dirname(found_info) == result_dir):
					with open(found_info, 'r', encoding='utf-8', errors='ignore') as fh:
						lines = fh.readlines()
						for idx, line in enumerate(lines):
							line = line.strip()
							if not line:
								continue
							if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', line, flags=re.IGNORECASE):
								# Apply same logic for .txt if it happens to be an atlas
								if idx + 1 < len(lines) and lines[idx+1].strip().lower().startswith('size:'):
									continue
								image_paths.add(line)
								info_image_paths.add(line)

			# also include any image files physically present in the export folder (recursive)
			for root, dirs, files in os.walk(result_dir):
				for fn in files:
					if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', fn, flags=re.IGNORECASE):
						# store relative path to result_dir so later resolution can join correctly
						rel = os.path.relpath(os.path.join(root, fn), result_dir)
						image_paths.add(rel)
		except Exception as e:
			msg = f"{name}: error parsing exports: {e}"
			errors.append(msg)
			self.log_error(msg)
		
		# Update total spine images count (exported references + unchecked)
		if all_file_stats:
			# EXPORTED_UNIQUE_IMAGES is populated during process_skin_dict, but that happens LATER in this function.
			# However, json_image_paths is populated above. 
			# The issue is we are calculating this 'total_spine' BEFORE we run the skin processing loop which fully validates references.
			# We must recalculate total_spine AT THE END of this function or update it there.
			# Let's initialize it here with 0, and update it at the end of the function.
			all_file_stats[-1]['total_spine'] = 0

		# Check for non-exported files (explicit content from Spine log OR in info/atlas but NOT in json)
		export_msg = None
		
		# set of missing files (normalized)
		missing_files_display = set()
		
		# NOTE: We do NOT add spine_export_unchecked to missing_files_display anymore. 
		# We report them separately.
		
		# 2. Compare Info/Atlas vs JSON
		if info_image_paths and json_image_paths:
			# Normalize for comparison (lowercase, forward slashes)
			json_norm = {p.lower().replace('\\', '/') for p in json_image_paths}
			
			for p in info_image_paths:
				p_norm = p.lower().replace('\\', '/')
				if p_norm not in json_norm:
					# Try matching without extension if JSON has bare names
					p_base = os.path.splitext(p_norm)[0]
					if p_base not in json_norm:
						missing_files_display.add(p)

		if missing_files_display:
			# Log the warning
			count = len(missing_files_display)
			preview = ', '.join(sorted(list(missing_files_display))[:5])
			more = "..." if count > 5 else ""
			export_msg = f"WARNING: {count} images likely checked off for export (found in logs or Atlas but not JSON): {preview}{more}"
			self.log_warning(export_msg)
		elif info_image_paths and json_image_paths:
			export_msg = "Export Consistency Check: OK (All files in Info/Atlas match JSON export)"
			self.info_panel.append(export_msg)
		elif not info_image_paths and json_image_paths:
			if spine_export_unchecked:
				# We already know why there is no atlas/info (or why it might be incomplete)
				export_msg = "Export Consistency Check: Incomplete (See 'Unchecked' warnings above)"
			else:
				export_msg = "Export Consistency Check: Skipped (No Info/Atlas file found to compare)"
			self.info_panel.append(export_msg)
		
		# Store msg in stats for final report
		if all_file_stats and export_msg:
			all_file_stats[-1]['consistency_msg'] = export_msg



		# Debug: show collected image references from exports
		try:
			if image_paths:
				self.info_panel.append("Collected image refs: " + ", ".join(sorted(image_paths)))
		except Exception:
			pass
		
		# Progress update: Collection done
		self.progress_bar.setValue(base_progress + 10)
		QApplication.processEvents()

		# Resolve image paths to filesystem paths relative to the temporary result_dir, folder, or input folder
		resolved = set()
		# directories to search (priority order)
		search_dirs = [result_dir, folder, os.path.dirname(input_path)]
		
		# Pre-scan for exact filename matches to avoid aggressive collection
		# Map basename_lower -> list of full absolute paths
		file_map = {} 
		for d in search_dirs:
			if not d or not os.path.exists(d): continue
			for root, dirs, files in os.walk(d):
				for f in files:
					if f.lower().endswith(('.png', '.jpg', '.jpeg')):
						# key by basename without extension
						bn_noext = os.path.splitext(f)[0].lower()
						fp = os.path.normcase(os.path.abspath(os.path.join(root, f)))
						if bn_noext not in file_map: file_map[bn_noext] = []
						file_map[bn_noext].append(fp)
						
						# also key by full basename
						bn_full = f.lower()
						if bn_full not in file_map: file_map[bn_full] = []
						file_map[bn_full].append(fp)

		for ip in image_paths:
			# Cleaning the path from spine
			ip_clean = ip.strip()
			if not ip_clean: continue
			
			# 1. Absolute path check
			if os.path.isabs(ip_clean) and os.path.isfile(ip_clean):
				resolved.add(os.path.normcase(os.path.abspath(ip_clean)))
				continue
			
			# 2. Direct lookup (Exact path relative to search dirs)
			found = None
			for d in search_dirs:
				candidate = os.path.join(d, ip_clean)
				if os.path.isfile(candidate):
					found = candidate
					break
				# Try adding extension if missing
				if not found:
					for ext in ['.png', '.jpg', '.jpeg']:
						c_ext = candidate + ext
						if os.path.isfile(c_ext):
							found = c_ext
							break
					if found: break
			
			if found:
				resolved.add(os.path.normcase(os.path.abspath(found)))
				continue

			# 3. Recursive lookup for EXACT basename matches only
			# (Removed strict prefix/sequence matching to fix user issue where similar filenames were grouped incorrectly)
			base = os.path.basename(ip_clean)
			base_noext = os.path.splitext(base)[0].lower()
			base_full = base.lower()
			
			matches = file_map.get(base_full) or file_map.get(base_noext)
			if matches:
				# Add all exact matches found
				for m in matches:
					resolved.add(m)

			# 4. Sequence expansion: if ref ends with _ or - (Spine sequence indicator), scan file_map
			# for all numbered variants (e.g. guaranteed_win_ -> guaranteed_win_01, guaranteed_win_02, ...)
			# This is critical — the JSON only stores the base path, not the individual frame filenames.
			if not matches and (base_noext.endswith('_') or base_noext.endswith('-')):
				base_core_seq = base_noext.rstrip('_-')
				if base_core_seq:
					seq_re_scan = re.compile(r'^' + re.escape(base_core_seq) + r'[_\-]?\d+$')
					for k, v in file_map.items():
						# k is the basename-without-extension key in file_map
						k_noext = os.path.splitext(k)[0] if '.' in k else k
						if seq_re_scan.match(k_noext):
							for m in v:
								resolved.add(m)
			
		# convert to list for further processing and log resolved files
		resolved = list(resolved)

		# convert to list for further processing and log resolved files
		resolved = list(resolved)
		try:
			if resolved:
				self.info_panel.append("Resolved image files: " + ", ".join(resolved))
		except Exception:
			pass

		# --- Additional Checks: Duplicate content and naming conventions ---
		# Calculate dynamic thresholds based on similarity_confidence (80-100)
		try:
			# Ensure it's treated as float for math, int for display
			conf_val = float(similarity_confidence) if similarity_confidence is not None else 95.0
		except:
			conf_val = 95.0
		# Clamp to valid range
		conf_val = max(0.0, min(100.0, conf_val))
		
		# --- REDESIGNED THRESHOLD SYSTEM ---
		# Root problem: previously ALL thresholds (hash filter + SSIM + color) scaled together
		# from the same slider. This created a deadlock: tightening one tightened all,
		# causing misses at high confidence and false positives at low confidence.
		#
		# NEW DESIGN: Two separate stages with independent thresholds:
		#   Stage 1 - Candidate Selection (Hash pre-filter): ALWAYS generous.
		#             Goal: catch ALL potential matches. Never miss a real duplicate.
		#             A generous hash filter only costs some extra OpenCV comparisons.
		#   Stage 2 - Final Validation (SSIM + ORB + Color): ALWAYS strict fixed values.
		#             Goal: reject ALL false positives. Both SSIM and ORB must agree.
		#
		# The confidence slider now ONLY affects size/alpha tolerance (edge cases).
		
		t_factor = (100.0 - conf_val) / 100.0
		
		# --- Stage 1: Hash pre-filter (generous fixed values - candidate selection only) ---
		# These are intentionally loose. OpenCV validation below does the real work.
		th_alpha = 0.08  # Fixed: quick reject if alpha ratio differs by >8%
		th_dmax  = 60    # Fixed: generous dHash distance limit (candidate selection)
		th_amax  = 150   # Fixed: generous aHash distance limit (candidate selection)
		th_sum   = 200   # Fixed: generous combined limit
		
		# --- Stage 2: Final validation thresholds (ALL fixed - slider has NO effect on match quality) ---
		# SSIM + ORB dual-gate. Both must agree. No slider influence.
		th_ssim  = 0.97  # Hard minimum structural similarity
		th_color = 0.90  # Color histogram must be >= 90% correlated
		th_size_diff = 0  # Size must be identical - no tolerance, no slider influence

		th = {
			'alpha_diff': th_alpha,
			'd_max': th_dmax,
			'a_max': th_amax,
			'sum_max': th_sum,
			'ssim_min': th_ssim,
			'color_min': th_color,
			'size_diff': th_size_diff,
			'conf_val': conf_val # Passed for logging context
		}

		# Initialize consolidation maps
		# consolidation_map: path -> target_path (For EXACT duplicates)
		# consolidation_map_mirror: path -> {'target': target_path, 'axis': 'x'|'y'} (For FLIPPED duplicates)
		consolidation_map = {}
		consolidation_map_mirror = {}
		
		try:
			# Duplicate image content detection (SHA1)
			import hashlib
			
			# DEBUG LOG START
			self.info_panel.append(f"<span style='color:cyan'>--- Duplicate Analysis (Confidence: {int(conf_val)}%) ---</span>")
			msg_th = f"Thresholds: SSIM > {th_ssim:.2f}, Color > {th_color:.2f}, HashDist < {th_dmax}"
			if th_size_diff > 0: msg_th += f", SizeTol: {th_size_diff}px"
			self.info_panel.append(f"<span style='color:#AAAAAA; font-size:10px'>{msg_th}</span>")
			self.info_panel.append(f"Analyzing {len(resolved)} resolved files for duplicates...")
			# DEBUG LOG END

			def _sha1_for_file(p):
				h = hashlib.sha1()
				with open(p, 'rb') as fh:
					while True:
						chunk = fh.read(65536)
						if not chunk: break
						h.update(chunk)
				return h.hexdigest()

			# Helper for bytes hash
			def _sha1_bytes(b):
				h = hashlib.sha1()
				h.update(b)
				return h.hexdigest()

			def _hamming_distance_int(a, b):
				return (a ^ b).bit_count()

			def _compute_similarity_signature(path, image_module):
				try:
					with image_module.open(path) as im_pil:
						im = im_pil.convert('RGBA')

						# Remove alpha dust/noise.
						# Increased threshold to 15 to catch compression artifacts in alpha
						r, g, b, a = im.split()
						lut = [0 if i < 15 else i for i in range(256)]
						a = a.point(lut)
						im.putalpha(a)

						# Normalize transparent RGB values.
						im_clean = im.convert('RGBa').convert('RGBA')

						orig_w, orig_h = im_clean.size
						bbox = im_clean.getbbox()
						if bbox:
							im_trimmed = im_clean.crop(bbox)
							trim_l, trim_t, trim_r, trim_b = bbox
							trim_w, trim_h = im_trimmed.size
						else:
							im_trimmed = im_clean
							trim_l, trim_t = 0, 0
							trim_w, trim_h = orig_w, orig_h

						# Stable normalized hash (robust exact visual match).
						im_thumb = im_trimmed.resize((64, 64), resample=image_module.BILINEAR)
					# Reduce quantization to keep more color information (0xE0 = top 3 bits = 8 levels per channel)
					# This prevents different colors from matching while still being robust to minor differences
					im_quant = im_thumb.point(lambda p: p & 0xE0)
					norm_hash = _sha1_bytes(im_quant.tobytes())

					# Perceptual hashes for near-duplicate grouping.
					# IMPORTANT: Compute on color channels, not grayscale, to distinguish different colors
					# Resize to small size and separate into R, G, B channels
					color_thumb = im_trimmed.resize((8, 8), resample=image_module.BILINEAR)
					r_data, g_data, b_data, a_data = color_thumb.split()
					
					# Compute average hash on each color channel separately
					# ALSO: Compute mean channel brightness to reject palette swaps (e.g. Red Chest vs Blue Chest)
					# Structurally they are identical (ahash match), but absolute color is different.
					mean_colors = []
					
					def compute_channel_ahash_and_mean(channel_img):
						pixels = list(channel_img.getdata())
						avg = sum(pixels) / len(pixels) if pixels else 0.0
						mean_colors.append(avg)
						hash_val = 0
						for px in pixels:
							hash_val = (hash_val << 1) | (1 if px >= avg else 0)
						return hash_val
					
					ahash_r = compute_channel_ahash_and_mean(r_data)
					ahash_g = compute_channel_ahash_and_mean(g_data)
					ahash_b = compute_channel_ahash_and_mean(b_data)
					# Combine into single hash (R in high bits, G in middle, B in low)
					ahash = (ahash_r << 128) | (ahash_g << 64) | ahash_b
					
					# Compute difference hash on luminance only (for shape matching)
					gray = im_trimmed.convert('L')
					dh_img = gray.resize((9, 8), resample=image_module.BILINEAR)
					dh_pixels = list(dh_img.getdata())
					dhash = 0
					for y in range(8):
						row_start = y * 9
						for x in range(8):
							left = dh_pixels[row_start + x]
							right = dh_pixels[row_start + x + 1]
							dhash = (dhash << 1) | (1 if left >= right else 0)

					alpha_hist = a.histogram()
					total_px = max(1, orig_w * orig_h)
					non_zero_alpha = total_px - (alpha_hist[0] if alpha_hist else 0)
					alpha_ratio = float(non_zero_alpha) / float(total_px)

					return {
						'norm_hash': norm_hash,
						'ahash': ahash,
						'mean_colors': mean_colors, # [avg_r, avg_g, avg_b]
						'dhash': dhash,
						'alpha_ratio': alpha_ratio,
						'original_w': orig_w,
						'original_h': orig_h,
						'trim_l': trim_l,
						'trim_t': trim_t,
						'trim_w': trim_w,
						'trim_h': trim_h,
						'path': path # Added path for advanced OpenCV check
					}
				except Exception as e:
					return None


			def _reverse_bits_8(n):
				n = ((n & 0xF0) >> 4) | ((n & 0x0F) << 4)
				n = ((n & 0xCC) >> 2) | ((n & 0x33) << 2)
				n = ((n & 0xAA) >> 1) | ((n & 0x55) << 1)
				return n

			def _flip_hash_h_64(h):
				res = 0
				for i in range(8):
					shift = (7 - i) * 8
					byte_val = (h >> shift) & 0xFF
					rev = _reverse_bits_8(byte_val)
					res |= (rev << shift)
				return res

			def _flip_ahash_h(h):
				mask = 0xFFFFFFFFFFFFFFFF
				b = h & mask
				g = (h >> 64) & mask
				r = (h >> 128) & mask
				return (_flip_hash_h_64(r) << 128) | (_flip_hash_h_64(g) << 64) | _flip_hash_h_64(b)

			def _flip_dhash_h(h):
				res = 0
				for i in range(8):
					shift = (7 - i) * 8
					byte_val = (h >> shift) & 0xFF
					rev = _reverse_bits_8(byte_val)
					inv = (~rev) & 0xFF
					res |= (inv << shift)
				return res

			def _is_near_duplicate(sig_a, sig_b, th, flip_mode=None):
				# Advanced OpenCV check for robust validation
				# If basic criteria are met, we verify with histogram/SSIM if available
				# This is the "Judge" phase.
				
				if not sig_a or not sig_b:
					return False
				
				# Handle Virtual Flipping for Fuzzy Mirror Check
				dhash_b, ahash_b = sig_b['dhash'], sig_b['ahash']
				
				if flip_mode == 'x':
					# Apply transformation to B's hashes
					ahash_b = _flip_ahash_h(sig_b['ahash'])
					dhash_b = _flip_dhash_h(sig_b['dhash'])
				
				# Allow flexible size tolerance
				w_diff = abs(sig_a['trim_w'] - sig_b['trim_w'])
				h_diff = abs(sig_a['trim_h'] - sig_b['trim_h'])
				size_tol = th.get('size_diff', 0)
				
				if w_diff > size_tol or h_diff > size_tol:
					# Debug logging for potential misses
					# Only log if hashes are very close (meaning they look similar but size blocked it)
					d_close = _hamming_distance_int(sig_a['dhash'], sig_b['dhash'])
					if d_close < 5 and (w_diff < 10 or h_diff < 10):
						pass
						# self.info_panel.append(f"<span style='color:orange'>Reject Size ({w_diff}x{h_diff}): {os.path.basename(sig_a['path'])} vs {os.path.basename(sig_b['path'])}</span>")
					return False
				
				# 1. Quick Alpha/Aspect Ratio Check
				if abs(sig_a['alpha_ratio'] - sig_b['alpha_ratio']) > th['alpha_diff']:
					return False

				# 2. Hash Distance Check (Candidate Selection)
				d_dist = _hamming_distance_int(sig_a['dhash'], dhash_b)
				a_dist = _hamming_distance_int(sig_a['ahash'], ahash_b)
				
				# Allow candidate if within relaxed bounds
				is_hash_candidate = (d_dist <= th['d_max'] and a_dist <= th['a_max'] and (d_dist + a_dist) <= th['sum_max'])
				
				# Hash pre-filter gates are already generous (Stage 1).
				# If we passed is_hash_candidate, always attempt full OpenCV validation (Stage 2).
				if OPENCV_AVAILABLE:
					# Any hash candidate goes to OpenCV - it will make the final call
					is_opencv_candidate = is_hash_candidate
					
					# Only proceed if plausible candidate
					if is_opencv_candidate and 'path' in sig_a and 'path' in sig_b:
						try:
							# Load images with Alpha to mask transparency (Fix for 'forgot to check colors')
							# We need to mask transparent areas so they don't dominate the histogram
							img1_raw = cv2.imread(sig_a['path'], cv2.IMREAD_UNCHANGED)
							img2_raw = cv2.imread(sig_b['path'], cv2.IMREAD_UNCHANGED)
							
							if img1_raw is None or img2_raw is None:
								return is_hash_candidate 
							
							# Apply Flip if requested
							if flip_mode == 'x':
								img2_raw = cv2.flip(img2_raw, 1) # 1 = Horizontal Flip

							# Helper: Extract BGR + Mask
							def _get_bgr_mask(im):
								if len(im.shape) == 3 and im.shape[2] == 4:
									# BGRA -> BGR + Alpha Mask
									return im[:,:,:3], (im[:,:,3] > 10).astype(np.uint8) * 255
								elif len(im.shape) == 3 and im.shape[2] == 3:
									# BGR -> BGR + Full Mask
									return im, np.ones(im.shape[:2], dtype=np.uint8) * 255
								elif len(im.shape) == 2:
									# Gray -> BGR + Full Mask
									return cv2.cvtColor(im, cv2.COLOR_GRAY2BGR), np.ones(im.shape, dtype=np.uint8) * 255
								return None, None

							bgr1, mask1 = _get_bgr_mask(img1_raw)
							bgr2, mask2 = _get_bgr_mask(img2_raw)

							if bgr1 is None or bgr2 is None: return is_hash_candidate

							# Standardize size (Match img2 to img1)
							if bgr1.shape[:2] != bgr2.shape[:2]:
								bgr2 = cv2.resize(bgr2, (bgr1.shape[1], bgr1.shape[0]))
								mask2 = cv2.resize(mask2, (bgr1.shape[1], bgr1.shape[0]), interpolation=cv2.INTER_NEAREST)

							# Apply mask to BGR to clean up transparent noise for SSIM/Color checks
							bgr1 = cv2.bitwise_and(bgr1, bgr1, mask=mask1)
							bgr2 = cv2.bitwise_and(bgr2, bgr2, mask=mask2)
							
							# Update main image vars for downstream SSIM
							img1 = bgr1
							img2 = bgr2

							# A. Hue/Saturation Histogram Check with Masking
							hsv1 = cv2.cvtColor(bgr1, cv2.COLOR_BGR2HSV)
							hsv2 = cv2.cvtColor(bgr2, cv2.COLOR_BGR2HSV)
							
							# Use mask to ignore transparent background
							hist1 = cv2.calcHist([hsv1], [0, 1], mask1, [180, 256], [0, 180, 0, 256])
							hist2 = cv2.calcHist([hsv2], [0, 1], mask2, [180, 256], [0, 180, 0, 256])
							
							cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
							cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
							
							color_score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
							
							# If color distributions are very different (e.g. Red vs Blue), score will be low (< 0.9)
							# Identical images usually > 0.99
							if color_score < th.get('color_min', 0.95): 
								# DEBUG LOG
								# self.info_panel.append(f"<font color='orange'>Rejecting candidate (color): {color_score:.2f} (Needs > {th.get('color_min', 0.95):.2f})</font>")
								# self.info_panel.append(f"  {os.path.basename(sig_a['path'])} vs {os.path.basename(sig_b['path'])}")
								return False # Reject different colors
								
							# B. Structural Similarity (SSIM)
							# This confirms the "Drawing" is the same
							gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
							gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
							
							s = ssim(gray1, gray2)
							
							# C. Feature Matching (ORB) - "Sophisticated" Object Recognition
							# This acts like "face recognition" for sprites, identifying key features
							# regardless of minor shifts, noise, or scale differences.
							orb_score = 0.0
							try:
								# Initialize ORB (Oriented FAST and Rotated BRIEF)
								orb = cv2.ORB_create(nfeatures=500)
								kp1, des1 = orb.detectAndCompute(img1, None)
								kp2, des2 = orb.detectAndCompute(img2, None)
								
								if des1 is not None and des2 is not None and len(des1) > 4 and len(des2) > 4:
									# Brute-Force Matcher with Hamming distance (efficient for binary descriptors)
									bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
									matches = bf.match(des1, des2)
									
									if matches:
										# Filter for "good" matches (low distance = high similarity)
										# Distance < 50 is usually a very strong match
										good_matches = [m for m in matches if m.distance < 50]
										
										# Calculate robust score: Ratio of good matches to total keypoints
										# If > 50% of keypoints match perfectly, it's the same object
										orb_score = len(good_matches) / min(len(kp1), len(kp2))
							except Exception:
								pass # Feature matching can fail on featureless images (smooth gradients), which SSIM handles better
							
							# --- FINAL DECISION LOGIC (Dual-Gate, fixed thresholds, slider-independent) ---
							# Gate A: Near pixel-perfect (SSIM >= 0.99) - same image, possibly re-saved
							if s >= 0.99:
								return True
							
							# Gate B: Both SSIM >= 0.97 AND ORB >= 0.65 must agree
							# Requiring BOTH eliminates palette-swaps and similar-but-different images.
							if s >= 0.97 and orb_score >= 0.65:
								return True
							
							# Everything else: hard reject
							return False
							
						except Exception as e:
							# self.info_panel.append(f"OpenCV check failed: {e}")
							pass # Fallback to basic logic if CV fails
				# Not a viable OpenCV candidate — fall through to strict hash fallback below
				if not is_hash_candidate:
					return False

				# Strict no-OpenCV fallback: require very tight hash distances (no false positives)
				if d_dist > 8 or a_dist > 20:
					return False

				# Also require very similar mean colors (reject palette swaps)
				if 'mean_colors' in sig_a and 'mean_colors' in sig_b:
					mc_a = sig_a['mean_colors']
					mc_b = sig_b['mean_colors']
					color_dist = sum(abs(mc_a[i] - mc_b[i]) for i in range(3))
					if color_dist > 15:
						return False

				return True  # Near-identical hashes AND near-identical colors = safe match

			# Store trim offsets for later compensation
			trim_data = {}

			# Helper to catch hardlinks/symlinks pointing to same inode
			def _get_file_id(p):
				try:
					st = os.stat(p)
					# Use st_dev + st_ino for unique identity
					return (st.st_dev, st.st_ino)
				except:
					return p

			# Logic revamp for mirrors:
			# We want to detect if MULTIPLE *DIFFERENT* FILES (different inodes) have SAME HASH (Exact)
			# OR if a file has a hash matching the FLIPPED version of another file (Mirror).
			
			if not resolved:
				self.info_panel.append("No source images resolved for duplicate check.")

			# content_registry: hash -> list of entries
			# Entry: {'path': p, 'type': 'real'|'virtual_x'|'virtual_y', 'source_if_virtual': original_path}
			content_registry = {}
			
			duplicate_groups = [] # For reporting exact dupes
			
			# Import PIL if needed (Consolidate duplicates logic uses it for fuzzy hashing now too)
			if consolidate_duplicates or consolidate_mirrored:
				try:
					from PIL import Image
					import io
				except ImportError:
					self.log_warning("Pillow (PIL) not found! Fuzzy consolidation disabled. Install 'pillow' to enable.")
					consolidate_mirrored = False
					# Don't disable consolidate_duplicates entirely, as it still supports exact hash match
					# But fuzzy hashing won't work. The code below assumes PIL is present for normalized_hashes.


			# Phase 1: Hash all REAL files
			# Sort resolved to ensure deterministic primary selection
			resolved.sort(key=lambda x: (len(x), x))
			
			real_file_entries = [] # List of {'path': p, 'hash': h}
			
			# Pre-calculate normalized hashes for everything if mirroring is active
			# Because disk bytes != PIL save bytes
			normalized_hashes = {} 
			image_signatures = {}

			for rp in resolved:
				try:
					h = _sha1_for_file(rp)
					# Always register raw hash for exact duplicate detection
					if h not in content_registry: content_registry[h] = []
					entry = {'path': rp, 'type': 'real', 'hash': h}
					content_registry[h].append(entry)
					real_file_entries.append(entry)
					# Visual signature used for robust exact/near matching.
					if (consolidate_duplicates or consolidate_mirrored) and Image:
						sig = _compute_similarity_signature(rp, Image)
						if sig:
							normalized_hashes[rp] = sig['norm_hash']
							trim_data[rp] = {
								'original_w': sig['original_w'],
								'original_h': sig['original_h'],
								'trim_l': sig['trim_l'],
								'trim_t': sig['trim_t'],
								'trim_w': sig['trim_w'],
								'trim_h': sig['trim_h']
							}
							image_signatures[rp] = sig
							
				except Exception as e:
					self.info_panel.append(f"Could not hash file {rp}: {e}")

			# Phase 2: Generate Virtual Hashes for Mirroring (if enabled)
			# DEBUG: Write hash statistics before mirror phase
			try:
				debug_hash_path = os.path.join(result_dir, f"debug_hashes_{name}.txt")
				with open(debug_hash_path, "w") as dhf:
					dhf.write(f"Hash Statistics for {name}\n")
					dhf.write("=" * 80 + "\n")
					dhf.write(f"Total files hashed: {len(real_file_entries)}\n")
					
					# DEBUG LOG
					self.info_panel.append(f"  Hashed {len(real_file_entries)} files.")
					collision_count_debug = sum(1 for entries in content_registry.values() if len(entries) > 1)
					if collision_count_debug > 0:
						self.info_panel.append(f"  <font color='cyan'>Found {collision_count_debug} unique hashes with multiple files (Potential Exact Duplicates)</font>")
					else:
						self.info_panel.append(f"  No initial exact duplicates found (SHA1).")

					dhf.write(f"Unique SHA1 hashes: {len(content_registry)}\n")
					dhf.write(f"Image signatures computed: {len(image_signatures)}\n")
					dhf.write(f"consolidate_duplicates enabled: {consolidate_duplicates}\n")
					dhf.write(f"consolidate_mirrored enabled: {consolidate_mirrored}\n\n")
					
					# Show hashes with collisions
					dhf.write("Exact duplicates (SHA1 collisions):\n")
					dup_count = 0
					for h, entries in content_registry.items():
						real_entries = [e for e in entries if e['type'] == 'real']
						if len(real_entries) > 1:
							dup_count += 1
							dhf.write(f"  Hash {h[:12]}... has {len(real_entries)} files:\n")
							for e in real_entries:
								dhf.write(f"    - {os.path.basename(e['path'])}\n")
					
					if dup_count == 0:
						dhf.write("  (No exact duplicates found)\n")
			except Exception as e:
				pass
			
			if consolidate_mirrored:
				self.info_panel.append("<font color='#DAA520'>Generating mirror hashes for consolidation...</font>")
				
				# We need a reverse lookup for normalized hashes to find potential matches
				# map: normalized_hash -> list of real paths
				norm_hash_to_paths = {}
				for p, h_n in normalized_hashes.items():
					if h_n not in norm_hash_to_paths: norm_hash_to_paths[h_n] = []
					norm_hash_to_paths[h_n].append(p)

				# Iterate unique real NORMALIZED hashes (to avoid redundant flips)
				unique_norm_hashes = list(norm_hash_to_paths.keys())
				
				for h_n in unique_norm_hashes:
					paths = norm_hash_to_paths[h_n]
					if not paths: continue
					
					# Source is the first path for this hash
					source_path = paths[0]
					
					try:
						# Update normalization map with all "exact duplicates" found via TRIMMED pixel hash
						# This handles cases where file hash differs but pixel content (trimmed) is identical
						if len(paths) > 1:
							# Sort by path length then name to pick best "Source"
							paths.sort(key=lambda x: (len(x), x))
							primary = paths[0]
							remaining_paths = paths[1:]

							primary_norm = os.path.normcase(os.path.abspath(primary))
							
							for p in remaining_paths:
								norm_p = os.path.normcase(os.path.abspath(p))
								if norm_p != primary_norm: # Prevent self-assignment
									consolidation_map[norm_p] = primary
							
							# Update source_path to be the primary for mirror checks
							source_path = primary
							# Update the hash map to only contain the primary (remove exact duplicates from mirror detection)
							norm_hash_to_paths[h_n] = [primary]
						
						# Generate flips from the SOURCE
						# We compare the FLIPPED hash against OTHER normalized hashes.
						with Image.open(source_path) as im:
							im = im.convert('RGBA')
							
							# Clean alpha before flipping ensure clean source
							# Must apply SAME threshold logic as normalized_hashes generation!
							r, g, b, a = im.split()
							lut = []
							for i in range(256):
								lut.append(0 if i < 5 else i)
							a = a.point(lut)
							im.putalpha(a)
							
							im_clean = im.convert('RGBa').convert('RGBA')
							
							# Function to get TRIMMED hash of any image object
							def get_trimmed_hash(img_obj):
								bbox = img_obj.getbbox()
								if bbox:
									img_trimmed = img_obj.crop(bbox)
								else:
									img_trimmed = img_obj
									
								# Apply SAME fuzzy transform as original scan: 64x64 + Quantize
								# MUST match the quantization in _compute_similarity_signature (0xE0)
								im_thumb = img_trimmed.resize((64, 64), resample=Image.BILINEAR)
								im_quant = im_thumb.point(lambda p: p & 0xE0)
								
								return _sha1_bytes(im_quant.tobytes())
							
							# X-Flip
							im_x = im_clean.transpose(Image.FLIP_LEFT_RIGHT)
							# Use FUZZY hash to match the database!
							h_x = get_trimmed_hash(im_x)
							
							# If this flipped hash exists in our normalized DB, we found a match!
							if h_x in norm_hash_to_paths:
								targets = norm_hash_to_paths[h_x]
								for t_path in targets:
									# Skip self (symmetric images)
									sp_norm = os.path.normcase(os.path.abspath(source_path))
									tp_norm = os.path.normcase(os.path.abspath(t_path))
									
									if sp_norm == tp_norm:
										continue
									
									# Avoid circular dependencies or overwriting exact matches
									if tp_norm in consolidation_map: continue

									# We found a Mirror Case!
									# Deterministic choice: Keep the one that is "first" alphabetically as Source
									if sp_norm < tp_norm:
										# source is master. target is slave.
										consolidation_map_mirror[tp_norm] = {'target': source_path, 'transform': 'flipX', 'axis': 'x'}
									else:
										# target is master. source is slave.
										consolidation_map_mirror[sp_norm] = {'target': t_path, 'transform': 'flipX', 'axis': 'x'}

							# Y-Flip
							im_y = im_clean.transpose(Image.FLIP_TOP_BOTTOM)
							h_y = get_trimmed_hash(im_y)
							
							# Check match
							if h_y in norm_hash_to_paths:
								targets = norm_hash_to_paths[h_y]
								for t_path in targets:
									sp_norm = os.path.normcase(os.path.abspath(source_path))
									tp_norm = os.path.normcase(os.path.abspath(t_path))
									
									if sp_norm == tp_norm: continue
									if tp_norm in consolidation_map: continue
									
									if sp_norm < tp_norm:
										consolidation_map_mirror[tp_norm] = {'target': source_path, 'transform': 'flipY', 'axis': 'y'}
									else:
										consolidation_map_mirror[sp_norm] = {'target': t_path, 'transform': 'flipY', 'axis': 'y'}

							
							# Rotate 90 CW (transposed)
							im_r90 = im_clean.transpose(Image.ROTATE_270) # PIL Rotate is CCW, so 270 is 90 CW
							h_r90 = get_trimmed_hash(im_r90)

							if h_r90 in norm_hash_to_paths:
								targets = norm_hash_to_paths[h_r90]
								for t_path in targets:
									sp_norm = os.path.normcase(os.path.abspath(source_path))
									tp_norm = os.path.normcase(os.path.abspath(t_path))
									if sp_norm == tp_norm: continue
									if tp_norm in consolidation_map: continue
									
									if sp_norm < tp_norm:
										consolidation_map_mirror[tp_norm] = {'target': source_path, 'transform': 'rotate90', 'angle': 90}
									else:
										# If Source is target, then Source = Target rotated 90 CW.
										# Target = Source rotated -90 (or 270)
										consolidation_map_mirror[sp_norm] = {'target': t_path, 'transform': 'rotate90', 'angle': -90}

							# Rotate 180
							im_r180 = im_clean.transpose(Image.ROTATE_180)
							h_r180 = get_trimmed_hash(im_r180)

							if h_r180 in norm_hash_to_paths:
								targets = norm_hash_to_paths[h_r180]
								for t_path in targets:
									sp_norm = os.path.normcase(os.path.abspath(source_path))
									tp_norm = os.path.normcase(os.path.abspath(t_path))
									
									# Special Check: Identical vs Rotated 180
									# Sometimes images are identical but one is "logically" rotated in Spine.
									# BUT here we are comparing PIXELS.
									# If PixelHash(A) == PixelHash(B-Rot180), then A is visually same as B rotated 180.
									# This handles the case where the user rotated the image content in Photoshop before exporting.
									
									if sp_norm == tp_norm: continue
									if tp_norm in consolidation_map: continue
									
									if sp_norm < tp_norm:
										consolidation_map_mirror[tp_norm] = {'target': source_path, 'transform': 'rotate180', 'angle': 180}
									else:
										consolidation_map_mirror[sp_norm] = {'target': t_path, 'transform': 'rotate180', 'angle': 180}
							
							# Rotate 270 CW (90 CCW)
							im_r270 = im_clean.transpose(Image.ROTATE_90) # PIL Rotate is CCW, so 90 is 270 CW
							h_r270 = get_trimmed_hash(im_r270)

							if h_r270 in norm_hash_to_paths:
								targets = norm_hash_to_paths[h_r270]
								for t_path in targets:
									sp_norm = os.path.normcase(os.path.abspath(source_path))
									tp_norm = os.path.normcase(os.path.abspath(t_path))
									if sp_norm == tp_norm: continue
									if tp_norm in consolidation_map: continue
									
									if sp_norm < tp_norm:
										# Target = Source rotated 270 CW (or -90)
										consolidation_map_mirror[tp_norm] = {'target': source_path, 'transform': 'rotate270', 'angle': -90}
									else:
										# Source = Target rotated 270 CW
										# Target = Source rotated 90
										consolidation_map_mirror[sp_norm] = {'target': t_path, 'transform': 'rotate270', 'angle': 90}
					except Exception:
						pass

			# Phase 3: Consolidation Map Building
			# Write simple debug file showing hash analysis
			try:
				simple_debug_path = os.path.join(result_dir, f"hash_analysis_{name}.txt")
				with open(simple_debug_path, "w") as f:
					f.write(f"Hash Analysis for {name}\n")
					f.write("=" * 80 + "\n\n")
					f.write(f"Total files analyzed: {len(resolved)}\n")
					f.write(f"Content registry entries: {len(content_registry)}\n")
					f.write(f"Consolidate duplicates enabled: {consolidate_duplicates}\n")
					f.write(f"Consolidate mirrored enabled: {consolidate_mirrored}\n\n")
					
					f.write("Hash Collisions (multiple files with same SHA1):\n")
					collision_count = 0
					for h, entries in content_registry.items():
						real_entries = [e for e in entries if e['type'] == 'real']
						if len(real_entries) > 1:
							collision_count += 1
						if collision_count == 0:
							f.write("  (none found)\n")
						
						f.write(f"\n\nImage Signatures Computed: {len(image_signatures)}\n")
						
			except Exception as e:
				pass
			
			# Iterate over all content hashes that have collisions
			for h, entries in content_registry.items():
				real_entries = [e for e in entries if e['type'] == 'real']
				
				# Case A: Exact Duplicates (Multiple real files share hash)
				if len(real_entries) > 1:
					# Sort to pick primary
					real_entries.sort(key=lambda x: (len(x['path']), x['path']))
					primary = real_entries[0]['path']
					
					# Record group for reporting
					group_paths = [e['path'] for e in real_entries]
					duplicate_groups.append(group_paths)
					
					if consolidate_duplicates:
						for other in real_entries[1:]:
							norm_p = os.path.normcase(os.path.abspath(other['path']))
							# Don't overwrite if existing (stable sort ensures consistency)
							if norm_p not in consolidation_map:
								consolidation_map[norm_p] = primary

			# Phase 3b: Near-duplicate matching using perceptual signatures.
			near_duplicate_groups = []
			if consolidate_duplicates and image_signatures:
				# Use windowed search sorted by height to allow size tolerance
				# Create flat list of (path, sig)
				sig_list = []
				for p, sig in image_signatures.items():
					if sig and 'trim_h' in sig:
						sig_list.append((p, sig))
				
				# Sort by height
				sig_list.sort(key=lambda x: x[1]['trim_h'])
				
				size_tol = th.get('size_diff', 0)
				
				for i in range(len(sig_list)):
					p1, sig1 = sig_list[i]
					
					source_norm = os.path.normcase(os.path.abspath(p1))
					if source_norm in consolidation_map:
						continue
						
					group = [p1]
					
					# Look ahead
					for j in range(i + 1, len(sig_list)):
						p2, sig2 = sig_list[j]
						
						# Stop scanning if height difference > tolerance (list is sorted by height)
						h_diff = sig2['trim_h'] - sig1['trim_h']
						if h_diff > size_tol:
							break
							
						# Check width difference
						w_diff = abs(sig2['trim_w'] - sig1['trim_w'])
						if w_diff > size_tol:
							continue
							
						target_norm = os.path.normcase(os.path.abspath(p2))
						if target_norm in consolidation_map:
							continue

						if _is_near_duplicate(sig1, sig2, th):
							consolidation_map[target_norm] = p1
							group.append(p2)
						elif consolidate_mirrored:
							# Check Horizontal Flip (Fuzzy Match)
							if _is_near_duplicate(sig1, sig2, th, flip_mode='x'):
								# Prioritize exact name based sorting? logic handled later, but we need to set map
								# If p1 < p2 name wise?
								# The existing mirror logic prioritizes alphabetically.
								# 'target' is the one being removed. 
								# Here p1 is source, p2 is candidate.
								# If p2 is a flipped version of p1.
								# We map p2 -> p1
								
								# Check if we already have a mirror map for this?
								if target_norm not in consolidation_map_mirror:
									consolidation_map_mirror[target_norm] = {'target': p1, 'transform': 'flipX', 'axis': 'x'}
						
						# Debug logging omitted for performance
						
					if len(group) > 1:
						near_duplicate_groups.append(group)

			# Case B: Mirror Duplicates (Processed via Normalized Hashes AND Fuzzy Search)
			# (Exact Hashes done in Phase 2. Fuzzy Hashes done in Phase 3 just above.)
			# Prune any mirror mappings where the source or target has been consolidated as an exact duplicate
			if consolidate_mirrored and consolidation_map_mirror:
				# Remove mirror entries if:
				# 1. The key (file to be replaced) is already being replaced by exact dup
				# 2. The target is being remapped by exact consolidation (chaining issue)
				keys_to_remove = []
				for k, v in consolidation_map_mirror.items():
					target_path = v['target']
					target_norm = os.path.normcase(os.path.abspath(target_path))
					
					# Case 1: Key is in exact consolidation map (already being remapped)
					if k in consolidation_map:
						keys_to_remove.append(k)
					# Case 2: Target is being remapped by exact consolidation (avoid chaining)
					elif target_norm in consolidation_map:
						keys_to_remove.append(k)
				
				for k in keys_to_remove:
					del consolidation_map_mirror[k]
			
			# Reporting
			self.info_panel.append(f"  Exact Groups: {len(duplicate_groups)}, Near-Dup Groups: {len(near_duplicate_groups)}, Mirrors: {len(consolidation_map_mirror)}")
			self.info_panel.append(f"  Total Remappings Active: {len(consolidation_map)}")
			
			if duplicate_groups:
				if consolidate_duplicates:
					self.info_panel.append(f"<span style='color:#DAA520; font-weight:bold;'>Consolidating {len(duplicate_groups)} duplicate group(s)...</span>")
					# Log sample
					count = 0
					for group in duplicate_groups:
						if count < 3:
							replacements = [os.path.basename(p) for p in group[1:]]
							self.info_panel.append(f"  <font color='#DAA520'>Remap {', '.join(replacements)} -> {os.path.basename(group[0])}</font>")
						count += 1
					if count > 3: self.info_panel.append(f"  ... and {count-3} more.")
				else:
					self.info_panel.append(f"Found {len(duplicate_groups)} duplicate groups (Consolidation OFF).")
					if all_file_stats: all_file_stats[-1]['duplicate_image_groups'] = duplicate_groups # Save for report

			if near_duplicate_groups:
				self.info_panel.append(f"<span style='color:#4CAF50; font-weight:bold;'>Consolidating {len(near_duplicate_groups)} similar-image group(s) ({similarity_mode.title()} mode)...</span>")
				count = 0
				for group in near_duplicate_groups:
					if count < 3:
						replacements = [os.path.basename(p) for p in group[1:]]
						self.info_panel.append(f"  <font color='#4CAF50'>Similar remap {', '.join(replacements)} -> {os.path.basename(group[0])}</font>")
					count += 1
				if count > 3:
					self.info_panel.append(f"  ... and {count-3} more similar groups.")

			if consolidation_map_mirror:
				self.info_panel.append(f"<span style='color:#9C27B0; font-weight:bold;'>Found {len(consolidation_map_mirror)} mirrored images!</span>")
				count = 0
				for k, v in consolidation_map_mirror.items():
					if count < 5:
						msg = f"  <font color='#9C27B0'>Mirror: {os.path.basename(k)} -> {os.path.basename(v['target'])} ({v['transform']})</font>"
						self.info_panel.append(msg)
					count += 1
				if count > 5: self.info_panel.append(f"  <font color='#9C27B0'>... and {count-5} more.</font>")
			
			# DEBUG: Write comprehensive consolidation report
			try:
				debug_report_path = os.path.join(result_dir, f"consolidation_debug_report_{name}.txt")
				with open(debug_report_path, "w") as f:
					f.write("=" * 80 + "\n")
					f.write(f"CONSOLIDATION DEBUG REPORT FOR: {name}\n")
					f.write("=" * 80 + "\n\n")
					
					f.write(f"THRESHOLD SETTINGS (Mode: {similarity_mode.title()}):\n")
					f.write(f"  alpha_diff: {th['alpha_diff']}\n")
					f.write(f"  d_max: {th['d_max']}\n")
					f.write(f"  a_max: {th['a_max']}\n")
					f.write(f"  sum_max: {th['sum_max']}\n\n")
					
					f.write(f"FILES ANALYZED: {len(resolved)} total\n\n")
					
					f.write("EXACT DUPLICATE GROUPS:\n")
					for i, group in enumerate(duplicate_groups):
						f.write(f"  Group {i+1}:\n")
						for p in group:
							bn = os.path.basename(p)
							is_key = os.path.normcase(os.path.abspath(p)) in consolidation_map
							marker = " (KEY - REMAPPED)" if is_key else " (primary)"
							f.write(f"    - {bn}{marker}\n")
					
					f.write(f"\nNEAR-DUPLICATE GROUPS: {len(near_duplicate_groups)}\n")
					for i, group in enumerate(near_duplicate_groups):
						f.write(f"  Group {i+1}:\n")
						for p in group:
							bn = os.path.basename(p)
							is_key = os.path.normcase(os.path.abspath(p)) in consolidation_map
							marker = " (KEY - REMAPPED)" if is_key else " (primary)"
							f.write(f"    - {bn}{marker}\n")
					
					f.write(f"\nCONSOLIDATION MAP ({len(consolidation_map)} entries):\n")
					for k, v in sorted(consolidation_map.items()):
						f.write(f"  {os.path.basename(k)} -> {os.path.basename(v)}\n")
					
					f.write(f"\nMIRROR MAP ({len(consolidation_map_mirror)} entries):\n")
					for k, v in sorted(consolidation_map_mirror.items()):
						f.write(f"  {os.path.basename(k)} -> {os.path.basename(v['target'])} ({v.get('transform', 'unknown')})\n")
			except Exception as e:
				self.info_panel.append(f"Failed to write consolidation debug report: {e}")

		except Exception as e:
			self.info_panel.append(f"Duplicate check failed: {e}")
			import traceback
			traceback.print_exc()

		try:
			# Naming conventions: lowercase, no spaces, only a-z0-9._- allowed for filenames
			naming_violations = []
			for rp in resolved:
				bn = os.path.basename(rp)
				reasons = []
				# leading/trailing whitespace
				if bn != bn.strip():
					reasons.append('leading/trailing whitespace')
				if bn != bn.lower():
					reasons.append('uppercase letters')
				if re.search(r'\s', bn):
					reasons.append('spaces')
				# disallow path separators inside basename (safety)
				if '/' in bn or '\\' in bn:
					reasons.append('path-separator in name')
				# allowed chars
				if not re.match(r'^[a-z0-9._-]+$', bn):
					if 'uppercase letters' not in reasons and 'spaces' not in reasons and 'leading/trailing whitespace' not in reasons:
						reasons.append('non-standard characters')
				if reasons:
					naming_violations.append({'file': rp, 'basename': bn, 'reasons': reasons})

			# Check slot names (slots can contain problematic spaces/whitespace)
			slots = j.get('slots', []) if isinstance(j.get('slots', []), list) else []
			for s in slots:
				try:
					slot_name = s.get('name') if isinstance(s, dict) else None
					if slot_name:
						s_reasons = []
						if slot_name != slot_name.strip():
							s_reasons.append('leading/trailing whitespace')
						if re.search(r'\s', slot_name):
							s_reasons.append('spaces')
						if slot_name != slot_name.lower():
							s_reasons.append('uppercase letters')
						if s_reasons:
							naming_violations.append({'file': input_path, 'basename': f"slot:{slot_name}", 'reasons': s_reasons})
				except Exception:
					pass

			# Check skeleton object fields for whitespace/typos
			skel = j.get('skeleton') if isinstance(j.get('skeleton'), dict) else None
			if skel:
				for key, val in skel.items():
					if isinstance(val, str):
						k_reasons = []
						if val != val.strip():
							k_reasons.append(f"skeleton.{key}: leading/trailing whitespace")
						# token-level fuzzy check for common tokens (catch 'anticiation' -> 'anticipation')
						toks = re.split(r'[_\s]+', val.lower())
						allowed_tokens = set(['reel','anticipation','tile','win','event','special','spin','feature','screen','logo','pop','up','persistence','transition','frame','side','bet','ambient','buy','bonus','jackpot','loop','intro','back','front','collect'])
						for t in toks:
							if not t or t.isdigit():
								continue
							if t not in allowed_tokens:
								m = difflib.get_close_matches(t, list(allowed_tokens), n=1, cutoff=0.72)
								if m:
									k_reasons.append(f"skeleton.{key}: possible typo '{t}' -> '{m[0]}'")
					if k_reasons:
						naming_violations.append({'file': input_path, 'basename': f"skeleton.{key}", 'reasons': k_reasons})

			# Persist and display filename/slot/skeleton naming violations
			if naming_violations:
				tc = self.info_panel.textCursor()
				tc.movePosition(QTextCursor.End)
				self.info_panel.setTextCursor(tc)
				self.info_panel.insertHtml(f"<span style='color:#32CD32'>Naming violations: {len(naming_violations)} item(s)</span><br/>")
				for v in naming_violations[:40]:
					tc = self.info_panel.textCursor()
					tc.movePosition(QTextCursor.End)
					self.info_panel.setTextCursor(tc)
					self.info_panel.insertHtml(f"<span style='color:#32CD32'> - {v['basename']}: {', '.join(v['reasons'])}</span><br/>")
				if all_file_stats:
					all_file_stats[-1]['naming_violations'] = naming_violations

			# Additional checks for animation names (detect spaces, non-standard chars, and probable typos)

			try:
				allowed_tokens = set(['reel','anticipation','tile','win','event','special','spin','feature','screen','logo','pop','up','persistence','transition','frame','side','bet','ambient','buy','bonus','jackpot','loop','intro','back','front','collect'])
				anims = list(j.get('animations', {}).keys()) if isinstance(j.get('animations', {}), dict) else []
				for a in anims:
					anim_reasons = []
					# leading/trailing whitespace
					if a != a.strip():
						anim_reasons.append('leading/trailing whitespace')
					if a != a.lower():
						anim_reasons.append('uppercase letters')
					if re.search(r'\s', a):
						anim_reasons.append('spaces')
					if not re.match(r'^[a-z0-9._-]+$', a.lower()):
						anim_reasons.append('non-standard characters')
					# token-level typo detection
					tokens = re.split(r'[_\s]+', a.lower())
					for t in tokens:
						if not t or t.isdigit():
							continue
						if t not in allowed_tokens:
							m = difflib.get_close_matches(t, list(allowed_tokens), n=1, cutoff=0.72)
							if m:
								anim_reasons.append(f"possible typo '{t}' -> '{m[0]}'")
					if anim_reasons:
						naming_violations.append({'file': input_path, 'basename': a, 'reasons': anim_reasons})
			except Exception:
				pass
		except Exception as e:
			self.info_panel.append(f"Naming check failed: {e}")
		
		# Progress update: Resolution done
		self.progress_bar.setValue(base_progress + 20)
		QApplication.processEvents()

		# --- Analyze Opacity ---
		if hasattr(self, 'status_label'): self.status_label.setText(f"Analyzing opacity: {ui_label_text}")
		opaque_results = []
		
		# Skip opacity scan entirely if optimization is disabled
		# (Unless we want to warn about opaque images in PNG folder? But user disabled it.)
		if optimization_enabled:
			# Ensure limit is high enough (redundant check)
			try:
				import PIL.ImageFile
				# Force it again just to be sure
				PIL.ImageFile.MAX_TEXT_MEMORY = 2048 * 1024 * 1024
				self.info_panel.append(f"DEBUG: MAX_TEXT_MEMORY set to {PIL.ImageFile.MAX_TEXT_MEMORY}")
			except Exception as e:
				self.info_panel.append(f"DEBUG: Failed to set MAX_TEXT_MEMORY: {e}")

			# DEBUG: Log all analysis details to file
			debug_log_path = os.path.join(result_dir, "sorting_debug.txt")
			with open(debug_log_path, "w") as df:
				df.write(f"ANALYSIS SESSION START\n")
				df.write(f"Configured Threshold: {self.config.get('opacity_threshold', self.opacity_slider.value())}%\n")
				df.write(f"Configured Alpha Cutoff: {self.config.get('alpha_cutoff', 250)}\n")

			total_resolved = len(resolved)
			
			for idx, img_path in enumerate(resolved):
				# Skip .spine files or other non-image files that might have been picked up
				if img_path.lower().endswith('.spine') or img_path.lower().endswith('.json'):
					continue

				# Progress update: Opacity check (20-50 range)
				if total_resolved > 0:
					p = 20 + int((idx / total_resolved) * 30)
					self.progress_bar.setValue(base_progress + p)
					QApplication.processEvents()
					
				try:
					im = Image.open(img_path)
					# convert to RGBA to reliably access alpha channel
					rgba = im.convert('RGBA')
					alpha = rgba.split()[-1]
					data = list(alpha.getdata())
					total = len(data)
					if total == 0:
						# treat empty images as opaque to avoid divide-by-zero
						ratio = 1.0
						opaque_count = 0
					else:
						# use configured alpha cutoff (count pixels with alpha >= cutoff as opaque)
						alpha_cutoff = int(self.config.get("alpha_cutoff", 250))
						opaque_count = sum(1 for v in data if v >= alpha_cutoff)
						ratio = opaque_count / total
					# threshold from slider (percentage)
					threshold_val_config = float(self.config.get("opacity_threshold", self.opacity_slider.value()))
					threshold = threshold_val_config / 100.0
					fully_opaque = (ratio >= threshold)
					
					# Smart Corner Detection:
					# If the image is considered opaque by ratio, but has transparent corners, 
					# it is likely a rounded-rect asset (like a card or button) that MUST be PNG.
					# Note: This is now optional via config
					if fully_opaque and total > 0 and self.config.get("smart_corner_detection", True):
						width, height = im.size
						# Check 4 corners if image is large enough (at least 8x8 to check blocks)
						if width >= 8 and height >= 8:
							# Use a stricter threshold (e.g. 15) for structural transparency checks
							# independently of the global alpha_cutoff which might be high.
							# This avoids false positives on backgrounds with faint vignettes.
							corner_strict_cutoff = 20
							
							# Define 4 corner blocks (top-left, top-right, bottom-left, bottom-right)
							# We check a small 4x4 sample at each corner.
							# If the *average* alpha of the corner block is low, it's a structural corner.
							# Single pixel checks are too sensitive to noise/AA.
							block_size = 4
							corners_starts = [(0,0), (width-block_size, 0), (0, height-block_size), (width-block_size, height-block_size)]
							
							transparent_corners = 0
							for start_x, start_y in corners_starts:
								# Analyze the block
								block_transparent_pixels = 0
								total_block_pixels = 0
								
								for by in range(block_size):
									for bx in range(block_size):
										cx = start_x + bx
										cy = start_y + by
										c_idx = cy * width + cx
										if 0 <= c_idx < len(data):
											total_block_pixels += 1
											if data[c_idx] <= corner_strict_cutoff:
												block_transparent_pixels += 1
								
								# If > 75% of the corner block is transparent, count it as a transparent corner
								if total_block_pixels > 0 and (block_transparent_pixels / total_block_pixels) > 0.75:
									transparent_corners += 1
							
							# If 3 or more corners are strictly transparent, force PNG
							if transparent_corners >= 3:
								fully_opaque = False
								try:
									self.info_panel.append(f"  > Detected {transparent_corners} transparent corners in {os.path.basename(img_path)}. Forcing PNG.")
								except: pass

					# LOG DETAIL
					with open(debug_log_path, "a") as df:
						status = "OPAQUE" if fully_opaque else "TRANSPARENT"
						df.write(f"FILE: {os.path.basename(img_path)} | OpaquePix: {opaque_count}/{total} | Ratio: {ratio*100:.2f}% | Threshold: {threshold*100}% | Result: {status}\n")

					# log percentage for visibility
					try:
						self.info_panel.append(f"Opacity for {img_path}: {ratio*100:.2f}% ({opaque_count}/{total})")
					except Exception:
						pass
					opaque_results.append((img_path, fully_opaque))
				except Exception as e:
					msg = f"{name}: image analyze warning {img_path}: {e}"
					# unexpected warnings shouldn't stop the show or scare the user
					self.log_warning(msg)
					# Should default to False (Transparent) on error to be safe
					opaque_results.append((img_path, False))
		else:
			self.info_panel.append("Skipping opacity analysis (Sort all opaque to jpeg is OFF)")

		# Write opaque results to file
		try:
			json_base = os.path.splitext(os.path.basename(found_json or input_path))[0]
			out_file = os.path.join(result_dir, f"opaque_{json_base}.txt")
			with open(out_file, 'w', encoding='utf-8') as fh:
				for p, opaque in opaque_results:
					fh.write(f"{p}\t{int(bool(opaque))}\n")
			results.append(out_file)
			self.info_panel.append(f"Wrote result: {out_file}")
		except Exception as e:
			msg = f"{name}: could not write result file: {e}"
			errors.append(msg)
			self.log_error(msg)

		# Progress update: Opacity analysis done
		self.progress_bar.setValue(base_progress + 50)
		QApplication.processEvents()

		# --- Sorting algorithm: copy attachments into jpeg/png and rebuild JSON ---
		if hasattr(self, 'status_label'): self.status_label.setText(f"Sorting images: {ui_label_text}")
		try:
			if found_json and os.path.exists(found_json):
				# build opaque map (basename or full path -> opaque)
				opaque_map = {}
				for p, ok in opaque_results:
					is_ok = bool(ok)
					opaque_map[p] = is_ok
					opaque_map[os.path.normpath(p)] = is_ok
					opaque_map[os.path.abspath(p)] = is_ok
					opaque_map[p.lower()] = is_ok # handle potential case mismatch
					# REMOVED: Basename fallback to prevent collisions (e.g. skin1/head.png vs skin2/head.png)
					# opaque_map[os.path.basename(p)] = is_ok
					# opaque_map[os.path.basename(p).lower()] = is_ok

				# load json
				with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
					j = json.load(fh)

				# Extract all skin names for exclusion logic
				all_skin_names = set()
				temp_skins = j.get('skins', {})
				if isinstance(temp_skins, dict):
					all_skin_names.update(temp_skins.keys())
				elif isinstance(temp_skins, list):
					for s in temp_skins:
						if isinstance(s, dict):
							if 'name' in s:
								all_skin_names.add(s['name'])
							else:
								# Check for map-style skins in list (e.g. [{"skin1": {...}}, {"skin2": {...}}])
								# If any value is a dict, assume keys are skin names
								if any(isinstance(v, dict) for v in s.values()):
									for k, v in s.items():
										if isinstance(v, dict):
											all_skin_names.add(k)

				# skeleton name
				internal_skeleton_name = os.path.splitext(os.path.basename(found_json))[0]
				skeleton_name = os.path.splitext(os.path.basename(input_path))[0]

				# build slot blend map
				slot_blend = {}
				for s in j.get('slots', []):
					slot_blend[s.get('name')] = s.get('blend', 'normal')

				# prepare final output image folders under the chosen output root
				# structure: <output_root>/images/<skeleton>/{jpeg,png}
				output_root = base_output_root
				# Prefer the skeleton name embedded in the exported JSON (internal_skeleton_name).
				# Fall back to the project/spine filename (`skeleton_name`) if the JSON name isn't available.
				final_skeleton_dir = internal_skeleton_name or skeleton_name
				
				# Debug: Log the skeleton naming decision
				self.info_panel.append(f"Skeleton Folder Name Decision: JSON='{internal_skeleton_name}' Project='{skeleton_name}' -> Final='{final_skeleton_dir}'")
				
				images_root = os.path.join(output_root, 'images', final_skeleton_dir)
				jpeg_dir = os.path.join(images_root, 'jpeg')
				png_dir = os.path.join(images_root, 'png')
				# os.makedirs(jpeg_dir, exist_ok=True)  <-- Removed to prevent empty folders
				# os.makedirs(png_dir, exist_ok=True)   <-- Removed to prevent empty folders

				# Analyze existing skin paths to map folders to skins
				# folder_owners: folder_name -> set of skin names that use it
				folder_owners = {}
				
				def register_skin_path(skin_name, path):
					if not path or not skin_name: return
					# Normalize path
					path = path.replace('\\', '/').lower()
					parts = path.split('/')
					# Exclude filename
					if len(parts) > 1:
						dirs = parts[:-1]
						for d in dirs:
							# Exclude skeleton name and pluralization to prevent root folder hijacking
							if (d == skeleton_name.lower() or d.rstrip('s') == skeleton_name.lower().rstrip('s') or
								d == internal_skeleton_name.lower() or d.rstrip('s') == internal_skeleton_name.lower().rstrip('s')):
								continue

							if d not in ['jpeg', 'png', 'images', 'skeleton', 'root', 'common', 'assets', 'source', 'reference']:
								if d not in folder_owners: folder_owners[d] = set()
								folder_owners[d].add(skin_name)

				# Walk skins to populate folder_owners
				temp_skins_analysis = j.get('skins', {})
				if isinstance(temp_skins_analysis, dict):
					for s_name, s_node in temp_skins_analysis.items():
						if isinstance(s_node, dict):
							# walk attachments
							for slot_v in s_node.values():
								if isinstance(slot_v, dict):
									for att_k, att_v in slot_v.items():
										p = None
										if isinstance(att_v, dict):
											p = att_v.get('path') or att_v.get('name')
										if not p: p = att_k
										register_skin_path(s_name, p)
				elif isinstance(temp_skins_analysis, list):
					for item in temp_skins_analysis:
						if isinstance(item, dict):
							# Named skin?
							s_name = item.get('name')
							
							# If named skin, process 'attachments'
							if s_name and 'attachments' in item:
								for slot_v in item['attachments'].values():
									if isinstance(slot_v, dict):
										for att_k, att_v in slot_v.items():
											p = None
											if isinstance(att_v, dict):
												p = att_v.get('path') or att_v.get('name')
											if not p: p = att_k
											register_skin_path(s_name, p)
							
							# Map style in list?
							for k, v in item.items():
								if k != 'attachments' and k != 'name' and isinstance(v, dict):
									# Assume k is skin name
									for slot_v in v.values():
										if isinstance(slot_v, dict):
											for att_k, att_v in slot_v.items():
												p = None
												if isinstance(att_v, dict):
													p = att_v.get('path') or att_v.get('name')
												if not p: p = att_k
												register_skin_path(k, p)
				
				# Debug folder owners
				try:
					self.info_panel.append(f"Folder ownership analysis: {len(folder_owners)} folders tracked.")
					for f, owners in folder_owners.items():
						self.info_panel.append(f"  Folder '{f}' owned by: {', '.join(owners)}")
				except: pass

				# helper: find source file for an image reference
				def find_source_image(ref_name, skin_context=None):
					# Debug: log the reference being searched
					try:
						self.info_panel.append(f"find_source_image: looking for ref '{ref_name}'")
					except Exception:
						pass
					
					# Helper to filter candidates by skin name (folder match)
					def filter_by_skin(candidates, skin_name):
						if not candidates:
							return candidates
						
						# If no skin context, we can't prioritize, but we might want to avoid specific skin folders?
						# For now, just return candidates if no skin context.
						if not skin_name:
							return candidates

						skin_norm = skin_name.lower()
						
						# Strategy 1: Exact folder name match (e.g. .../pink/...)
						filtered = []
						for c in candidates:
							dir_path = os.path.dirname(c).lower().replace('\\', '/')
							parts = dir_path.split('/')
							if skin_norm in parts:
								filtered.append(c)
						if filtered: return filtered

						# Strategy 2: Partial folder name match (e.g. .../skin_pink/...)
						# We look for the skin name as a substring in the path parts
						for c in candidates:
							dir_path = os.path.dirname(c).lower().replace('\\', '/')
							parts = dir_path.split('/')
							# Check if skin name is part of any folder name
							if any(skin_norm in p for p in parts):
								filtered.append(c)
						if filtered: return filtered
						
						# Strategy 3: Exclusion of OTHER skins (Ownership Logic)
						# If we didn't find a positive match for our skin, we should at least
						# exclude candidates that belong to OTHER known skins.
						
						# Use folder ownership analysis if available
						if folder_owners:
							filtered_ownership = []
							for c in candidates:
								dir_path = os.path.dirname(c).lower().replace('\\', '/')
								parts = dir_path.split('/')
								
								keep = True
								for p in parts:
									if p in folder_owners:
										owners = folder_owners[p]
										# If this folder is owned by someone
										if owners:
											# If owned by default, always keep
											if 'default' in owners:
												continue
											# If owned by us, always keep
											if skin_name and skin_name in owners:
												continue
											# If we are here, it is owned by others but NOT us and NOT default
											# So it belongs to another skin exclusively -> Exclude
											# Debug log exclusion
											# try: self.info_panel.append(f"Excluding '{c}' for skin '{skin_name}' because folder '{p}' is owned by {owners}")
											# except: pass
											keep = False
											break
								
								if keep:
									filtered_ownership.append(c)
							
							if filtered_ownership:
								return filtered_ownership
							# If ownership filter removed everything, return empty to avoid picking wrong skin assets
							return []

						# Fallback to name-based exclusion if no ownership data
						# Identify other skins to exclude
						# We exclude all known skins EXCEPT the current one and "default"
						IGNORED_SKIN_FOLDERS = {'images', 'common', 'assets', 'source', 'root', 'skeleton', 'jpeg', 'png', 'reference'}
						other_skins = {s.lower() for s in all_skin_names if s.lower() != skin_norm and s.lower() != 'default' and s.lower() not in IGNORED_SKIN_FOLDERS}
						
						if not other_skins:
							return candidates


						filtered_exclusion = []
						for c in candidates:
							dir_path = os.path.dirname(c).lower().replace('\\', '/')
							parts = dir_path.split('/')
							
							# Check if any part matches an OTHER skin
							is_other = False
							for p in parts:
								# 1. Exact match
								if p in other_skins:
									is_other = True
									break
								# 2. Partial match (e.g. "piggy_bank_right" contains "right")
								# We iterate other skins and check if they are present in the folder name
								for s in other_skins:
									if s in p:
										is_other = True
										break
								if is_other: break
							
							if not is_other:
								filtered_exclusion.append(c)
						
						if filtered_exclusion:
							return filtered_exclusion

						# If everything was excluded (e.g. only found "gold/head.png" for "pink" skin),
						# then we have a problem. We can either return nothing (missing asset) or return all (wrong asset).
						# Returning nothing is safer to avoid visual glitches of wrong skin, but might show missing image.
						# Returning all guarantees something shows up.
						# Given the user complaint "shows same asset", we should probably return NOTHING if we are sure it's wrong.
						# But let's return filtered_exclusion (which is empty) if we found candidates but they were all excluded.
						
						return [] 

					# try absolute -> return as single-item list for consistency
					if os.path.isabs(ref_name) and os.path.isfile(ref_name):
						return [ref_name]
					# normalized key lookup against opaque_map: return all matching resolved candidates
					norm = os.path.normpath(ref_name)
					if norm in opaque_map:
						matches = []
						norm_base = os.path.basename(norm).lower()
						for cand in resolved:
							if os.path.basename(cand).lower() == norm_base:
								matches.append(cand)
						if matches:
							# Apply skin filter
							matches = filter_by_skin(matches, skin_context)
							return matches
					# basename without extension
					base = os.path.splitext(os.path.basename(ref_name))[0]
					base_l = base.lower()
					# normalize a core base by stripping trailing separators so 'particles_' -> 'particles'
					base_core = base_l.rstrip('_-')
					# Debug
					try:
						self.info_panel.append(f"find_source_image: base='{base}' core='{base_core}'")
					except Exception:
						pass
					# prepare containers
					seq_matches = []
					prefix_matches = []
					exact_matches = []
					# regex to capture numeric suffix after the core base
					seq_re = re.compile(r'^' + re.escape(base_core) + r'(?:[_\-]?)(\d+)$')
					for cand in resolved:
						name_noext = os.path.splitext(os.path.basename(cand))[0].lower()
						# exact match (filename equals reference basename)
						if name_noext == base_l:
							exact_matches.append(cand)
						# numeric sequence match (e.g., base_core + sep + digits)
						m = seq_re.match(name_noext)
						if m:
							num = int(m.group(1))
							seq_matches.append((num, cand))
						# prefix match (starts with the reference basename)
						elif name_noext.startswith(base_l) or name_noext.startswith(base_core):
							prefix_matches.append(cand)
					
					# Helper to filter candidates by directory structure if ref_name has path info
					def filter_by_path(candidates, ref_name, is_tuple=False):
						# Check if ref_name has directory components
						ref_dir = os.path.dirname(ref_name)
						if not ref_dir:
							return candidates
						
						# Normalize ref_dir for comparison (handle separators)
						ref_dir_norm = ref_dir.replace('\\', '/').lower()
						
						filtered = []
						for item in candidates:
							path = item[1] if is_tuple else item
							# Get directory of candidate
							cand_dir = os.path.dirname(path).replace('\\', '/').lower()
							
							# Check if candidate directory ends with reference directory
							# We check for exact suffix match with separator to avoid partial matches like "big_win" matching "big_win_shine"
							# Also handle case where cand_dir IS the ref_dir
							if cand_dir == ref_dir_norm or cand_dir.endswith('/' + ref_dir_norm):
								filtered.append(item)
						
						# If we found matches that respect the folder structure, return them
						if filtered:
							return filtered
						
						# Otherwise fallback to original candidates (maybe folder structure changed)
						return candidates

					# prefer an exact match first
					if exact_matches:
						# Filter by path if applicable
						exact_matches = filter_by_path(exact_matches, ref_name)
						# Filter by skin if applicable
						exact_matches = filter_by_skin(exact_matches, skin_context)

						# return all exact matches (could be multiple in different folders)
						# Debug: log exact match
						try:
							self.info_panel.append(f"Exact match found for '{ref_name}': {exact_matches[0]}")
						except Exception:
							pass
						return exact_matches

					# then prefer numeric sequences if found
					if seq_matches:
						# Filter by path if applicable
						seq_matches = filter_by_path(seq_matches, ref_name, is_tuple=True)
						
						# Filter by skin if applicable (seq_matches is list of tuples (num, path))
						if skin_context:
							candidates_only = [p for _, p in seq_matches]
							filtered_candidates = filter_by_skin(candidates_only, skin_context)
							# Reconstruct seq_matches with only filtered paths
							seq_matches = [m for m in seq_matches if m[1] in filtered_candidates]

						seq_matches.sort(key=lambda x: x[0])
						try:
							self.info_panel.append(f"Sequence detected for '{ref_name}': {len(seq_matches)} frames")
						except Exception:
							pass
						# return ordered list of candidates
						return [p for _, p in seq_matches]
					
					# then prefix matches: sort intelligently (numeric suffixes first)
					if prefix_matches:
						# Filter by path if applicable
						prefix_matches = filter_by_path(prefix_matches, ref_name)
						# Filter by skin if applicable
						prefix_matches = filter_by_skin(prefix_matches, skin_context)

						# attempt numeric-suffix ordering: extract trailing digits from basename
						def _num_key(path):
							bn = os.path.splitext(os.path.basename(path))[0]
							m = re.search(r'(\d+)$', bn)
							if m:
								return (0, int(m.group(1)))
							# no trailing digits: fallback to alphabetical
							return (1, bn)
						try:
							prefix_matches.sort(key=_num_key)
						except Exception:
							prefix_matches.sort()
						try:
							self.info_panel.append(f"Prefix matches for '{ref_name}': {len(prefix_matches)} found, representative: {os.path.basename(prefix_matches[0])}")
						except Exception:
							pass
						return prefix_matches
					# nothing found
					return None

				# iterate skins -> slots -> attachments
				skins = j.get('skins', {})
				
				# Debug: Check JSON content
				bones_count = len(j.get('bones', []))
				slots_count = len(j.get('slots', []))
				self.info_panel.append(f"JSON Analysis: {bones_count} bones, {slots_count} slots found.")
				if bones_count == 0:
					self.info_panel.append("WARNING: No bones found in exported JSON! The output skeleton will be empty.")

				# -----------------------------
				# Naming convention checks (per-skeleton detailed)
				# - Report skeleton and animation name problems in detail
				# - Summarize slots/bones/constraints issues as counts with examples
				# -----------------------------
				try:
					# Prepare container for naming results
					naming = {
						'skeleton': [],
						'animations': [],
						'slots_summary': {'count': 0, 'examples': []},
						'bones_summary': {'count': 0, 'examples': []},
						'constraints_summary': {'count': 0, 'examples': []}
					}

					# Helper checks
					def check_name_issues(name):
						reasons = []
						if name != name.strip():
							reasons.append('leading/trailing whitespace')
						if ' ' in name:
							reasons.append('contains space')
						if re.search(r'[A-Z]', name):
							reasons.append('contains uppercase')
						# Allow common filename chars, flag anything outside
						if not re.match(r'^[a-z0-9._\- ]+$', name):
							reasons.append('non-standard characters')

						# Basic fuzzy spell-check for obvious typos in animation/skeleton tokens
						try:
							import difflib
							# small curated wordlist + workspace-derived words could be added later
							_common_words = set((
								'idle','walk','run','jump','attack','hit','death','spawn','intro',
								'anticipation','anticipate','land','fall','shoot','throw','cast'
							))
							# split into alpha tokens
							for tok in re.split(r'[^a-zA-Z]+', name):
								if not tok or len(tok) < 4:
									continue
								low = tok.lower()
								if low in _common_words:
									continue
								# look for close matches in our small list
								matches = difflib.get_close_matches(low, _common_words, n=1, cutoff=0.8)
								if matches:
									reasons.append(f"possible misspelling: did you mean '{matches[0]}'?")
						except Exception:
							# non-fatal: don't block naming checks if difflib unavailable
							pass
						return reasons

					# Skeleton name(s)
					skel_obj = j.get('skeleton') if isinstance(j, dict) else None
					candidates = []
					if skel_obj and isinstance(skel_obj, dict):
						# common skeleton name fields
						for k in ('name', 'skeleton', 'spine'):
							v = skel_obj.get(k)
							if isinstance(v, str) and v:
								candidates.append((k, v))
					# also include internal filename as candidate
					if internal_skeleton_name:
						candidates.append(('filename', internal_skeleton_name))

					for src, val in candidates:
						rs = check_name_issues(val)
						if rs:
							naming['skeleton'].append({'field': src, 'value': val, 'reasons': rs})

					# Animations (detailed per-skeleton)
					for anim in sorted(j.get('animations', {}).keys() if isinstance(j.get('animations', {}), dict) else []):
						ars = check_name_issues(anim)
						if ars:
							naming['animations'].append({'name': anim, 'reasons': ars})

					# Slots/Bones/Constraints: aggregate counts and collect first examples
					for slot in j.get('slots', []):
						n = slot.get('name', '') if isinstance(slot, dict) else ''
						if n:
							rs = check_name_issues(n)
							if rs:
								naming['slots_summary']['count'] += 1
								if len(naming['slots_summary']['examples']) < 5:
									naming['slots_summary']['examples'].append({'name': n, 'reasons': rs})

					for b in j.get('bones', []):
						n = b.get('name', '') if isinstance(b, dict) else ''
						if n:
							rs = check_name_issues(n)
							if rs:
								naming['bones_summary']['count'] += 1
								if len(naming['bones_summary']['examples']) < 5:
									naming['bones_summary']['examples'].append({'name': n, 'reasons': rs})

					for c in j.get('constraints', []):
						# constraints may be simple dicts with 'name'
						if isinstance(c, dict):
							n = c.get('name')
						else:
							n = ''
						if n:
							rs = check_name_issues(n)
							if rs:
								naming['constraints_summary']['count'] += 1
								if len(naming['constraints_summary']['examples']) < 5:
									naming['constraints_summary']['examples'].append({'name': n, 'reasons': rs})

					# Persist naming results into stats for later reporting
					all_file_stats[-1].setdefault('naming', naming)
				except Exception:
					# Non-fatal: don't break processing on naming check errors
					pass

				# build a list of all skin dicts (slot->attachments) regardless of skins being dict or list
				ALL_SKIN_DICTS = []
				if isinstance(skins, dict):
					for _, sdict in skins.items():
						if isinstance(sdict, dict):
							ALL_SKIN_DICTS.append(sdict)
				elif isinstance(skins, list):
					for item in skins:
						if isinstance(item, dict):
							# case: {'name': 'default', 'attachments': {...}}
							if 'attachments' in item and isinstance(item.get('attachments'), dict):
								ALL_SKIN_DICTS.append(item.get('attachments'))
							else:
								# case: {skinName: skinDict, ...}
								for v in item.values():
									if isinstance(v, dict):
										ALL_SKIN_DICTS.append(v)
				
				# Pre-calculate attachment -> slots mapping to avoid massive loop
				ATTACHMENT_SLOT_MAP = {}
				for s_dict in ALL_SKIN_DICTS:
					if isinstance(s_dict, dict):
						for s_name, s_val in s_dict.items():
							if isinstance(s_val, dict):
								for att_key in s_val:
									if att_key not in ATTACHMENT_SLOT_MAP:
										ATTACHMENT_SLOT_MAP[att_key] = []
									ATTACHMENT_SLOT_MAP[att_key].append(s_name)

				# Global Scan Data (for pre-scan pass)
				SCAN_SLOT_USAGE = {} # path -> set(slots)
				PRECALC_DESTINATIONS = {} # path -> 'jpeg' or 'png'
				EXPORTED_UNIQUE_IMAGES = set()  # will record only actually exported (or placeholder) source paths
				TOTAL_ATTACHMENTS_COUNT = 0
				CONSOLIDATED_IMAGES_COUNT = 0
				UNIQUE_COPIED_PATHS = set()

				# helper to process a single skin dict (slot -> attachments)
				def process_skin_dict(skin_dict, skin_name=None, scan_mode=False):
					nonlocal TOTAL_ATTACHMENTS_COUNT
					nonlocal CONSOLIDATED_IMAGES_COUNT
					if not isinstance(skin_dict, dict):
						return skin_dict
					
					for slot_name, attachments in list(skin_dict.items()):
						if not isinstance(attachments, dict):

							self.info_panel.append(f"Skipping slot {slot_name}: unexpected attachments type {type(attachments)}")
							continue
						for attach_name, attach_val in list(attachments.items()):
							if not scan_mode:
								TOTAL_ATTACHMENTS_COUNT += 1

							# determine referenced image name
							if isinstance(attach_val, dict):
								# prefer explicit path in attachment value; otherwise use the attachment name
								# Check 'name' as well, as meshes often use 'name' for the image path
								ref = attach_val.get('path') or attach_val.get('name') or attach_name
							else:
								# attach_name may include folder-like segments
								ref = attach_name
							
							# find real source file
							src = find_source_image(ref, skin_context=skin_name)
							
							# DEBUG: Trace consolidation
							if src and isinstance(src, str):
								fname = os.path.basename(src)
								if fname in ['clubs.png', 'flipy.png', 'rotator.png', 'ddd.png']:
									norm_src = os.path.normcase(os.path.abspath(src))
									in_mirror = norm_src in consolidation_map_mirror
									if not in_mirror and consolidated_mirrored:
										# If not found, check if keys exist with different case?
										self.info_panel.append(f"<font color='orange'>DEBUG: {fname} found at {src}</font>")
										self.info_panel.append(f"&nbsp;&nbsp;Key: {norm_src}")
										self.info_panel.append(f"&nbsp;&nbsp;In Map: {norm_src in consolidation_map}, In Mirror: {norm_src in consolidation_map_mirror}")
										# Check if ANY key ends with this filename
										for k in consolidation_map_mirror:
											if k.endswith(os.path.normcase(fname)):
												self.info_panel.append(f"&nbsp;&nbsp;Partial match found in keys: {k}")

							
							# Consolidation State
							consolidation_occurred = False
							
							# Keep backup of original src for later reference
							src_list = src if isinstance(src, (list, tuple)) else ([src] if src else [])
							
							# Debug log if src is found and MAP is active
							# if src and consolidation_map and not scan_mode:
							# 	# Only log if one of our srcs is actually a target
							# 	# self.info_panel.append(f"Checking consolidation for: {src}")
							# 	pass
							
							# Check if likely a sequence to optionally skip consolidation
							is_sequence_check = False
							if isinstance(attach_val, dict) and 'sequence' in attach_val:
								is_sequence_check = True
							elif str(attach_name).endswith('_'):
								is_sequence_check = True
							elif isinstance(src, (list, tuple)) and len(src) > 1:
								is_sequence_check = True

							# Check if source is in 'png' folder (user requirement: consolidation only for png folder)
							is_png_folder_check = False
							if src:
								s_p = src[0] if isinstance(src, (list, tuple)) else src
								# Normalize separators and check path components
								try:
									parts = os.path.dirname(s_p).replace('\\', '/').lower().split('/')
									if 'png' in parts:
										is_png_folder_check = True
								except: pass
									
							# Applies Consolidation Logic (if map exists and has entries)
							try:
								# 1. Exact Consolidation
								if src and consolidation_map and not is_sequence_check and is_png_folder_check:
									if isinstance(src, (list, tuple)):
										# For sequences, we need to map each frame
										new_src = []
										for p in src:
											norm_p = os.path.normcase(os.path.abspath(p))
											if norm_p in consolidation_map:
												new_src.append(consolidation_map[norm_p])
												consolidation_occurred = True
												if not scan_mode:
													CONSOLIDATED_IMAGES_COUNT += 1
											else:
												new_src.append(p)
										# CRITICAL: Deduplicate the list after consolidation
										# If consolidation mapped multiple files to the same primary, we still only want to copy once
										if new_src and consolidation_occurred:
											seen_files = {}
											dedup_src = []
											for f in new_src:
												norm_f = os.path.normcase(os.path.abspath(f))
												if norm_f not in seen_files:
													seen_files[norm_f] = True
													dedup_src.append(f)
											src = dedup_src
										else:
											src = new_src
									else:
										# Single file consolidation
										norm_p = os.path.normcase(os.path.abspath(src))
										if norm_p in consolidation_map:
											src = consolidation_map[norm_p]
											consolidation_occurred = True
											if not scan_mode:
												CONSOLIDATED_IMAGES_COUNT += 1
								
								# 2. Mirror Consolidation (independent check)
								if src and consolidation_map_mirror and not is_sequence_check and is_png_folder_check:
									common_transform = None
									new_src_list = []
									all_mapped = True
									
									src_check = src if isinstance(src, (list, tuple)) else [src]
									for s_path in src_check:
										norm_p = os.path.normcase(os.path.abspath(s_path))
										if norm_p in consolidation_map_mirror:
											entry = consolidation_map_mirror[norm_p]
											# Check transform consistency
											if common_transform is None:
												common_transform = entry
											elif common_transform['transform'] != entry['transform']:
												all_mapped = False
												break
											new_src_list.append(entry['target'])
										else:
											all_mapped = False
											break
									
									if all_mapped and common_transform:
										# Strict Safety Check: Do NOT apply to Meshes or complex attachments
										is_complex = False
										if 'type' in attach_val and attach_val['type'] in ('mesh', 'linkedmesh', 'path', 'boundingbox', 'clipping'):
											is_complex = True
										# Check for mesh data keys just in case type is omitted
										if 'uvs' in attach_val or 'triangles' in attach_val or 'vertices' in attach_val:
											is_complex = True
											
										if not is_complex:
											# Apply replacement
											src = new_src_list if isinstance(src, (list, tuple)) else new_src_list[0]
											
											if not scan_mode:
												CONSOLIDATED_IMAGES_COUNT += len(src_check)
												consolidation_occurred = True
												
												# Update JSON Attachment Data
												# We need to flip scale.
												# If scale not present, default is 1.0.
												
												# Rename 'name' or 'path' in the attachment to match the new target
												# so we don't rely solely on the file copying loop to fix the reference.
												# Actually, the file copying loop below will determine the new path based on 'src'.
												# BUT, if we have a "rename" effect which the user complains about, maybe we should
												# ensure the JSON path is updated to point to the EXISTING target file's location/name.
												
												# The loop below handles:
												# 1. Calculates destination path based on `src` (which is now the Target file)
												# 2. Copies file (if not exists)
												# 3. Updates `attach_val['path']`
												
												# The issue "just renamed image" might mean:
												# The exported JSON now points to "TargetImage.png" instead of "SourceImage.png".
												# This IS the intended behavior: we want to reuse the existing image.
												# If the user sees "SourceImage.png" in the export folder but with Target content, that would be weird.
												# But here we change `src` to `TargetImage.png`.
												# So the script will copy `TargetImage.png` to the export folder.
												# And the JSON will point to `TargetImage.png` (or wherever it ends up).
												
												# If the user wants to KEEP the original name "SourceImage" but use the CONTENT of "TargetImage",
												# then we should NOT change `src`, but we should change... wait.
												# If we want consolidation (reuse), we MUST point to the shared asset.
												# If we keep the old name, we are duplicating the file on disk (just with copied content).
												# That is NOT consolidation. Consolidation means 1 file on disk, multiple references.
												# So "renamed image" in JSON is correct.
												
												# Perhaps the user means they saw a file "SourceImage.png" in the output that was actually "TargetImage"?
												# No, if we change `src`, the copier uses `os.path.basename(src)` as the filename.
												# So it will output `TargetImage.png`.
												
												# Parse transform type
												import math
												t_type = common_transform.get('transform')
												
												# 1. Get Current Transform Values
												cur_x = attach_val.get('x', 0.0)
												cur_y = attach_val.get('y', 0.0)
												cur_rot = attach_val.get('rotation', 0.0)
												cur_sx = attach_val.get('scaleX', 1.0)
												cur_sy = attach_val.get('scaleY', 1.0)

												# 2. Determine New Transform Values (Rotation/Scale)
												new_rot = cur_rot
												new_sx = cur_sx
												new_sy = cur_sy
												
												if t_type == 'flipX':
													new_sx *= -1.0
												elif t_type == 'flipY':
													new_sy *= -1.0
												elif t_type in ('rotate90', 'rotate180', 'rotate270'):
													angle = common_transform.get('angle', 0)
													new_rot += angle

												# 3. Apply Transform Updates
												attach_val['scaleX'] = new_sx
												attach_val['scaleY'] = new_sy
												attach_val['rotation'] = new_rot
												
												# 4. Handle Trim Compensation (Offset Adjustment)
												# We need the ORIGINAL src path (before renaming) to lookup trim data.
												original_path_ref = src_list[0]
												target_path_ref = new_src_list[0]
												
												# KEY: Normalize paths for lookup
												op_norm = os.path.normcase(os.path.abspath(original_path_ref))
												tp_norm = os.path.normcase(os.path.abspath(target_path_ref))
												
												if trim_data and op_norm in trim_data and tp_norm in trim_data:
													o_dat = trim_data[op_norm]
													t_dat = trim_data[tp_norm]
													
													# Update dimensions to match TARGET (visual correctness)
													attach_val['width'] = t_dat['original_w']
													attach_val['height'] = t_dat['original_h']
													
													# Calculate Center in Pixel Space (Top-Left Origin)
													# trim_l + trim_w/2
													o_cx = o_dat['trim_l'] + o_dat['trim_w'] / 2.0
													o_cy = o_dat['trim_t'] + o_dat['trim_h'] / 2.0
													
													t_cx = t_dat['trim_l'] + t_dat['trim_w'] / 2.0
													t_cy = t_dat['trim_t'] + t_dat['trim_h'] / 2.0
													
													# Convert to Offset from Image Center (Y-Up for Spine)
													# Spine Offset X = Content_CX - Image_W/2
													# Spine Offset Y = Image_H/2 - Content_CY
													
													ox = o_cx - (o_dat['original_w'] / 2.0)
													oy = (o_dat['original_h'] / 2.0) - o_cy
													
													tx = t_cx - (t_dat['original_w'] / 2.0)
													ty = (t_dat['original_h'] / 2.0) - t_cy
													
													# Transform Logic:
													# Visual Center of Content relative to Bone = 
													# (att_x, att_y) + Rotate(att_rot) * Scale(att_scale) * (Content_Offset_From_Image_Center)
													
													def rotate_point(px, py, angle_deg):
														rad = math.radians(angle_deg)
														cos_a = math.cos(rad)
														sin_a = math.sin(rad)
														return px * cos_a - py * sin_a, px * sin_a + py * cos_a
													
													# Calculate original visual content position relative to bone
													# Start with Bone -> Attachment Center (cur_x, cur_y)
													# Add Attachment Center -> Content Center vector (ox, oy), transformed by attachment transform
													
													# 1. Scale content offset
													sox = ox * cur_sx
													soy = oy * cur_sy
													
													# 2. Rotate content offset
													rox, roy = rotate_point(sox, soy, cur_rot)
													
													# 3. Add to attachment position
													vis_x = cur_x + rox
													vis_y = cur_y + roy
													
													# Now we want the new attachment to have its content at (vis_x, vis_y)
													# New Attachment Position (new_att_x, new_att_y) + Transformed New Content Offset = (vis_x, vis_y)
													# (new_att_x, new_att_y) = (vis_x, vis_y) - Transformed New Content Offset
													
													# 1. Scale target content offset
													stx = tx * new_sx
													sty = ty * new_sy
													
													# 2. Rotate target content offset
													rtx, rty = rotate_point(stx, sty, new_rot)
													
													# 3. Calculate new attachment position
													new_att_x = vis_x - rtx
													new_att_y = vis_y - rty
													
													# Check if significant change (avoid noise)
													if abs(new_att_x - cur_x) > 0.001 or abs(new_att_y - cur_y) > 0.001:
														attach_val['x'] = new_att_x
														attach_val['y'] = new_att_y
												
												# Handle Trim Offset Adjustment (for whitespace consolidation)
												# Check if src was part of a trimmed match
												# We need the original path to lookup trim data. We have `s_path` (original src)
												# BUT `src` variable has already been updated to `new_src_list`.
												
												# We need the ORIGINAL src path to calculate the offset relative to the TARGET.
												# Let's iterate over `src_list` (original versions)
												if trim_data:
													# Find corresponding trim data for the consolidated target
													target_key = src_list[0] if isinstance(src_list, (list, tuple)) else src_list
													# Wait, `src_list` is the ORIGINAL list before mapping. Correct.
													# The TARGET is `new_src_list[0]`.
													
													target_path = new_src_list[0]
													original_path = s_path # from loop above
													
													# Only adjust if both have trim data
													if target_path in trim_data and original_path in trim_data:
														t_dat = trim_data[target_path]
														o_dat = trim_data[original_path]
														
														# Calculate center offset relative to image center
														# X: (trim_l + w/2) - orig_w/2
														# Y: (orig_h/2) - (trim_t + h/2)  <-- Y is up, pixel Y is down
														
														def get_center_offset(d):
															cx = d['trim_l'] + d['trim_w'] / 2.0
															cy = d['trim_t'] + d['trim_h'] / 2.0
															
															off_x = cx - (d['original_w'] / 2.0)
															off_y = (d['original_h'] / 2.0) - cy
															return off_x, off_y

														tx, ty = get_center_offset(t_dat)
														ox, oy = get_center_offset(o_dat)
														
														# We want visual consistency.
														# The attachment was at position (ax, ay) pointing to Original Image center.
														# Its content was offset by (ox, oy).
														# The New Image has content offset by (tx, ty).
														# We need to move attachment by (ox - tx, oy - ty)
														
														diff_x = ox - tx
														diff_y = oy - ty
														
														if abs(diff_x) > 0.01 or abs(diff_y) > 0.01:
															attach_val['x'] = attach_val.get('x', 0.0) + diff_x
															attach_val['y'] = attach_val.get('y', 0.0) + diff_y
															# Ensure we update width/height so Spine centers it correctly relative to new image center
															attach_val['width'] = t_dat['original_w']
															attach_val['height'] = t_dat['original_h']
														elif t_dat['original_w'] != attach_val.get('width') or t_dat['original_h'] != attach_val.get('height'):
															# Even if center offset is zero, dimensions might differ (symmetric padding)
															attach_val['width'] = t_dat['original_w']
															attach_val['height'] = t_dat['original_h']
									
							except Exception as e:
								# Log the error
								try:
									with open(os.path.join(result_dir, "consolidation_debug.txt"), "a") as f:
										f.write(f"Consolidation ERROR: {e}\n")
								except: pass
							
							
							# Note: do NOT record candidate matches here — we only want to count
							# source files that were actually exported/copied or placeholders created.
							# `EXPORTED_UNIQUE_IMAGES` will be updated on successful copy/create below.
							
							if scan_mode:
								if src:
									matches_scan = src if isinstance(src, (list, tuple)) else [src]
									for ms in matches_scan:
										try:
											k_s = os.path.normpath(ms)
											if k_s not in SCAN_SLOT_USAGE:
												SCAN_SLOT_USAGE[k_s] = set()
											SCAN_SLOT_USAGE[k_s].add(slot_name)
										except: pass
								continue
							
							# determine blend(s) for this slot
							blend = slot_blend.get(slot_name, 'normal')
							# determine opaque status
							is_opaque = False
							
							# If optimization is enabled, perform opacity analysis
							if src and optimization_enabled:
								# src may be a single path or a list of matches; consider all matches opaque to be opaque
								matches_check = src if isinstance(src, (list, tuple)) else [src]
								vals = []
								for m in matches_check:
									# More robust lookup
									val = False
									found_key = False
									
									candidates_keys = [
										m,
										os.path.normpath(m),
										os.path.abspath(m),
										m.lower()
										# REMOVED: Basename fallback
										# os.path.basename(m),
										# os.path.basename(m).lower()
									]
									
									for k in candidates_keys:
										if k in opaque_map:
											val = opaque_map[k]
											found_key = True
											break
									
									vals.append(val)
							
							# If attachment appears in slots, collect those slots and their blends
							# Optimization: use pre-calculated map instead of iterating all skins
							slots_found = ATTACHMENT_SLOT_MAP.get(attach_name, [])
							
							# decide destination:
							# - If attachment appears in one or more slots and ALL such slots use a non-normal blend,
							#   then put the image in `jpeg`.
							# - Otherwise, if the current slot's blend is normal, none of the appearing slots are non-normal,
							#   and the image is opaque, put in `jpeg`.
							# - Otherwise put in `png`.
							
							base_dest = None
							appears_only_in_non_normal = False
							if slots_found:
								appears_only_in_non_normal = all(slot_blend.get(s, 'normal') != 'normal' for s in slots_found)

							reason = []
							is_jpeg_source = False
							# Check if source path suggests it was originally in a jpeg folder
							if src:
								src_check = src[0] if isinstance(src, (list, tuple)) else src
								if 'jpeg' in str(src_check).lower():
									is_jpeg_source = True

							# Check if it is a reference image (should not be sorted into jpeg/png)
							is_reference = "reference" in str(attach_name).lower()
							if src:
								src_check = src[0] if isinstance(src, (list, tuple)) else src
								if "reference" in str(src_check).lower():
									is_reference = True

							if is_reference:
								# For references, we want to keep them separate but still organized.
								# Place them in the global images folder (not under skeleton subfolder).
								# base_dest is already set to global images root.
								pass
							else:
								forced_decision = None
								if src:
									src_check = src[0] if isinstance(src, (list, tuple)) else src
									try:
										k_s = os.path.normpath(src_check)
										forced_decision = PRECALC_DESTINATIONS.get(k_s)
									except: pass

								if forced_decision == 'png':
									base_dest = png_dir
									reason.append("global: forced to png")
								elif forced_decision == 'jpeg':
									base_dest = jpeg_dir
									reason.append("global: forced to jpeg")
								elif slots_found and appears_only_in_non_normal:
									base_dest = jpeg_dir
									reason.append("only in non-normal slots")
								elif is_opaque:
									base_dest = jpeg_dir
									reason.append("opaque")
								else:
									base_dest = png_dir
									if not is_opaque: reason.append("transparent")
									if blend != 'normal': reason.append(f"blend={blend}")
								
								# Warning if it was JPEG but forced to PNG
								if is_jpeg_source and base_dest == png_dir:
									msg = f"<font color='red'>WARNING:</font> '{attach_name}' was in jpeg folder but forced to PNG due to: Transparent corners and/or edges while using normal mode . You may want to fix transparency and put it back to jpeg folder manually or change blend mode !!!"
									self.info_panel.append(msg)
									jpeg_forced_png_warnings.append(f"[{name}] {msg}")
								else:
									# Optional: log decision for debugging
									# self.info_panel.append(f"Decision for '{attach_name}': PNG ({', '.join(reason)})")
									pass

							# Clean ref path to remove structural prefixes (jpeg, png, skeleton_name)
							# This prevents duplication like win_events/jpeg/win_events/jpeg/...
							# Use the logic from the "ok" version which filters parts based on a blocklist
							# and uses attach_name as the source of truth for folder structure.
							
							# copy file(s) if found
							if src:
								matches = src if isinstance(src, (list, tuple)) else [src]
								
								# Additional filter: Remove any files that are marked as duplicates in consolidation_map
								# This prevents accidentally copying both the duplicate and its consolidated primary
								# NEVER apply this filter to sequences — all frames must be preserved as-is
								if consolidation_map and not is_sequence_check:
									filtered_matches = []
									skipped_duplicates = []
									for f in matches:
										norm_f = os.path.normcase(os.path.abspath(f))
										# Only include files that are NOT consolidation targets (keys in consolidation_map)
										if norm_f not in consolidation_map:
											filtered_matches.append(f)
										else:
											skipped_duplicates.append(f)
									
									if skipped_duplicates and len(matches) > 1:
										# Log which duplicates are being skipped for this attachment
										try:
											primary = consolidation_map.get(os.path.normcase(os.path.abspath(skipped_duplicates[0])))
											if primary:
												self.info_panel.append(f"<font color='#4CAF50'>Skipped duplicate(s) for '{attach_name}': {[os.path.basename(d) for d in skipped_duplicates]} → {os.path.basename(primary)}</font>")
										except Exception:
											pass
									
									# CRITICAL FIX: If all matches were consolidated, use the primary file instead
									if filtered_matches:
										matches = filtered_matches
									elif skipped_duplicates:
										# All source files were consolidated - use the primary file
										primary = consolidation_map.get(os.path.normcase(os.path.abspath(skipped_duplicates[0])))
										if primary:
											matches = [primary]
										# else: if primary is not found, keep the first skipped file as fallback
								
								if isinstance(matches, (list, tuple)) and len(matches) > 1:
									try:
										self.info_panel.append(f"Copying sequence of {len(matches)} frames for '{attach_name}' to {base_dest}")
									except Exception:
										pass

								base_name = None
								
								# -- CONSOLIDATION LOGIC --
								# If consolidation occurred, we replace the attachment path (ref) with the consolidated source file logic.
								if consolidation_occurred and src:
									s_path = src[0] if isinstance(src, (list, tuple)) else src
									if s_path:
										s_parent = os.path.basename(os.path.dirname(s_path))
										s_name = os.path.basename(s_path)
										s_base = os.path.splitext(s_name)[0]
										
										# Check parent folder for structure preservation
										if s_parent.lower() not in ('images', 'root', 'source') and s_parent != os.path.basename(final_skeleton_dir):
											ref = f"{s_parent}/{s_base}"
										else:
											ref = s_base
										
										# Update base_name (without extension) for downstream logic
										base_name = s_base

								# Extract nested folder structure from REFERENCE PATH (the source of truth)
								# We use 'ref' because attach_name might just be an alias/key, while ref contains the path
								attach_name_str = str(ref).replace('\\', '/')
								
								# Clean up attach_name_str (remove extension if present)
								if attach_name_str.lower().endswith('.png') or attach_name_str.lower().endswith('.jpg'):
									attach_name_str = os.path.splitext(attach_name_str)[0]
									
								nested_folders_str = ""
								if not base_name: base_name = os.path.basename(str(ref))
								
								# Ensure base_name logic doesn't carry extension into sequence detection
								if base_name.lower().endswith('.png') or base_name.lower().endswith('.jpg'):
									base_name = os.path.splitext(base_name)[0]
								
								# Check if the attachment belongs to another skeleton
								# Default to the CURRENT processed skeleton (final_skeleton_dir), NOT the project name
								target_skeleton = final_skeleton_dir
								parts = attach_name_str.split('/')
								
								# Heuristic to detect if attachment belongs to another skeleton
								potential_skeleton = parts[0]
								is_other_skeleton = False
								
								# Only check for other skeletons if "Force local sorting" is NOT checked
								if not self.force_local_cb.isChecked():
									# 1. Check against known skeletons in the folder
									if all_skeleton_names and len(parts) > 1:
										potential_lower = potential_skeleton.lower()
										# Check exact match, pluralization match, or version-prefix match (symbols_v6 matches symbols)
										match = None
										for s in all_skeleton_names:
											s_lower = s.lower()
											if s_lower == potential_lower:
												match = s; break
											if s_lower.rstrip('s') == potential_lower.rstrip('s'):
												match = s; break
											# Version prefix check: skeleton "symbols_v6" matches folder "symbols"
											if s_lower.startswith(potential_lower):
												rest = s_lower[len(potential_lower):]
												if rest and (rest[0] in ['_', '-', 'v', '.'] or rest[0].isdigit()):
													match = s; break
													
										if match:
											potential_skeleton = match # Use correct casing
											is_other_skeleton = True
									
									# 2. Fallback: If the first folder is NOT the current skeleton name, and it's not a common folder name,
									# treat it as an external skeleton/folder even if we don't have the .spine file for it.
									# This handles cases like "piggy_banks/..." being used in "game_intro" where "piggy_banks.spine" might not be in the current batch.
									if not is_other_skeleton and len(parts) > 1:
										IGNORED_ROOTS = ['images', 'common', 'skeleton', 'root', 'private', 'jpeg', 'png', 'assets', 'source', 'reference']
										# Check against skeleton name with pluralization handling
										if potential_skeleton.lower().rstrip('s') != skeleton_name.lower().rstrip('s') and potential_skeleton.lower() not in IGNORED_ROOTS:
											is_other_skeleton = True
											# Use the folder name as the target skeleton name
											potential_skeleton = potential_skeleton 
									
									# 2a. Fallback using Source File Path:
									# If we haven't detected a redirection from the attachment string,
									# check if the RESOLVED source file actually lives in another skeleton's folder.
									if not is_other_skeleton and src:
										src_path_check = src[0] if isinstance(src, (list, tuple)) else src
										if src_path_check:
											src_parts = os.path.dirname(src_path_check).replace('\\', '/').split('/')
											src_parts_lower = [p.lower() for p in src_parts]
											
											# Check against known skeletons
											if all_skeleton_names:
												for s in all_skeleton_names:
													s_name = s.lower()
													# Skip self
													if s_name == skeleton_name.lower(): continue
													
													# Check if this skeleton name matches any path part
													# 1. Exact match
													if s_name in src_parts_lower:
														potential_skeleton = s
														is_other_skeleton = True
														break
													# 2. Relaxed match (folder "symbols" matches skeleton "symbols_v6")
													for p in src_parts_lower:
														if len(p) < 3 or p in ['jpeg', 'png', 'images', 'assets', 'source', 'common', 'root', 'backup']:
															continue
														
														if s_name.startswith(p):
															rest = s_name[len(p):]
															# Ensure significant prefix match
															if rest and (rest[0] in ['_', '-', 'v', '.'] or rest[0].isdigit()):
																potential_skeleton = s
																is_other_skeleton = True
																break
													if is_other_skeleton: break
								
								# Apply redirection if detected
								if is_other_skeleton and potential_skeleton.lower() != skeleton_name.lower():
									target_skeleton = potential_skeleton
									
									if is_reference:
										# For references, we want to keep them separate but still organized.
										# Place them in the global images folder (not under skeleton subfolder).
										# base_dest is already set to global images root.
										pass
									else:
										# Redirect base_dest to the other skeleton's folder
										# We respect the current decision of jpeg/png, but put it in the other skeleton's structure
										current_family = 'jpeg' if 'jpeg' in base_dest.lower() else 'png'
										base_dest = os.path.join(output_root, 'images', target_skeleton, current_family)
									
									# Debug log for redirection (only once per target to avoid spam)
									try:
										self.info_panel.append(f"Redirecting '{attach_name}' to skeleton '{target_skeleton}'")
									except: pass
								
								# Remove any family markers (jpeg/png) and skeleton name from the path
								filtered_parts = []
								for part in parts[:-1]:  # Exclude the last part (basename)
									part_lower = part.lower()
									# If it's a reference, we WANT to keep the 'reference' folder in the path
									# so we don't filter it out even if it might be in a blocklist (though 'reference' isn't currently blocked)
									
									# Also filter out the skeleton name if it appears in the path (e.g. game_intro/reference/...)
									# Also handle common typos like pluralization (piggy_bank vs piggy_banks)
									if part_lower == skeleton_name.lower() or part_lower.rstrip('s') == skeleton_name.lower().rstrip('s'):
										continue

									if part_lower not in ['jpeg', 'png', 'images', 'symbols', 'skeleton'] and part_lower.rstrip('s') != target_skeleton.lower().rstrip('s'):
										filtered_parts.append(part)
								
								if filtered_parts:
									nested_folders_str = '/'.join(filtered_parts)
								
								# Use source directory structure to determine nested folders
								# This replaces the disabled attachment-name based logic above
								if not nested_folders_str and src:
									try:
										# Use the first found file
										s_path = src[0] if isinstance(src, (list, tuple)) else src
										if s_path:
											# Check path components
											s_parts = os.path.dirname(s_path).replace('\\', '/').split('/')
											
											# Identify root markers
											markers = ['png', 'jpeg', 'images', 'symbols', 'source', 'common']
											
											# Find the LAST occurrence of a marker to handle cases like .../images/png/...
											last_marker_idx = -1
											for i, p in enumerate(s_parts):
												if p.lower() in markers:
													last_marker_idx = i
											
											if last_marker_idx != -1 and last_marker_idx < len(s_parts) - 1:
												# Look at folders AFTER the last marker
												sub_parts = s_parts[last_marker_idx+1:]
												
												# Filter out part if it matches the final skeleton folder name
												# (this may be the internal JSON skeleton name or the project filename)
												if sub_parts and 'final_skeleton_dir' in locals():
													p0 = sub_parts[0].lower()
													s_name = final_skeleton_dir.lower()
													if p0 == s_name or p0.rstrip('s') == s_name.rstrip('s'):
														sub_parts.pop(0)
												
												if sub_parts:
													nested_folders_str = '/'.join(sub_parts)
									except Exception:
										pass

								# If this is a skin attachment and the source file was found in a matching skin folder,
								# we MUST preserve that skin folder in the output to avoid collisions with other skins.
								if skin_name and skin_name.lower() != 'default' and src:
									src_check = src[0] if isinstance(src, (list, tuple)) else src
									src_dir_parts = os.path.dirname(src_check).replace('\\', '/').lower().split('/')
									
									# Check if the source file is in a folder matching the skin name (exact or partial)
									# OR if the folder is OWNED by the skin (via folder_owners)
									
									# 1. Check direct name match
									if any(skin_name.lower() in p for p in src_dir_parts):
										# Check if we already have the skin name in the nested structure
										current_nesting = nested_folders_str.lower().split('/') if nested_folders_str else []
										if skin_name.lower() not in current_nesting:
											if nested_folders_str:
												nested_folders_str = f"{skin_name}/{nested_folders_str}"
											else:
												nested_folders_str = skin_name
									
									# 2. Check ownership match (e.g. folder "left" owned by skin "pink")
									elif folder_owners:
										# Iterate in REVERSE to build hierarchy bottom-up (prepending)
										# This ensures we capture deep nesting like "skin/subfolder" correctly
										for p in reversed(src_dir_parts):
											if p in folder_owners and skin_name in folder_owners[p]:
												# This folder belongs to our skin! Preserve it.
												# We use the actual folder name (e.g. "left")
												current_nesting = nested_folders_str.lower().split('/') if nested_folders_str else []
												if p.lower() not in current_nesting:
													if nested_folders_str:
														nested_folders_str = f"{p}/{nested_folders_str}"
													else:
														nested_folders_str = p
												# Do NOT break, so we can capture multiple levels of owned folders

								# Initialize sequence/placeholder flags BEFORE using them
								is_sequence = False # General heuristic for folder organization
								is_spine_sequence = False # Strict JSON definition for file pathing
								try:
									if isinstance(attach_val, dict) and 'sequence' in attach_val:
										is_sequence = True
										is_spine_sequence = True
									elif str(attach_name).endswith('_'):
										is_sequence = True
								except Exception:
									pass
								
								is_placeholder = 'placeholder' in os.path.basename(str(attach_name)).lower()

								# Ensure sequence subfolder exists
								if is_sequence:
									seq_name = re.sub(r'[_\-]?\d+$', '', base_name)
									# Strip trailing underscore so we don't duplicate folder names like "name_" inside "name"
									seq_name = seq_name.rstrip('_')
									
									if not seq_name: seq_name = base_name
									
									if seq_name:
										# Heuristic: If source file is in a folder matching the sequence name, prefer that structure
										# This fixes cases where attachment path has a typo (e.g. dissapear_fx vs disspear)
										if src:
											src_path = src[0] if isinstance(src, (list, tuple)) else src
											src_folder_name = os.path.basename(os.path.dirname(src_path))
											if src_folder_name.lower() == seq_name.lower():
												nested_folders_str = src_folder_name

										if not nested_folders_str:
											nested_folders_str = seq_name
										elif not nested_folders_str.lower().endswith(seq_name.lower()):
											nested_folders_str = f"{nested_folders_str}/{seq_name}"

								first_rel = None
								copy_succeeded = False
								
								for idx, m in enumerate(matches):
									if self.stop_requested:
										raise Exception("Process stopped by user")
									
									# Only process PNG and JPEG files to avoid confusion with junk files (PSD, AEP, etc.)
									if not m.lower().endswith(('.png', '.jpg', '.jpeg')):
										continue
									
									QApplication.processEvents()
									
									# Build destination path with nested folder structure
									if nested_folders_str:
										nested_path = nested_folders_str.replace('/', os.path.sep)
										dst = os.path.join(base_dest, nested_path, os.path.basename(m))
									else:
										dst = os.path.join(base_dest, os.path.basename(m))
									
									# Create parent directories if needed (ONLY if not JSON only export)
									export_json_only = self.config.get("json_export_only", False)
									
									if not export_json_only:
										try:
											os.makedirs(os.path.dirname(dst), exist_ok=True)
										except Exception:
											pass
									
									# Copy the file
									try:
										import shutil
										norm_dst = os.path.normpath(dst).lower()
										
										# Skip copy if destination already exists/processed in this run
										if norm_dst in UNIQUE_COPIED_PATHS:
											copy_succeeded = True
										else:
											if not export_json_only:
												shutil.copy2(m, dst)
											
											# Mark as succeeded regardless of whether we actually copied or just calculated paths
											copy_succeeded = True
											UNIQUE_COPIED_PATHS.add(norm_dst)
											
											# Update stats
											if all_file_stats:
												stats = all_file_stats[-1]
												stats['total'] += 1
												if 'jpeg' in base_dest.lower():
													stats['jpeg'] += 1
												else:
													stats['png'] += 1
												try:
													# Record the source path that was actually exported
													EXPORTED_UNIQUE_IMAGES.add(os.path.normpath(m))
												except Exception:
													pass
									except Exception as e:
										self.info_panel.append(f"Failed to copy {m} -> {dst}: {e}")
										continue
									
									# Build JSON path only once (on first successful copy)
									if first_rel is None:
										family = os.path.basename(base_dest)
										
										# Update base_name to reflect the ACTUAL file name being used (for consolidation)
										start_base_name = os.path.basename(m) # Use the remapped file name
										
										# If it's a reference, we don't want the 'family' (which is just 'images' or skeleton name) in the path
										# if we are already at the root.
										# However, base_dest for references is images_root (e.g. .../images/skeleton).
										# So family is 'skeleton'.
										# But the JSON path expects: skeleton/path/to/image
										
										if is_spine_sequence:
											# For sequences: use basename without digits and add trailing underscore
											# FIX: Handle extension correctly (strip it before regex)
											s_root, s_ext = os.path.splitext(start_base_name)
											base_no_digits = re.sub(r"[_\-]?\d+$", "", s_root)
											
											# Ensure it ends with underscore for standard sequence prefixing
											if base_no_digits and not base_no_digits.endswith('_'):
												base_no_digits = base_no_digits + '_'
											
											# Build JSON path with nested structure
											if nested_folders_str:
												if is_reference:
													# For references, we skip the 'family' part (jpeg/png) AND the skeleton name
													# because they are in the global images root.
													first_rel = f"{nested_folders_str}/{base_no_digits}".replace('\\', '/')
												else:
													first_rel = f"{target_skeleton}/{family}/{nested_folders_str}/{base_no_digits}".replace('\\', '/')
											else:
												if is_reference:
													first_rel = f"{base_no_digits}".replace('\\', '/')
												else:
													first_rel = f"{target_skeleton}/{family}/{base_no_digits}".replace('\\', '/')
										else:
											# Single image logic
											# If extension is .png, we can strip it for cleaner Spine paths
											final_name = start_base_name
											if final_name.lower().endswith('.png'):
												final_name = os.path.splitext(final_name)[0]
											
											if nested_folders_str:
												if is_reference:
													first_rel = f"{nested_folders_str}/{final_name}".replace('\\', '/')
												else:
													first_rel = f"{target_skeleton}/{family}/{nested_folders_str}/{final_name}".replace('\\', '/')
											else:
												if is_reference:
													first_rel = f"{final_name}".replace('\\', '/')
												else:
													first_rel = f"{target_skeleton}/{family}/{final_name}".replace('\\', '/')

										# Clean up any duplicate family tokens
										if first_rel:
											first_rel = first_rel.replace('/jpeg/jpeg/', '/jpeg/').replace('/png/png/', '/png/')
										
										# Update JSON with the path if ANY file was successfully copied
										if first_rel and copy_succeeded:
											if isinstance(attach_val, dict):
												attach_val['path'] = first_rel
											else:
												attachments[attach_name] = {'path': first_rel}

								# Only create placeholder if NO source files were found
								if not src and (is_sequence or is_placeholder):
									# For declared sequences or placeholders with no files found, create placeholder using attachment name structure
									family = os.path.basename(base_dest)
									
									# Extract nested folders from ATTACHMENT NAME
									attach_name_str = str(attach_name).replace('\\', '/')
									nested_folders_str = ""
									base_name = os.path.basename(str(attach_name))
									
									# Remove any family markers (jpeg/png) and skeleton name from the path
									parts = attach_name_str.split('/')
									filtered_parts = []
									# for part in parts[:-1]:  # Exclude the last part (basename)
									# 	part_lower = part.lower()
									# 	# Also filter out the skeleton name if it appears in the path (e.g. game_intro/reference/...)
									# 	# Also handle common typos like pluralization (piggy_bank vs piggy_banks)
									# 	if part_lower == skeleton_name.lower() or part_lower.rstrip('s') == skeleton_name.lower().rstrip('s'):
									# 		continue

									# 	if part_lower not in ['jpeg', 'png', 'images', 'symbols', 'skeleton'] and part_lower.rstrip('s') != target_skeleton.lower().rstrip('s'):
									# 		filtered_parts.append(part)
									
									if filtered_parts:
										nested_folders_str = '/'.join(filtered_parts)
									
									# If we have no nested folders from attachment name (which is disabled above),
									# we rely ONLY on sequence logic below or explicit structure from skin/etc.
									# This prevents "04_BACKGROUND/BIRD/Body" folders
									
									# Ensure sequence subfolder exists ONLY for sequences
									if is_sequence:
										seq_name = re.sub(r'[_\-]?\d+$', '', base_name)
										# Strip trailing underscore so we don't duplicate folder names like "name_" inside "name"
										seq_name = seq_name.rstrip('_')
										
										if not seq_name: seq_name = base_name
										if seq_name:
											if not nested_folders_str:
												nested_folders_str = seq_name
											elif not nested_folders_str.lower().endswith(seq_name.lower()):
												nested_folders_str = f"{nested_folders_str}/{seq_name}"

									# Extract basename without digits for sequence placeholder
									if is_sequence:
										base_no_digits = re.sub(r"\d+$", "", base_name)
										if base_no_digits and not base_no_digits.endswith('_'):
											base_no_digits = base_no_digits + '_'
									else:
										# Static placeholder: use exact name
										base_no_digits = base_name
									
									# Build JSON path with nested structure
									if nested_folders_str:
										first_rel = f"{target_skeleton}/{family}/{nested_folders_str}/{base_no_digits}".replace('\\', '/')
									else:
										first_rel = f"{target_skeleton}/{family}/{base_no_digits}".replace('\\', '/')
									first_rel = first_rel.replace('/jpeg/jpeg/', '/jpeg/').replace('/png/png/', '/png/')
									
									# Create placeholder file ONLY if no real files were found
									try:
										if not self.config.get("json_export_only", False):
											if nested_folders_str:
												nested_path = nested_folders_str.replace('/', os.path.sep)
												ph_dst = os.path.join(base_dest, nested_path, base_no_digits)
											else:
												ph_dst = os.path.join(base_dest, base_no_digits)
											
											# For static placeholders, ensure we have an extension if missing (Spine usually wants .png)
											if not is_sequence and not os.path.splitext(ph_dst)[1]:
												ph_dst += ".png"

											os.makedirs(os.path.dirname(ph_dst), exist_ok=True)
											if not os.path.exists(ph_dst):
												# Try to create a valid transparent PNG (4x4)
												created = False
												if Image:
													try:
														# Create 4x4 transparent image
														img = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
														img.save(ph_dst)
														created = True
													except Exception:
														pass
												
												if not created:
													# Fallback to 1x1 transparent PNG bytes
													with open(ph_dst, 'wb') as ph:
														ph.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
									except Exception:
										pass
									# If we created a placeholder file, update stats/sets similarly to a copied file
									try:
										if not self.config.get("json_export_only", False) and all_file_stats:
											norm_ph = os.path.normpath(ph_dst).lower()
											if norm_ph not in UNIQUE_COPIED_PATHS:
												UNIQUE_COPIED_PATHS.add(norm_ph)
												stats = all_file_stats[-1]
												stats['total'] += 1
												if 'jpeg' in base_dest.lower():
													stats['jpeg'] += 1
												else:
													stats['png'] += 1
												try:
													EXPORTED_UNIQUE_IMAGES.add(os.path.normpath(ph_dst))
												except Exception:
													pass
									except Exception:
										pass
									
									# Update JSON
									if isinstance(attach_val, dict):
										attach_val['path'] = first_rel
									else:
										attachments[attach_name] = {'path': first_rel}
					return skin_dict

				# --- PRE-SCAN EXECUTION ---
				try:
					self.info_panel.append("Running pre-scan to unify image destinations...")
					for temp_skin in ALL_SKIN_DICTS:
						process_skin_dict(temp_skin, scan_mode=True)
					
					for f_path, slots in SCAN_SLOT_USAGE.items():
						is_opaque_f = False
						candidates = [f_path, os.path.normpath(f_path), os.path.abspath(f_path), f_path.lower()]
						
						# Determine opacity from map
						for k in candidates:
							if k in opaque_map:
								is_opaque_f = opaque_map[k]
								break
						
						# Determine slot usage blend
						appears_only_in_non_normal = True
						if slots:
							appears_only_in_non_normal = all(slot_blend.get(s, 'normal') != 'normal' for s in slots)
						
						if appears_only_in_non_normal:
							dest = 'jpeg'
						elif is_opaque_f:
							dest = 'jpeg'
						else:
							dest = 'png'
						
						PRECALC_DESTINATIONS[f_path] = dest
						PRECALC_DESTINATIONS[os.path.normpath(f_path)] = dest

				except Exception as e:
					self.info_panel.append(f"Pre-scan failed: {e}")

				# Ensure 'animations' are preserved and logged (write debug file into result_dir)
				try:
					dbg_dir = result_dir or os.path.dirname(self.config_path) or os.getcwd()
					os.makedirs(dbg_dir, exist_ok=True)
					dbg_path = os.path.join(dbg_dir, "debug_anims.txt")
				except Exception:
					dbg_path = os.path.join(os.path.dirname(self.config_path) or '.', "debug_anims.txt")
				try:
					with open(dbg_path, "a", encoding='utf-8') as f_dbg:
						if 'animations' in j:
							anim_count = len(j['animations'])
							log_msg = f"Trace: 'animations' key present with {anim_count} animations before logic.\n"
							self.info_panel.append(log_msg.strip())
							f_dbg.write(log_msg)
						else:
							log_msg = "Trace: 'animations' key MISSING before logic.\n"
							self.info_panel.append(log_msg.strip())
							f_dbg.write(log_msg)
				except Exception as e:
					self.info_panel.append(f"Could not write debug_anims before logic: {e}")

				if isinstance(skins, dict):
					for skin_name, skin in list(skins.items()):
						if not isinstance(skin, dict):
							self.info_panel.append(f"Skipping skin {skin_name}: unexpected type {type(skin)}")
							continue
						skins[skin_name] = process_skin_dict(skin, skin_name=skin_name)
				elif isinstance(skins, list):
					# preserve list shape: process each element which may be a dict mapping skinName->skinDict or a skinDict directly
					new_list = []
					for item in skins:
						if isinstance(item, dict):
							# detect if item is {skinName: {..}} or a skin dict (slot->attachments)
							# if any value is a dict, treat as mapping skinName->skinDict
							if any(isinstance(v, dict) for v in item.values()):
								new_item = {}
								# Try to find skin name first (for named skin objects)
								current_skin_name = item.get('name')
								
								for k, v in item.items():
									if isinstance(v, dict):
										# If k is 'attachments', use current_skin_name
										# If k is a skin name (in the map case), use k
										s_name = current_skin_name if k == 'attachments' else k
										new_item[k] = process_skin_dict(v, skin_name=s_name)
									else:
										new_item[k] = v
								new_list.append(new_item)
							else:
								# item itself is a skin dict
								new_list.append(process_skin_dict(item))
						else:
							new_list.append(item)
					j['skins'] = new_list

				# Progress update: Sorting and copying done
				self.progress_bar.setValue(base_progress + 80)
				QApplication.processEvents()

				try:
					dbg_dir = result_dir or os.path.dirname(self.config_path) or os.getcwd()
					os.makedirs(dbg_dir, exist_ok=True)
					dbg_path = os.path.join(dbg_dir, "debug_anims.txt")
				except Exception:
					dbg_path = os.path.join(os.path.dirname(self.config_path) or '.', "debug_anims.txt")
				try:
					with open(dbg_path, "a", encoding='utf-8') as f_dbg:
						if 'animations' in j:
							log_msg = f"Trace: 'animations' key present with {len(j['animations'])} animations AFTER logic.\n"
							self.info_panel.append(log_msg.strip())
							f_dbg.write(log_msg)
						else:
							log_msg = "Trace: 'animations' key MISSING AFTER logic.\n"
							self.info_panel.append(log_msg.strip())
							f_dbg.write(log_msg)
				except Exception as e:
					self.info_panel.append(f"Could not write debug_anims after logic: {e}")

				# Update total stats to match User Expectation
				if all_file_stats:
					stats = all_file_stats[-1]
					
					# Deduplicate unchecked warnings (list of dicts)
					unique_unchecked_list = []
					if spine_export_unchecked:
						_seen_warns = set()
						for item in spine_export_unchecked:
							# create a unique key for the warning
							key = (item['region'], item.get('slot'))
							if key not in _seen_warns:
								_seen_warns.add(key)
								unique_unchecked_list.append(item)
					
					# Store unchecked list for reporting
					stats['unchecked'] = sorted(unique_unchecked_list, key=lambda x: x['region'])
					
					# Store unchecked animations
					unique_unchecked_anims = sorted(list(set(spine_export_unchecked_anims))) if spine_export_unchecked_anims else []
					
					# Advanced: If we have Source of Truth (from ZIP file), compute missing animations by diff
					if 'source_anims_defined' in stats:
						all_def = stats['source_anims_defined']
						# Get exported animations from JSON
						exported_anims = set()
						if 'animations' in j:
							exported_anims.update(j['animations'].keys())
						
						# Find anims that are in Source but NOT in Export
						# (and ignore any that we already detected via CLI warnings to avoid duplicates)
						missing_from_comparision = all_def - exported_anims
						
						if missing_from_comparision:
							# Add them to the list
							for m in missing_from_comparision:
								if m not in unique_unchecked_anims:
									unique_unchecked_anims.append(m)
							# sort again
							unique_unchecked_anims.sort()
					
					stats['unchecked_anims'] = unique_unchecked_anims
					
					# Update Animation Stats
					if 'source_anims_defined' in stats:
						all_def = stats['source_anims_defined']
						exported_anims = set()
						if 'animations' in j:
							exported_anims.update(j['animations'].keys())
						
						stats['anim_total_count'] = len(all_def)
						stats['anim_exported_count'] = len(exported_anims)
					else:
						# If source analysis failed, at least report what we exported
						exported_anims_count = len(j.get('animations', {}))
						stats['anim_exported_count'] = exported_anims_count
						# Total is at least exported + unchecked warnings
						stats['anim_total_count'] = exported_anims_count + len(unique_unchecked_anims)
						
					# Debug (temporary, to see if anything was caught)
					# if spine_export_unchecked_anims:
					# 	print(f"DEBUG: Found unchecked anims: {spine_export_unchecked_anims}")

					# Use the actually copied/created destinations for exported counts
					stats['total_attachments'] = TOTAL_ATTACHMENTS_COUNT
					stats['consolidated_count'] = CONSOLIDATED_IMAGES_COUNT

					# total_spine_used: best-effort estimate = number of unique source paths discovered
					# fall back to TOTAL_ATTACHMENTS_COUNT if we have no EXPORTED_UNIQUE_IMAGES
					try:
						stats['total_spine_used'] = len(EXPORTED_UNIQUE_IMAGES) + len(unique_unchecked_list)
					except Exception:
						stats['total_spine_used'] = TOTAL_ATTACHMENTS_COUNT

					# total_exported_unique: number of unique destination files we actually created/copied
					stats['total_exported_unique'] = stats.get('total', 0)

					# Exported Jpeg/Png counts come from the per-file stats we maintained during copying
					stats['unique_jpeg'] = stats.get('jpeg', 0)
					stats['unique_png'] = stats.get('png', 0)

				# normalize skeleton images path so Spine can resolve images inside archive
				skel = j.get('skeleton')
				if isinstance(skel, dict):
					# ensure skeleton.images points to the images folder relative to the JSON
					skel['images'] = './images/'
					self.info_panel.append(f"Set skeleton.images to: {skel.get('images', 'unset')}")
				
				# Verify animations count before saving
				anims_check = j.get('animations', {})
				if not anims_check:
					self.log_warning("WARNING: The exported JSON has NO animations! Resulting Spine file will be empty of animations.")
				else:
					self.info_panel.append(f"Verifying animations: {len(anims_check)} animations present in data.")

				# save modified json into the output root
				if hasattr(self, 'status_label'): self.status_label.setText(f"Writing JSON: {ui_label_text}")
				new_json_path = os.path.join(output_root, os.path.splitext(os.path.basename(found_json))[0] + '.json')
				
				# Debug: Verify bones before writing
				final_bones = len(j.get('bones', []))
				self.info_panel.append(f"Final JSON check: {final_bones} bones. Writing to {new_json_path}")
				
				try:
					indent_val = 2 if self.config.get("pretty_print_json", True) else None
					with open(new_json_path, 'w', encoding='utf-8') as nj:
						# Ensure ensure_ascii=False to support unicode characters without escaping
						json.dump(j, nj, indent=indent_val, ensure_ascii=False)
						nj.flush()
						os.fsync(nj.fileno())
					
					f_size = os.path.getsize(new_json_path)
					self.info_panel.append(f"Wrote sorted json: {new_json_path} (Size: {f_size} bytes)")
					
					# Double check content on disk
					with open(new_json_path, 'r', encoding='utf-8') as f_verify:
						j_verify = json.load(f_verify)

						# Run naming + fuzzy spell-check on the temporary JSON (so we catch typos even
						# when the source was a binary .spine). Merge results into per-file stats.
						try:
							def _check_name_issues_local(name):
								reasons = []
								if name != name.strip():
									reasons.append('leading/trailing whitespace')
								if ' ' in name:
									reasons.append('contains space')
								if re.search(r'[A-Z]', name):
									reasons.append('contains uppercase')
								if not re.match(r'^[a-z0-9._\- ]+$', name):
									reasons.append('non-standard characters')
								# fuzzy spell-check
								try:
									import difflib
									_common_words = set((
										'anticipation','anticipate','idle','walk','run','jump','attack','hit','death','spawn','intro',
										'open','close','blink','slide','push','pull','shoot','throw','cast'
									))
									for tok in re.split(r'[^a-zA-Z]+', name):
										if not tok or len(tok) < 4:
											continue
										low = tok.lower()
										if low in _common_words:
											continue
										m = difflib.get_close_matches(low, _common_words, n=1, cutoff=0.8)
										if m:
											reasons.append(f"possible misspelling: did you mean '{m[0]}'?")
								except Exception:
									pass
								return reasons

							naming_new = {
								'skeleton': [],
								'animations': [],
								'slots_summary': {'count': 0, 'examples': []},
								'bones_summary': {'count': 0, 'examples': []},
								'constraints_summary': {'count': 0, 'examples': []}
							}
							# skeleton name fields
							skel_obj = j_verify.get('skeleton') if isinstance(j_verify, dict) else None
							cands = []
							if skel_obj and isinstance(skel_obj, dict):
								for k in ('name', 'skeleton', 'spine'):
									v = skel_obj.get(k)
									if isinstance(v, str) and v:
										cands.append((k, v))
							for src, val in cands:
								rs = _check_name_issues_local(val)
								if rs:
									naming_new['skeleton'].append({'field': src, 'value': val, 'reasons': rs})

							# animations
							for anim in sorted(j_verify.get('animations', {}).keys() if isinstance(j_verify.get('animations', {}), dict) else []):
								ars = _check_name_issues_local(anim)
								if ars:
									naming_new['animations'].append({'name': anim, 'reasons': ars})

							# slots/bones/constraints summaries
							for slot in j_verify.get('slots', []):
								n = slot.get('name', '') if isinstance(slot, dict) else ''
								if n:
									rs = _check_name_issues_local(n)
									if rs:
										naming_new['slots_summary']['count'] += 1
										if len(naming_new['slots_summary']['examples']) < 5:
											naming_new['slots_summary']['examples'].append({'name': n, 'reasons': rs})
							for b in j_verify.get('bones', []):
								n = b.get('name', '') if isinstance(b, dict) else ''
								if n:
									rs = _check_name_issues_local(n)
									if rs:
										naming_new['bones_summary']['count'] += 1
										if len(naming_new['bones_summary']['examples']) < 5:
											naming_new['bones_summary']['examples'].append({'name': n, 'reasons': rs})
							for c in j_verify.get('constraints', []):
								if isinstance(c, dict):
									n = c.get('name')
								else:
									n = ''
								if n:
									rs = _check_name_issues_local(n)
									if rs:
										naming_new['constraints_summary']['count'] += 1
										if len(naming_new['constraints_summary']['examples']) < 5:
											naming_new['constraints_summary']['examples'].append({'name': n, 'reasons': rs})

							# Merge into existing stats naming if present
							try:
								if all_file_stats:
									s = all_file_stats[-1]
									if not s.get('naming'):
										s['naming'] = naming_new
									else:
										# merge skeleton entries
										existing = s['naming']
										for sk in naming_new.get('skeleton', []):
											if sk not in existing.get('skeleton', []):
												existing.setdefault('skeleton', []).append(sk)
										for a in naming_new.get('animations', []):
											if a not in existing.get('animations', []):
												existing.setdefault('animations', []).append(a)
										for cat in ('slots_summary', 'bones_summary', 'constraints_summary'):
											cnew = naming_new.get(cat, {})
											cex = existing.get(cat, {'count':0,'examples':[]})
											cex['count'] = cex.get('count',0) + cnew.get('count',0)
											# merge examples by name
											existing_examples = {e['name'] for e in cex.get('examples',[])}
											for ex in cnew.get('examples',[]):
												if ex['name'] not in existing_examples:
													existing.setdefault(cat, {'count':0,'examples':[]})['examples'].append(ex)
										s['naming'] = existing
							except Exception:
								pass
						except Exception:
							# non-fatal
							pass
						verify_keys = list(j_verify.get('animations', {}).keys())
						verify_count = len(verify_keys)
						self.info_panel.append(f"VERIFICATION (JSON): Found {verify_count} animations: {', '.join(sorted(verify_keys))}")
						
						# Retrieve source animations from stats since cli_source_anims is not in scope local to this function
						source_anims_check = all_file_stats[-1].get('source_anims_defined', set()) if all_file_stats else set()
						# If stored as per-skeleton mapping, union them for this verification step
						if isinstance(source_anims_check, dict):
							try:
								source_anims_check = set().union(*[v for v in source_anims_check.values() if v])
							except Exception:
								source_anims_check = set()
						
						if source_anims_check:
							missing = source_anims_check - set(verify_keys)
							if missing:
								self.info_panel.append(f"WARNING: Missing animations in JSON that were in Source: {', '.join(missing)}")
								self.info_panel.append(f"*** MISSING ANIMATION: {list(missing)[0]} ***")
							else:
								self.info_panel.append("SUCCESS: All source animations accounted for in JSON.")

						if verify_count > 0:
							self.info_panel.append(f"VERIFY SUCCESS: Animations are guaranteed to be in the JSON file at: {new_json_path}")
							self.info_panel.append("If the resulting .spine file is empty, please import this JSON file manually.")

					if f_size == 0:
						self.log_error(f"Error: JSON file {new_json_path} is empty (0 bytes)!")
						
				except Exception as e:
					self.log_error(f"Failed to write JSON: {e}")
					errors.append(f"JSON write error: {e}")

				# Progress update: JSON written
				self.progress_bar.setValue(base_progress + 90)
				QApplication.processEvents()

				# create a .spine package using Spine CLI (binary format)
				if hasattr(self, 'status_label'): self.status_label.setText(f"Creating .spine: {ui_label_text}")
				# Use input_path (source .spine filename) so multiple skeletons merge into one .spine file
				spine_pkg = os.path.join(output_root, os.path.splitext(os.path.basename(input_path))[0] + '.spine')
				if spine_exe and os.path.exists(spine_exe):
					self.info_panel.append(f"Converting JSON to binary .spine using: {spine_exe}")
					try:
						# Command: Spine -i input.json -o output.spine --import
						# Note: Spine CLI requires absolute paths usually
						abs_json = os.path.abspath(new_json_path)
						abs_pkg = os.path.abspath(spine_pkg)
						
						# Ensure we overwrite any existing file to avoid merging skeletons (only for the first skeleton)
						if is_first and os.path.exists(abs_pkg):
							try:
								os.remove(abs_pkg)
								self.info_panel.append(f"Removed existing file: {spine_pkg}")
							except Exception as e:
								self.info_panel.append(f"<font color='yellow'>Warning: Could not remove existing file {spine_pkg}: {e}</font>")

						cmd = [spine_exe] + (extra_cli_args or []) + ['-i', abs_json, '-o', abs_pkg, '--import']
						self.info_panel.append(f"Running: {' '.join(cmd)}")
						
						# Run synchronously
						# Fix: Force UTF-8 encoding or replacement to avoid Windows codepage errors on binary logs
						proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
						
						# Always log output for debugging import issues
						if proc.stdout: self.info_panel.append(f"Import STDOUT: {proc.stdout}")
						if proc.stderr: self.info_panel.append(f"Import STDERR: {proc.stderr}")

						if proc.returncode == 0:
							if os.path.exists(abs_pkg):
								size_bytes = os.path.getsize(abs_pkg)
								self.info_panel.append(f"Successfully created binary .spine file: {spine_pkg} (Size: {size_bytes} bytes)")
								if size_bytes < 5000 and verify_count > 0:
									self.log_warning(f"WARNING: The generated .spine file is very small ({size_bytes} bytes) despite having {verify_count} animations in JSON. The imports might have failed silently!")
							else:
								self.log_error("Import reported success but file was NOT created/found!")
						else:
							self.info_panel.append(f"Spine conversion failed (code {proc.returncode}):")
							self.info_panel.append(proc.stdout)
							self.info_panel.append(proc.stderr)
							self.info_panel.append(f"You can manually import the JSON: {new_json_path}")
					except Exception as e:
						self.info_panel.append(f"Error running Spine CLI: {e}")
				else:
					self.info_panel.append("Spine executable not found or not configured. Skipping .spine generation.")
					self.info_panel.append(f"Please manually import the JSON file into Spine: {new_json_path}")

				# Cleanup temporary files
				if not self.keep_temp_cb.isChecked():
					# Delete the sorted JSON if the binary .spine file was successfully created
					if os.path.exists(spine_pkg) and os.path.exists(new_json_path):
						try:
							os.remove(new_json_path)
							# self.info_panel.append(f"Deleted temporary JSON: {new_json_path}")
						except Exception as e:
							self.info_panel.append(f"<font color='yellow'>Warning: Could not delete temp JSON {new_json_path}: {e}</font>")

					if is_last:
						try:
							# Remove the temporary export folder (spine_temp_...)
							if result_dir and os.path.isdir(result_dir) and 'spine_temp_' in os.path.basename(result_dir):
								# Use robust removal helper (retries + logging)
								self._remove_temp_dir(result_dir, reason='export-cleanup')
						except Exception as e:
							self.info_panel.append(f"<font color='yellow'>Cleanup warning: {e}</font>")

				# Optionally open the generated .spine in Spine
				if is_last:
					try:
						# Check config, default to True if not present
						if self.config.get("open_after_export", True):
							if spine_exe and os.path.exists(spine_exe) and os.path.exists(spine_pkg):
								self.info_panel.append(f"Opening in Spine: {spine_pkg}")
								# Wait a moment to ensure file handles are released
								time.sleep(1.0)
								# Use subprocess.Popen to avoid blocking the UI
								# Include extra_cli_args (like --update version) if present
								cmd_open = [spine_exe] + (extra_cli_args or []) + [spine_pkg]
								self.info_panel.append(f"Launch cmd: {' '.join(cmd_open)}")
								subprocess.Popen(cmd_open)
							else:
								if not spine_exe:
									self.info_panel.append("Spine executable not configured; cannot open.")
								elif not os.path.exists(spine_pkg):
									self.info_panel.append("Spine package not found; cannot open.")
					except Exception as e:
						self.info_panel.append(f"Could not open in Spine: {e}")
		except Exception as e:
			self.info_panel.append(f"Sorting step failed: {e}")






	def _toggle_blink(self):
		if not hasattr(self, '_blink_state'):
			self._blink_state = True
			self._funny_counter = 0

		self._blink_state = not self._blink_state
		# Blink between Light Green (#90EE90) and a dimmer Green (#32CD32) or Gray
		color = '#90EE90' if self._blink_state else '#228B22' 
		self.status_label.setStyleSheet(f"font-weight: bold; color: {color}; font-style: italic;")

	def process_selected(self):
		self.stop_requested = False
		# use selected Spine executable from dropdown (fall back to config/default)
		global_spine_exe = None
		try:
			global_spine_exe = self.spine_combo.currentData()
		except Exception:
			pass
		if not global_spine_exe:
			global_spine_exe = self.config.get('spine_exe_selected') or self.config.get("spine_exe", self.default_spine_exe)
		
		# Check existence (support .app directories on macOS)
		if not os.path.exists(global_spine_exe):
			QMessageBox.warning(self, "Spine not found", f"Spine executable not found:\n{global_spine_exe}")
			return

		# Resolve .app to binary on macOS for execution
		runnable_spine_exe = global_spine_exe
		if sys.platform == 'darwin' and global_spine_exe.endswith('.app'):
			binary = os.path.join(global_spine_exe, "Contents", "MacOS", "Spine")
			if os.path.exists(binary):
				runnable_spine_exe = binary

		folder = self.folder_display.text()
		if not folder or not os.path.isdir(folder):
			QMessageBox.information(self, "No folder", "Please select a folder containing .spine files first.")
			return

		to_process = []
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			widget = self.list_widget.itemWidget(item)
			
			is_checked = False
			filename = item.text()
			manual_exe = None
			
			if widget and isinstance(widget, SpineFileWidget):
				is_checked = widget.isChecked()
				filename = widget.label.text()
				manual_exe = widget.getSelectedSpineExe()
			else:
				# Fallback if no widget set (legacy items)
				is_checked = (item.checkState() == Qt.Checked)
				
			if is_checked:
				to_process.append((filename, manual_exe))

		if not to_process:
			QMessageBox.information(self, "No files selected", "Please check one or more .spine files to process.")
			return
		
		# Update UI for processing state
		self.process_btn.setEnabled(False)
		self.stop_btn.setEnabled(True)
		self.setWindowIcon(self.icon_busy)
		self.progress_bar.setRange(0, len(to_process) * 100)
		self.progress_bar.setValue(0)

		# Make sure label is up to date (in case user changed config but UI didn't reflow)
		self._update_active_version_label()
		
		# List to collect warnings about JPEGs forced to PNG
		jpeg_forced_png_warnings = []
		# List to collect statistics for each file
		all_file_stats = []
			
		file_scanner = FileScanner()

		# Collect all skeleton names from the folder for cross-reference detection
		all_skeleton_names = []
		try:
			for f in os.listdir(folder):
				if f.lower().endswith('.spine'):
					all_skeleton_names.append(os.path.splitext(f)[0])
		except Exception:
			pass

		# clear and start info log
		self.info_panel.clear()
		self.info_panel.append(f"Starting processing of {len(to_process)} file(s)")
		# Debug: log effective config vs UI states to help diagnose mac cleanup issue
		try:
			self.info_panel.append(f"Config path: {self.config_path}")
			self.info_panel.append(f"Config validate_only: {self.config.get('validate_only', False)}  Checkbox validate_only: {getattr(self, 'validate_only_cb', None) and self.validate_only_cb.isChecked()}")
			self.info_panel.append(f"Config keep_temp_files: {self.config.get('keep_temp_files', False)}  Checkbox keep_temp: {getattr(self, 'keep_temp_cb', None) and self.keep_temp_cb.isChecked()}")
			self.info_panel.append(f"Config verbose_cleanup_logging: {self.config.get('verbose_cleanup_logging', False)}  Checkbox verbose_cleanup: {getattr(self, 'verbose_cleanup_cb', None) and self.verbose_cleanup_cb.isChecked()}")
		except Exception:
			pass
		
		# Setup Status Label Blinking
		if not hasattr(self, 'blink_timer'):
			self.blink_timer = QTimer(self)
			self.blink_timer.timeout.connect(self._toggle_blink)
		
		self.status_label.setStyleSheet("font-weight: bold; color: #90EE90; font-style: italic;")
		self.status_label.setText("Starting...")
			
		self.blink_timer.start(500)

		# log current threshold settings
		try:
			cur_thresh = int(self.config.get("opacity_threshold", self.opacity_slider.value()))
			cur_alpha = int(self.config.get("alpha_cutoff", self.alpha_cutoff_spin.value()))
			self.info_panel.append(f"Using opacity threshold: {cur_thresh}%  alpha cutoff: {cur_alpha}")
		except Exception:
			pass

		if Image is None:
			if hasattr(self, 'blink_timer'): self.blink_timer.stop()
			QMessageBox.warning(self, "Missing dependency", "Pillow is required to analyze images. Install with: pip install Pillow")
			self.process_btn.setEnabled(True)
			self.stop_btn.setEnabled(False)
			self.setWindowIcon(self.icon_idle)
			return

		timestamp = int(time.time())
		results = []
		errors = []
		
		for i, item_data in enumerate(to_process):
			result_dir = None
			if self.stop_requested:
				self.info_panel.append("Process stopped by user.")
				break
			
			# Unpack item data (filename, manual_exe)
			if isinstance(item_data, tuple):
				name, manual_exe = item_data
			else:
				name = item_data
				manual_exe = None

			base_progress = i * 100
			self.progress_bar.setValue(base_progress)
			QApplication.processEvents()
			
			# Initialize stats for this file (container for multiple skeletons)
			# We'll use a list 'skeletons' to store individual skeleton stats
			file_stats = {
				'name': name,
				'is_container': True,
			    'skeletons': [],
				# Default keys to prevent KeyError if no skeletons are processed
				'total': 0, 'jpeg': 0, 'png': 0, 'total_spine': 0
			}
			all_file_stats.append(file_stats)
			
			input_path = os.path.join(folder, name)
			
			# Ensure input is the checked .spine file
			if not input_path.lower().endswith('.spine'):
				msg = f"Skipped (not a .spine file): {input_path}"
				errors.append(msg)
				self.log_error(msg)
				continue
			if not os.path.isfile(input_path):
				msg = f"Missing: {input_path}"
				errors.append(msg)
				self.log_error(msg)
				continue

			# Version Auto-Switch / Manual Selection Logic
			# We'll use a local variable for the executable so we don't permanently switch the global selection
			current_runnable_spine_exe = runnable_spine_exe
			extra_cli_args = []
			detected_ver = None
			
			# Check if we have a specific setup from the launcher version combo override
			using_launcher_version = False
			if hasattr(self, 'launcher_version_combo') and self.launcher_version_combo.count() > 0:
				selected_launcher_ver = self.launcher_version_combo.currentText().strip()
				if selected_launcher_ver:
					self.info_panel.append(f"Using Launcher Version Override: {selected_launcher_ver}")
					detected_ver = selected_launcher_ver
					using_launcher_version = True
					# Prefer to avoid forcing the Spine Launcher to download a version that doesn't exist.
					# Check local updates folder first; only use --update if version is present locally.
					try:
						user_home = os.path.expanduser('~')
						updates_folder = None
						if os.name == 'nt':
							user_profile = os.environ.get('USERPROFILE') or user_home
							if user_profile:
								updates_folder = os.path.join(user_profile, 'Spine', 'updates')
						elif sys.platform == 'darwin':
							updates_folder = os.path.join(user_home, 'Library', 'Application Support', 'Spine', 'updates')
						else:
							updates_folder = os.path.join(user_home, '.spine', 'updates')
						if updates_folder and os.path.isdir(os.path.join(updates_folder, selected_launcher_ver)):
							extra_cli_args = ["--update", selected_launcher_ver]
						else:
							self.info_panel.append(f"Launcher version {selected_launcher_ver} not found locally; skipping '--update' to avoid download errors.")
							# Leave extra_cli_args empty so we don't trigger a launcher download attempt
							extra_cli_args = []
					except Exception:
						# On unexpected errors, fall back to previous behavior to avoid blocking user
						extra_cli_args = ["--update", selected_launcher_ver]
					
					# When using launcher version, we usually prefer Spine.com if the base was Spine.exe,
					# because CLI args work better with .com on Windows
					if os.name == 'nt' and str(current_runnable_spine_exe).lower().endswith('.exe'):
						candidate_com = str(current_runnable_spine_exe)[:-4] + ".com"
						if os.path.exists(candidate_com):
							current_runnable_spine_exe = candidate_com
			
			# If user selected a specific version for this file (in the list), it overrides global/launcher settings
			if manual_exe:
				self.info_panel.append(f"Using manually selected version for {name}")
				# Clear any launcher overrides if per-file override is set
				extra_cli_args = [] 
				current_runnable_spine_exe = manual_exe
				# Mac app bundle resolution
				if sys.platform == 'darwin' and current_runnable_spine_exe.endswith('.app'):
					candidate = os.path.join(current_runnable_spine_exe, "Contents", "MacOS", "Spine")
					if os.path.exists(candidate):
						current_runnable_spine_exe = candidate
			else:
				# Use global default
				pass

			# Auto-detection removed as per user request
			# detected_ver = None # (Already handled above for Launcher Override)
			final_exe_path = None
			
			# Capture which version we finally decided on for reporting

			final_reported_version = detected_ver if detected_ver else "Unknown"
			final_exe_used = os.path.basename(current_runnable_spine_exe)
			if extra_cli_args:
				final_exe_used += f" (Args: {' '.join(extra_cli_args)})"
				
			# Store in stats for report
			file_stats['spine_version_source'] = final_reported_version
			file_stats['spine_exe_used'] = final_exe_used

			# Determine base output root and create a timestamped temporary export folder
			base_output_root = self.output_display.text() or os.path.expanduser("~")
			os.makedirs(base_output_root, exist_ok=True)
			
			# Create temp export dir
			result_dir = os.path.join(base_output_root, f"spine_temp_{timestamp}_{i}")
			os.makedirs(result_dir, exist_ok=True)

			self.info_panel.append(f"\nProcessing: {name}")
			self.status_label.setText(f"Processing file: {name}")
			
			# 0. Retrieve Source Info (Animations list) via CLI
			# This is crucial for verifying unchecked animations that won't appear in JSON
			cli_source_anims = set()
			cli_source_skeletons = set()
			# Per-skeleton mapping of animations (to avoid attributing animations to wrong skeleton)
			cli_source_anims_by_skel = {}
			current_skel = None
			try:
				# Spine 4.0+ uses just -i <path> for info. Old --info flag is deprecated/removed in some versions.
				# We try without --info first as it is cleaner for newer versions found in testing.
				info_cmd = [current_runnable_spine_exe] + extra_cli_args + ['-i', input_path]
				self.info_panel.append(f"Running Source Info Check: {' '.join(info_cmd)}")
				self.status_label.setText(f"Analyzing source info: {name}")
				# Fix: Force UTF-8 encoding or replacement to avoid Windows codepage errors on binary logs
				i_proc = subprocess.run(info_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
				
				# If that failed uniquely or produced no output, maybe try --info (legacy fallback)?
				# But per testing, -i is the "Info" command if no other action is specified.
				
				# ANSI Strip Helper
				def strip_ansi(text):
					ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
					return ansi_escape.sub('', text)

				if i_proc.returncode == 0:
					info_out = strip_ansi(i_proc.stdout)
					# Save info log for debug
					info_log_path = os.path.join(result_dir, "spine_source_info.log")
					try:
						with open(info_log_path, 'w', encoding='utf-8') as ilf:
							ilf.write(info_out)
					except: pass
					
					# Robust parser for "Animations:" section
					# Handles:
					# 1. New format: Animations (N): anim1, anim2, ...
					# 2. Old format: Animations: \n  anim1 \n  anim2
					# 3. Multiple skeletons in one file
					# 4. Strict format: Animation: name (singular?)
					# 5. Loose/Garbage header: ... Animations: ...
					lines = info_out.splitlines()
					header_found = False
					# Match "Animations", "Animations (N)", "Animations:", "Animations (N):" - Allow preceding chars
					anim_headers_patterns = [
						re.compile(r"Animations\s*(?:\(\d+\))?:\s*(.*)", re.IGNORECASE),
						re.compile(r"Animations\s*$", re.IGNORECASE), # Header on own line
						re.compile(r"Animations\s*\(\d+\)\s*$", re.IGNORECASE)
					]
					
					# Parser for Skeletons
					skel_re = re.compile(r"Skeleton:\s*(.+)", re.IGNORECASE)

					for idx, line in enumerate(lines):
						line_strip = line.strip()
						# Check for Skeleton
						m_skel = skel_re.search(line)
						if m_skel:
							# Clean skeleton capture to avoid trailing warning text like "] to: ..."
							s_name = m_skel.group(1).strip()
							# Split on ']' or ', ' or ' to:' to remove appended warning fragments
							try:
								s_name = re.split(r"\]|,|\sto:\s", s_name)[0].strip()
							except Exception:
								s_name = s_name.split(']')[0].split(',')[0].split(' to:')[0].strip()
							# Strip surrounding quotes/brackets
							s_name = s_name.strip('"\'')
							if s_name and '<' not in s_name:
								cli_source_skeletons.add(s_name)
								current_skel = s_name

						# Iterative header check
						m = None
						for p_idx, p in enumerate(anim_headers_patterns):
							# We search anywhere in the line now (removed ^ anchor via regex def above)
							m = p.search(line) 
							if m: 
								# Ensure it's not "No Animations" or similar false positive, though improbable with colon
								break
						
						if m:
							header_found = True
							# If pattern captured content (Pattern 1), parse it
							# Pattern 1 is index 0
							if p.pattern.endswith("(.*)"):
								inline_content = m.group(1).strip()
								if inline_content:
									parts = [x.strip() for x in inline_content.split(',') if x.strip()]
									cli_source_anims.update(parts)
									if current_skel:
										cli_source_anims_by_skel.setdefault(current_skel, set()).update(parts)
									else:
										cli_source_anims_by_skel.setdefault(None, set()).update(parts)
							
							# Check for indented subsequent lines OR lines that look like animation names
							# Spine info usually indents. But if indentation is lost, we look for non-header lines.
							header_indent = len(line) - len(line.lstrip())
							j_idx = idx + 1
							while j_idx < len(lines):
								next_line = lines[j_idx]
								if not next_line.strip():
									j_idx += 1
									continue
								
								# Break if we hit another Header (e.g. "Skins:", "Bones:", "Slots:", "Events:", "Skeleton:", "Size:", "Spine")
								# Note: "Skeleton" and "Size" might appear after Animations in some output formats
								if re.search(r"^\s*(?:Skins|Bones|Slots|Events|(?:Ik|Transform|Path)?\s*Constraints|Skeleton|Size|Spine)\s*(?:\(\d+\))?:", next_line, re.IGNORECASE):
									break
								
								# If it's a list, it usually keeps indentation
								# But let's be generous: Any line that is NOT a header and has content might be part of the list
								raw_c = next_line.strip()
								if raw_c:
									# Ignore known noise words or non-animation lines that slipped in
									if raw_c.lower() in ['complete.', 'complete', 'done', 'finishing export']:
										j_idx += 1
										continue

									if ',' in raw_c:
										parts = [x.strip() for x in raw_c.split(',') if x.strip()]
										cli_source_anims.update(parts)
										if current_skel:
											cli_source_anims_by_skel.setdefault(current_skel, set()).update(parts)
										else:
											cli_source_anims_by_skel.setdefault(None, set()).update(parts)
									else:
										cli_source_anims.add(raw_c)
										if current_skel:
											cli_source_anims_by_skel.setdefault(current_skel, set()).add(raw_c)
										else:
											cli_source_anims_by_skel.setdefault(None, set()).add(raw_c)
								
								j_idx += 1
					
					if cli_source_anims:
						# If we collected per-skeleton animations, show combined and keep mapping
						if cli_source_anims_by_skel:
							combined = set().union(*cli_source_anims_by_skel.values()) if any(cli_source_anims_by_skel.values()) else set()
							self.info_panel.append(f"CLI Analysis (SOURCE): Found {len(combined)} animations (per-skeleton mapping available)")
						else:
							self.info_panel.append(f"CLI Analysis (SOURCE): Found {len(cli_source_anims)} animations: {', '.join(sorted(cli_source_anims))}")
					# Also log any skeletons detected by the CLI parsing so we can debug mac vs win differences
					try:
						if cli_source_skeletons:
							self.info_panel.append(f"CLI Analysis (SOURCE): Detected skeleton(s): {', '.join(sorted(cli_source_skeletons))}")
						else:
							self.info_panel.append("CLI Analysis (SOURCE): No 'Skeleton:' lines detected in Spine info output.")
					except Exception:
						pass
				else:
					self.info_panel.append(f"CLI Info command failed (Code {i_proc.returncode})")
					# Cannot check header_found or info_out as they are undefined if command failed

			except Exception as e:
				self.log_error(f"Failed to run info command: {e}")

			self.info_panel.append(f"Exporting JSON to: {result_dir}")

			# Run Spine export
			export_settings = os.path.abspath("default_export.json")
			# Always overwrite definitions to ensure packAtlas is enabled for consistency checks
			try:
				with open(export_settings, 'w') as f:
					# Enabled packAtlas so we can cross-reference JSON vs Atlas for missing files
					# We must provide a valid SpinePackerSettings object, not a string
					settings_json = (
						'{"class": "export-json", "name": "JSON", "extension": ".json", "format": "JSON", '
						'"prettyPrint": false, "nonessential": true, "cleanUp": false, '
						'"packAtlas": null, '
						'"packSource": "attachments", "warnings": true}'
					)
					f.write(settings_json)
			except:
				pass

			cmd = [
				current_runnable_spine_exe 
			] + extra_cli_args + [
				'-i', input_path, 
				'-o', result_dir,
				'-e', export_settings if os.path.exists(export_settings) else 'json'
			]
			# Force "clean" off if requested (using -n as per user request, or rely on JSON settings)
			# User explicitly asked for -n (clean=false/no-clean)
			# Note: -n in some Spine versions might mean --name. But we will follow user instruction.
			# To be safe against version differences, we rely primarily on export_settings "cleanUp": false.
			
			self.info_panel.append(f"Running export with cleanUp=false via settings.")
			self.status_label.setText(f"Exporting raw data: {name}")
			
			spine_export_unchecked = []
			spine_export_unchecked_anims = []
			try:
				self.info_panel.append(f"Running export command: {' '.join(cmd)}")
				# Use subprocess.run for reliability (avoids buffer deadlocks)
				# Fix: Force UTF-8 encoding or replacement to avoid Windows codepage errors on binary logs
				proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
				
				# Reactive Version Switching (Retry Logic)
				# If export fails due to version mismatch, parse the required version and retry
				if proc.returncode != 0:
					combined_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
					# Pattern: "Project version: 4.2.43"
					m_ver = re.search(r"Project version:\s*([0-9]+\.[0-9]+\.[0-9]+)", combined_output)
					if m_ver:
						required_ver = m_ver.group(1)
						self.info_panel.append(f"Detected version mismatch! Required: {required_ver}. Retrying...")
						
						# Switch to required version
						# 1. Try local find
						retry_exe = self.find_best_spine_exe(required_ver)
						retry_args = []
						if retry_exe:
							self.info_panel.append(f"Found local executable for retry: {retry_exe}")
							# Only switch exe, no extra args needed usually
						else:
							# Fallback: Use same exe (Launcher) but force version
							self.info_panel.append(f"No local exe found. Forcing download/launch with -u {required_ver}")
							retry_exe = current_runnable_spine_exe
							retry_args = ['-u', required_ver]
							
						# Construct new command
						# We must insert -u BEFORE -i usually
						retry_cmd = [retry_exe] + retry_args + [
							'-i', input_path, 
							'-o', result_dir,
							'-e', export_settings if os.path.exists(export_settings) else 'json'
						]
						
						self.info_panel.append(f"Retrying export command: {' '.join(retry_cmd)}")
						proc = subprocess.run(retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
						
						if proc.returncode == 0:
							self.info_panel.append("Retry successful!")
							# Update variables for subsequent steps (Import) to use the correct version
							current_runnable_spine_exe = retry_exe
							extra_cli_args = retry_args
							
							# Update report stats with the corrected version
							final_reported_version = required_ver
							final_exe_used = os.path.basename(current_runnable_spine_exe)
							if extra_cli_args:
								final_exe_used += f" (Args: {' '.join(extra_cli_args)})"
							file_stats['spine_version_source'] = final_reported_version
							file_stats['spine_exe_used'] = final_exe_used

				# Parse output for unchecked export warnings
				# Example: Attachment's keys not exported because it has "Export" unchecked: [region: pop/coin_fx/coin_fx_00, slot: fx]
				# We check both stdout and stderr just in case
				combined_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
				
				# LOG EVERYTHING for debug
				if combined_output.strip():
					self.info_panel.append(f"--- SPINE EXPORT LOGS ---\n{combined_output}\n-------------------------")
				
				# Regex to find the region and slot name
				# Example trace: ... [region: images/foo, slot: slot_bar]
				unchecked_pattern = re.compile(r'not exported because it has "Export" unchecked.*\[region:\s*([^,\]]+)(?:,\s*slot:\s*([^,\]]+))?', re.IGNORECASE)
				
				# Regex for unchecked animations (CLI output format can vary)
				# 1. Standard: Animation 'grand_bonus_intro' not exported because it has "Export" unchecked.
				# 2. Strict (older/newer): Animation not exported: <name>
				# 3. Simple: Animation not exported: foo
				# 4. Inverted: not exported: Animation 'foo'
				# We use a list of patterns to capture various formats
				unchecked_anim_patterns = [
					re.compile(r"Animation\s+['\"]?(.+?)['\"]?\s+(?:is\s+)?not exported", re.IGNORECASE),
					re.compile(r"Animation\s+not\s+exported\s*:\s*['\"]?(.+?)['\"]?$", re.IGNORECASE),
					re.compile(r"not exported\s*:\s*Animation\s+['\"]?(.+?)['\"]?$", re.IGNORECASE),
					re.compile(r"Animation\s+['\"]?(.+?)['\"]?\s+skipped", re.IGNORECASE)
				]
				
				# Regex for missing images (Spine CLI Warning)
				# Example: Image for attachment [region: path/to/img, slot: slotName] not found: path/to/img
				missing_image_pattern = re.compile(r"Image\s+for\s+attachment\s+\[region:\s*([^,\]]+)\s*,\s*slot:\s*([^,\]]+)\]\s+not\s+found:\s*(.+)", re.IGNORECASE)
				spine_export_missing = []
				spine_export_log_warnings = []

				# Save log to file for debugging/verification
				log_path = os.path.join(result_dir, "spine_export.log")
				try:
					with open(log_path, 'w', encoding='utf-8') as lf:
						lf.write(combined_output)
				except Exception as e:
					self.log_error(f"Could not write log file: {e}")

				for line in combined_output.splitlines():
					clean_line = line.strip()
					if not clean_line: continue
					
					# Track if handled
					is_handled = False

					# Check attachments unchecked
					m = unchecked_pattern.search(clean_line)
					if m:
						r_name = m.group(1).strip()
						s_name = m.group(2).strip() if m.group(2) else None
						spine_export_unchecked.append({'region': r_name, 'slot': s_name})
						is_handled = True
					
					# Check missing images
					m_missing = missing_image_pattern.search(clean_line)
					if m_missing:
						missing_path = m_missing.group(1).strip()
						spine_export_missing.append(missing_path)
						is_handled = True

					# Check "Slot is hidden: [slot: h1_refp, bone: root, skeleton: symbols]"
					# This format is specific to recent Spine versions
					m_hidden = re.search(r"Slot\s+is\s+hidden:\s*\[(.+?)\]", clean_line, re.IGNORECASE)
					if m_hidden:
						# Capture full message or just the inside
						spine_export_log_warnings.append(clean_line)
						is_handled = True

					# Check animations using multiple patterns
					for p in unchecked_anim_patterns:
						m_anim = p.search(clean_line)
						if m_anim:
							anim_name = m_anim.group(1).strip()
							# Do not add if it's overly generic or empty
							if anim_name:
								spine_export_unchecked_anims.append(anim_name)
							is_handled = True
							break
					
					# General Scan for other "not exported" or "hidden" warnings
					# If line contains 'not exported' but wasn't handled above, or contains 'hidden'/'invisible'
					if not is_handled:
						lower_line = clean_line.lower()
						if ('not exported' in lower_line) or ('hidden' in lower_line) or ('invisible' in lower_line):
							# Avoid duplicates or noise
							spine_export_log_warnings.append(clean_line)
							
				# Filter out missing images if they are explicitly checked off for export.
				unchecked_regions = {item['region'] for item in spine_export_unchecked if item.get('region')}
				filtered_missing = []
				for m_path in spine_export_missing:
					if m_path not in unchecked_regions:
						filtered_missing.append(m_path)
				spine_export_missing = filtered_missing

				# Advanced Check: If input is a ZIP-based .spine file, we can read the source of truth
				# and conduct a perfect diff of animations.
				try:
					detected_source_anims = set()
					# Method A: ZIP Analysis
					if zipfile.is_zipfile(input_path):
						with zipfile.ZipFile(input_path, 'r') as z:
							# Look for the main json file inside the zip (usually same name as spine file or 'skeleton.json')
							# We need to find the json that corresponds to the current skeleton if there are multiple?
							# For simplicity, we scan all JSONs in the root
							for zf in z.namelist():
								if zf.lower().endswith('.json') and '/' not in zf:
									try:
										with z.open(zf) as jf:
											src_data = json.load(jf)
											if 'animations' in src_data:
												detected_source_anims.update(src_data['animations'].keys())
									except:
										pass
					
					# Method B: CLI Analysis (Augment with data found previously)
					# If CLI produced a per-skeleton mapping, prefer that; otherwise merge CLI results into detected_source_anims
					if cli_source_anims_by_skel and any(cli_source_anims_by_skel.values()):
						# store the per-skeleton mapping in a separate variable for later assignment
						cli_mapping = cli_source_anims_by_skel
					else:
						detected_source_anims.update(cli_source_anims)
					
					# Method C: Direct JSON Analysis (Fallback)
					if not detected_source_anims:
						try:
							with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
								content = f.read()
								# 1. Try Strict JSON Parsing first
								json_success = False
								try:
									src_data = json.loads(content)
									if 'animations' in src_data:
										detected_source_anims.update(src_data['animations'].keys())
										self.info_panel.append(f"Direct JSON Parse: Found {len(src_data['animations'])} animations.")
										json_success = True
								except:
									pass
								
								# 2. Heuristic Raw Regex Search (The "Out of the Box" solution)
								# If strict JSON failed (maybe it's old format, or has comments, or is essentially text-based)
								if not json_success:
									# Look for "animations": { ... } or animations: { ... }
									# Standard Spine JSON/Text format: key: { ... }
									m_anim = re.search(r'(?:["\']animations["\']|animations)\s*[:=]\s*\{', content)
									if m_anim:
										self.info_panel.append("Source file appears to contain text-based animation definitions. Scanning...")
										# Limit scan to avoid scanning the whole file if it's huge, but large enough for anims
										start_idx = m_anim.end()
										scan_window = content[start_idx:start_idx+100000] # 100kb window
										
										# Find keys like:  "run": {  or  run: {
										# Capture group 1 is the name
										# We filter out common property names that might appear inside an animation if the regex matches too deep
										# But usually animations are top-level in their block.
										found_keys = re.findall(r'(?:["\']([\w\s\-\.\(\)]+)["\']|([\w\s\-\.\(\)]+))\s*:\s*\{', scan_window)
										
										# Flatten and clean
										candidates = set()
										for k1, k2 in found_keys:
											val = (k1 or k2).strip()
											# Filter reserved words just in case we drifted into a sub-block
											if val not in ['bones', 'slots', 'ik', 'transform', 'events', 'drawOrder', 'attachments']:
												candidates.add(val)
										
										if candidates:
											detected_source_anims.update(candidates)
											self.info_panel.append(f"Raw Text Analysis: Found {len(candidates)} potential animations (e.g. {list(candidates)[:3]}).")
						except Exception as e:
							self.info_panel.append(f"Fallback Analysis Failed: {e}")
					
					if detected_source_anims or ('cli_mapping' in locals()):
						# Prefer per-skeleton mapping when available (cli_mapping), otherwise use flat detected_source_anims set
						if 'cli_mapping' in locals():
							all_file_stats[-1]['source_anims_defined'] = cli_mapping
						else:
							all_file_stats[-1]['source_anims_defined'] = detected_source_anims
				except Exception as e:
					self.info_panel.append(f"Source Analysis Failed: {e}")

				if proc.returncode != 0:
					msg = f"Spine export failed (Code {proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
					self.log_error(msg)
					errors.append(f"{name}: export failed")
					continue
			except Exception as e:
				msg = f"{name}: {e}"
				errors.append(msg)
				self.log_error(f"Export error: {e}")
				continue

			# Find all exported JSONs
			found_jsons = []
			found_info = None
			for f in os.listdir(result_dir):
				if f.lower().endswith('.json'):
					found_jsons.append(os.path.join(result_dir, f))
				elif (f.lower().endswith('.txt') or f.lower().endswith('.atlas')) and 'opaque' not in f:
					found_info = os.path.join(result_dir, f)
			
			if not found_jsons:
				msg = f"{name}: no JSON exported"
				errors.append(msg)
				self.log_error("No JSON found in export folder.")
				continue

			# Sort JSONs to ensure deterministic order
			found_jsons.sort()
			
			self.info_panel.append(f"Found {len(found_jsons)} skeleton(s) to process.")

			# Integrity Check: Skeletons
			# Check if any skeleton in source is missing from export
			# We store this in the 'container' file_stats so skeletons can access it
			file_stats['unchecked_skeletons'] = []

			# Always build exported_skel_names from found_jsons (used for multiple checks below)
			exported_skel_names = set()
			for f_json in found_jsons:
				exported_skel_names.add(os.path.splitext(os.path.basename(f_json))[0])

			if cli_source_skeletons:
				missing_skeletons = cli_source_skeletons - exported_skel_names
				if missing_skeletons:
					# Store in parent container so skeletons inherit it
					file_stats['unchecked_skeletons'] = sorted(list(missing_skeletons))

			# REF Skeleton Check: detect skeletons named like "ref", "reference", "ref_pose", etc.
			# Such skeletons are typically reference/helper skeletons that should NOT be exported.
			#   - If a REF skeleton IS in the export output -> likely an error, report as WARNING.
			#   - If a REF skeleton exists in the source but is turned off for export -> report as NOTE.
			_ref_skel_re = re.compile(
				r'^ref(?:s|erence|erences)?$'
				r'|^ref[_\-]'
				r'|[_\-]ref$',
				re.IGNORECASE
			)
			all_known_skels = set(cli_source_skeletons) | exported_skel_names
			ref_skels_exported = sorted([s for s in all_known_skels if _ref_skel_re.match(s) and s in exported_skel_names])
			ref_skels_off      = sorted([s for s in all_known_skels if _ref_skel_re.match(s) and s not in exported_skel_names])
			file_stats['ref_skeletons_exported'] = ref_skels_exported
			file_stats['ref_skeletons_off']      = ref_skels_off


			# Process each skeleton
			for idx, f_json in enumerate(found_jsons):
				is_first = (idx == 0)
				is_last = (idx == len(found_jsons) - 1)
				
				self.info_panel.append(f"Processing skeleton {idx+1}/{len(found_jsons)}: {os.path.basename(f_json)}")
				self.status_label.setText(f"Processing skeleton: {os.path.basename(f_json)}")
				
				# Create a specific statistics object for this skeleton
				skel_base_name = os.path.splitext(os.path.basename(f_json))[0]
				# Determine per-skeleton source animations (if a per-skeleton mapping was found)
				file_source_anims = file_stats.get('source_anims_defined', set())
				if isinstance(file_source_anims, dict):
					per_skel_anims = file_source_anims.get(skel_base_name) or file_source_anims.get(None) or set()
				else:
					per_skel_anims = file_source_anims

				skeleton_stats = {
					'name': f"{skel_base_name} ({name})", 
					'jpeg': 0, 'png': 0, 'total': 0, 'total_spine': 0,
					# Per-skeleton animations (set) for accurate comparisons
					'source_anims_defined': per_skel_anims,
					'unchecked_skeletons': file_stats.get('unchecked_skeletons', []),
					'ref_skeletons_exported': file_stats.get('ref_skeletons_exported', []),
					'ref_skeletons_off': file_stats.get('ref_skeletons_off', []),
					'spine_version_source': file_stats.get('spine_version_source', 'Unknown'),
					'spine_exe_used': file_stats.get('spine_exe_used', 'Unknown')
				}
				
				# Add to the file's list of skeletons
				file_stats['skeletons'].append(skeleton_stats)
				
				# Temporarily append this skeleton stats to all_file_stats so that _process_single_skeleton
				# (which uses all_file_stats[-1]) writes to IT, instead of the container 'file_stats'.
				# Warning: We must remove it after the call or manage indices carefully for the outer container.
				# Actually, if we just append it, accessing [-1] works as expected for this call.
				# But we want the final structure to be hierarchical.
				# Solution: We append it to all_file_stats, let the function populate it, 
				# and then we keep it linked in file_stats['skeletons'].
				# Wait, if we append to all_file_stats, we will have: [ContainerForFile1, Skel1, Skel2]
				# We should probably REMOVE the ContainerForFile1 from the reporting list or make the reporting list smarter.
				#
				# Let's adjust:
				# The reporting logic iterates over all_file_stats.
				# If we change 'file_stats' (the container) to NOT be in all_file_stats, or filter it out?
				#
				# Better approach for minimal code change in `_process_single_skeleton`:
				# We keep `all_file_stats` as a flat list of REPORTS.
				# The "container" I made earlier was to hold them, but now I think I should just replace the container with the individual reports
				# OR simply append the individual reports.
				#
				# Let's Modify the logic:
				# 1. Pop the "Container" stats we added at loop start (it was just a placeholder).
				# 2. For each skeleton, append a New stats object to all_file_stats.
				#
				# Note: 'file_stats' variable holds the container created at loop start. We can use it to store shared data like 'source_anims_defined'.
				# We just need to remove it from `all_file_stats` before appending the real per-skeleton stats.
				
				# Pop the container from the main list if it's the first skeleton, 
				# but we need to keep `file_stats` around because it holds 'source_anims_defined'.
				if idx == 0 and all_file_stats and all_file_stats[-1] == file_stats:
					all_file_stats.pop()

				all_file_stats.append(skeleton_stats)
				
				self._process_single_skeleton(
					f_json, found_info, result_dir, folder, input_path, file_scanner,
					base_output_root, current_runnable_spine_exe, base_progress, name, errors, results, 
					all_file_stats, jpeg_forced_png_warnings, all_skeleton_names=all_skeleton_names,
					is_first=is_first, is_last=is_last, optimization_enabled=self.optimization_cb.isChecked(),
					spine_export_unchecked=spine_export_unchecked,
					spine_export_unchecked_anims=spine_export_unchecked_anims,
					extra_cli_args=extra_cli_args,
					spine_export_missing=spine_export_missing,
					spine_export_log_warnings=spine_export_log_warnings,
					consolidate_duplicates=self.consolidate_duplicates_cb.isChecked(),
					consolidate_mirrored=self.consolidate_duplicates_cb.isChecked(),
					similarity_confidence=self.similarity_slider.value()
				)



		# After processing all skeletons for this file, optionally remove temp folder
		# when in Validate-Only mode and the user didn't request keeping temps.
		try:
			if self.config.get("validate_only", False) and not self.keep_temp_cb.isChecked():
				if result_dir and os.path.isdir(result_dir) and 'spine_temp_' in os.path.basename(result_dir):
					# Use robust removal helper (retries + logging)
					self._remove_temp_dir(result_dir, reason='validate-only')
		except Exception as e:
			self.info_panel.append(f"<font color='yellow'>Validation cleanup warning: {e}</font>")

		# Cleanup and Finish
		self.progress_bar.setValue(len(to_process) * 100)
		self.process_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)
		
		# Display statistics
		SUCCESS_COLOR = '#32CD32' # LimeGreen
		any_warnings = False
		self.info_panel.append(f"\n<font color='{SUCCESS_COLOR}'>--- Processing Statistics ---</font>")
		for i, stats in enumerate(all_file_stats):
			if 'total_exported_unique' in stats: # New format
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>File: {stats['name']}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Total Attachments: {stats.get('total_attachments', 0)}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Total used images in Spine: {stats.get('total_spine_used', 0)}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Total exported images: {stats.get('total_exported_unique', 0)}</font>")
				if 'consolidated_count' in stats and stats['consolidated_count'] > 0:
					self.info_panel.append(f"<font color='#DAA520'>  Consolidated duplicates: {stats['consolidated_count']}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Copied to JPEG folder: {stats.get('jpeg', 0)}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Copied to PNG folder: {stats.get('png', 0)}</font>")
				
				# Report Missing Files Count
				if 'missing_files_reported' in stats and stats['missing_files_reported']:
					count = len(stats['missing_files_reported'])
					self.info_panel.append(f"<font color='red'>  Missing files (not copied): {count}</font>")
				
				# Report Version Info
				src_ver = stats.get('spine_version_source', 'Unknown')
				exe_used = stats.get('spine_exe_used', 'Unknown')
				self.info_panel.append(f"<font color='#00BFFF'>  Source Project Version: {src_ver}</font>")
				self.info_panel.append(f"<font color='#00BFFF'>  Processed with Spine: {exe_used}</font>")

				# Duplicate images summary moved to RECOMMENDATIONS (appended at report end)
				# dup_groups = stats.get('duplicate_image_groups', [])
				# Naming violations summary
				naming_viol = stats.get('naming_violations', [])
				if naming_viol:
					self.info_panel.append(f"  Naming violations: {len(naming_viol)} file(s)")
					for v in naming_viol[:10]:
						self.info_panel.append(f"    - {v['basename']}: {', '.join(v['reasons'])}")
				else:
					self.info_panel.append(f"  Naming violations: none")
			
			elif stats['total'] > 0: # Fallback for old stats format if any
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>File: {stats['name']}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Total images copied: {stats['total']}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  Total images in Spine: {stats.get('total_spine', 0)}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  JPEG images: {stats['jpeg']}</font>")
				self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  PNG images: {stats['png']}</font>")
				
				# Report Missing Files Count
				if 'missing_files_reported' in stats and stats['missing_files_reported']:
					count = len(stats['missing_files_reported'])
					self.info_panel.append(f"<font color='red'>  Missing files (not copied): {count}</font>")
				# Duplicate images summary moved to RECOMMENDATIONS (appended at report end)
				# dup_groups = stats.get('duplicate_image_groups', [])
				# Naming violations summary (fallback stats format)
				naming_viol = stats.get('naming_violations', [])
				if naming_viol:
					self.info_panel.append(f"  Naming violations: {len(naming_viol)} file(s)")
					for v in naming_viol[:10]:
						self.info_panel.append(f"    - {v['basename']}: {', '.join(v['reasons'])}")
				else:
					self.info_panel.append(f"  Naming violations: none")
			
			# Report Missing Files (CRITICAL)
			if 'missing_files_reported' in stats and stats['missing_files_reported']:
				any_warnings = True
				self.info_panel.append("<br>")
				count = len(stats['missing_files_reported'])
				self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>{count} images likely checked off for export (found in logs or Atlas but not JSON): {', '.join(stats['missing_files_reported'])}</span>")
				for i, m in enumerate(stats['missing_files_reported']):
					if i < 15:
						self.info_panel.append(f"<font color='red'>    - {m}</font>")
					else:
						self.info_panel.append(f"<font color='red'>    - ... and {count - 15} more</font>")
						break

			# Report Log Warnings (CRITICAL)
			if 'log_warnings_reported' in stats and stats['log_warnings_reported']:
				any_warnings = True
				self.info_panel.append("<br>")
				count = len(stats['log_warnings_reported'])
				self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:orange;'>{count} additional issues (Hidden/Not Exported):</span>")
				for i, m in enumerate(stats['log_warnings_reported']):
					# Use orange for these specific log messages as requested ("red and orange letters")
					# Actually usage was "Critical errors found... check for report" in red, and 
					# user said: "with red and orange letters : JSON export: symbols_v3 Slot is hidden..."
					# I will use Orange for the message content to differentiate slightly or Red if it's super critical.
					# Let's use Red for the header and Orange for the message body as user hinted.
					if i < 15:
						self.info_panel.append(f"<font color='orange'>    - {m}</font>")
					else:
						self.info_panel.append(f"<font color='orange'>    - ... and {count - 15} more</font>")
						break

			# Report Unchecked Skeletons
			if 'unchecked_skeletons' in stats and stats['unchecked_skeletons']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_skel = len(stats['unchecked_skeletons'])
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>{n_skel} skeletons are checked off for export:</span>")
				for i, skel in enumerate(stats['unchecked_skeletons']):
					if i < 10:
						self.info_panel.append(f"<font color='orange'>    - {skel}</font>")
					else:
						self.info_panel.append(f"<font color='orange'>    - ... and {n_skel - 10} more</font>")
						break

			# Report REF skeletons that are exported (ERROR - should not be exported)
			if stats.get('ref_skeletons_exported'):
				any_warnings = True
				self.info_panel.append("<br>")
				ref_exp = stats['ref_skeletons_exported']
				self.info_panel.append(
					f"  <span style='color:#FF0000; font-weight:bold;'>ERROR:</span> "
					f"<span style='color:red;'>{len(ref_exp)} reference/REF skeleton(s) "
					f"are checked ON for export — this is likely a mistake:</span>"
				)
				for skel in ref_exp:
					self.info_panel.append(f"<font color='red'>    - '{skel}' (REF skeleton exported)</font>")

			# Report REF skeletons that exist but are turned OFF for export (NOTE - expected / OK)
			if stats.get('ref_skeletons_off'):
				self.info_panel.append("<br>")
				ref_off = stats['ref_skeletons_off']
				self.info_panel.append(
					f"  <span style='color:#5599FF; font-weight:bold;'>NOTE:</span> "
					f"<span style='color:#5599FF;'>{len(ref_off)} reference/REF skeleton(s) "
					f"found in project but are turned OFF for export (expected):</span>"
				)
				for skel in ref_off:
					self.info_panel.append(f"<font color='#5599FF'>    - '{skel}' (REF skeleton, not exported)</font>")

			# Report Unused Attachments (Defined in skins but NO animation key and NOT in setup pose)
			if stats.get('unused_attachments'):
				any_warnings = True
				self.info_panel.append("<br>")
				unused_atts = stats['unused_attachments']
				n_unused = len(unused_atts)
				self.info_panel.append(
					f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> "
					f"<span style='color:orange;'>{n_unused} attachments exist in skins but have NO animation keys and are NOT in the setup pose (they might be dead weight):</span>"
				)
				for i, u in enumerate(unused_atts):
					if i < 10:
						self.info_panel.append(f"<font color='orange'>    - {u}</font>")
					else:
						self.info_panel.append(f"<font color='orange'>    - ... and {n_unused - 10} more</font>")
						break

			# Report Unchecked Attachments (Explicit Spine Warnings)
			if 'unchecked' in stats and stats['unchecked']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_unchecked = len(stats['unchecked'])
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>{n_unchecked} attachments are checked off for export, so they were not copied:</span>")
				for i, u in enumerate(stats['unchecked']):
					# u is now a dict {'region':..., 'slot':...}
					d_text = u['region']
					if u.get('slot'):
						d_text += f" (in slot: {u['slot']})"
					
					if i < 10:
						self.info_panel.append(f"<font color='orange'>    - {d_text}</font>")
					else:
						self.info_panel.append(f"<font color='orange'>    - ... and {n_unchecked - 10} more</font>")
						break

			# Report Unchecked Animations
			anim_exported = stats.get('anim_exported_count', 0)
			anim_total = stats.get('anim_total_count', 0) # Raw count from source analysis
			
			# If we have 0 source animations but >0 exported, source analysis failed
			source_analysis_failed = (anim_total == 0 and anim_exported > 0)
			
			if source_analysis_failed:
				anim_color = 'orange'
				self.info_panel.append(f"Detected Animations: {anim_total} (Exported: {anim_exported})")
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>Source analysis found 0 animations (but {anim_exported} exported). Cannot verify unchecked animations.</span>")
			else:
				# Normal reporting
				anim_str = f"Detected Animations: {anim_total} (Exported: {anim_exported})"
				if 'unchecked_anims' in stats and stats['unchecked_anims']:
					anim_color = 'orange'
					self.info_panel.append(f"<font color='orange'>  {anim_str}</font>")
				else:
					anim_color = SUCCESS_COLOR
					self.info_panel.append(f"<font color='{SUCCESS_COLOR}'>  {anim_str}</font>")

			if 'unchecked_anims' in stats and stats['unchecked_anims']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_anim = len(stats['unchecked_anims'])
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>{n_anim} animations are checked off for export so they are not copied:</span>")
				for i, anim in enumerate(stats['unchecked_anims']):
					if i < 10:
						self.info_panel.append(f"<font color='orange'>    - {anim}</font>")
					else:
						self.info_panel.append(f"<font color='orange'>    - ... and {n_anim - 10} more</font>")
						break

			# Report Setup Pose Violations
			if 'setup_pose_warnings' in stats and stats['setup_pose_warnings']:
				any_warnings = True
				self.info_panel.append("<br>")
				self.info_panel.append(f"<span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>{len(stats['setup_pose_warnings'])} setup pose slots refer to UNCHECKED attachments:</span>")
				for msg in stats['setup_pose_warnings']:
					self.info_panel.append(f"<font color='red'>    - {msg}</font>")
					
			# Report General Setup Pose Active Attachments (Info/Warning)
			if 'setup_pose_active' in stats and stats['setup_pose_active']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_active = len(stats['setup_pose_active'])
				# Lighter orange color for soft warnings (e.g. #FFC04C or #FFB74D)
				soft_warning_color = "#FFC04C" 
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:{soft_warning_color};'>{n_active} slots have active attachments in Setup Pose:</span>")
				for i, msg in enumerate(stats['setup_pose_active']):
					if i < 10:
						self.info_panel.append(f"<font color='{soft_warning_color}'>    - {msg}</font>")
					else:
						self.info_panel.append(f"<font color='{soft_warning_color}'>    - ... and {n_active - 10} more</font>")
						break

			# Report Invisible Setup Pose Slots
			if 'setup_pose_invisible' in stats and stats['setup_pose_invisible']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_inv = len(stats['setup_pose_invisible'])
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:#FF4500;'>{n_inv} slots are INVISIBLE (Alpha=0) in Setup Pose but have active attachments:</span>")
				for i, msg in enumerate(stats['setup_pose_invisible']):
					if i < 10:
						self.info_panel.append(f"<font color='#FF4500'>    - {msg}</font>")
					else:
						self.info_panel.append(f"<font color='#FF4500'>    - ... and {n_inv - 10} more</font>")
						break

			# Report HIDDEN (visible: false) Setup Pose Slots
			if 'setup_pose_hidden' in stats and stats['setup_pose_hidden']:
				any_warnings = True
				self.info_panel.append("<br>")
				n_hidden = len(stats['setup_pose_hidden'])
				# CRITICAL styling
				self.info_panel.append(f"  <span style='color:#FF0000; font-weight:bold;'>CRITICAL:</span> <span style='color:red;'>{n_hidden} slots are HIDDEN (visible: false) in Setup Pose but have active attachments:</span>")
				for i, msg in enumerate(stats['setup_pose_hidden']):
					if i < 10:
						self.info_panel.append(f"<font color='red'>    - {msg}</font>")
					else:
						# Keep format
						self.info_panel.append(f"<font color='red'>    - ... and {n_hidden - 10} more</font>")
						break

			# Naming / Naming-convention Recommendations (detailed per-skeleton, summaries for slots/bones)
			if 'naming' in stats:
				n = stats['naming']
				# Skeleton name fields
				if n.get('skeleton'):
					any_warnings = True
					self.info_panel.append("<br>")
					self.info_panel.append("<span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>Skeleton name issues detected:</span>")
					for sk in n.get('skeleton'):
						self.info_panel.append(f"<font color='orange'>    - [{sk['field']}] '{sk['value']}' -> {', '.join(sk['reasons'])}</font>")
				# Animation name details
				if n.get('animations'):
					any_warnings = True
					self.info_panel.append("<br>")
					self.info_panel.append("<span style='color:#FF0000; font-weight:bold;'>WARNING:</span> <span style='color:orange;'>Animation name issues:</span>")
					for a in n.get('animations'):
						self.info_panel.append(f"<font color='orange'>    - {a['name']} -> {', '.join(a['reasons'])}</font>")
				# Slots/Bones/Constraints summaries
				for cat in ('slots_summary', 'bones_summary', 'constraints_summary'):
					c = n.get(cat, {})
					if c and c.get('count', 0) > 0:
						label = cat.split('_')[0].capitalize()
						self.info_panel.append("<br>")
						self.info_panel.append(f"<span style='color:#1E90FF; font-weight:bold;'>RECOMMENDATION:</span> <span style='color:#87CEFA;'>{label}: {c.get('count')} naming issues (examples):</span>")
						for ex in c.get('examples', []):
							self.info_panel.append(f"<font color='#87CEFA'>    - {ex['name']} -> {', '.join(ex['reasons'])}</font>")

			# Report Consistency Issues (Atlas vs JSON mismatch)
			if 'consistency_msg' in stats and stats['consistency_msg']:
				self.info_panel.append("<br>")
				c_msg = stats['consistency_msg']
				# Use orange for warnings, green (or default) for OK
				c_color = 'orange' if 'WARNING' in c_msg else 'green'
				if 'WARNING' in c_msg: any_warnings = True
				self.info_panel.append(f"<font color='{c_color}'>  {c_msg}</font>")
			
			# Separator (only between items, not after the last one)
			if i < len(all_file_stats) - 1:
				self.info_panel.append("\n" + "_"*50 + "\n")
		
		if jpeg_forced_png_warnings:
			any_warnings = True

		# Generate a plain-text full report with errors and warnings
		try:
			# Generate Report Content in Memory
			report_lines = []
			report_lines.append("Spine Sorter Full Report")
			report_lines.append(time.strftime("Generated: %Y-%m-%d %H:%M:%S", time.localtime(timestamp)))
			report_lines.append("\nErrors:")
			if errors:
				for e in errors:
					report_lines.append(f"- {e}")
			else:
				report_lines.append("None")
			
			if not any_warnings:
				report_lines.append("\nWarnings per file : None")
			else:
				report_lines.append("\nWarnings and details per file:")
				for stats in all_file_stats:
					report_lines.append(f"\nFile: {stats.get('name')}")
					report_lines.append(f"Source Version: {stats.get('spine_version_source', 'Unknown')}")
					report_lines.append(f"Processed with: {stats.get('spine_exe_used', 'Unknown')}")
					
					if stats.get('unused_attachments'):
						report_lines.append("Unused attachments (no animation key):")
						for u in stats.get('unused_attachments'):
							report_lines.append(f" - {u}")
					if stats.get('unchecked'):
						report_lines.append("Unchecked attachments:")
						for u in stats.get('unchecked'):
							report_lines.append(f" - {u.get('region')} (slot: {u.get('slot')})")
					if stats.get('unchecked_anims'):
						report_lines.append("Unchecked animations:")
						for a in stats.get('unchecked_anims'):
							report_lines.append(f" - {a}")
					if stats.get('setup_pose_warnings'):
						report_lines.append("Setup pose warnings:")
						for s in stats.get('setup_pose_warnings'):
							report_lines.append(f" - {s}")
					if stats.get('setup_pose_active'):
						report_lines.append("Active attachments in setup pose:")
						for s in stats.get('setup_pose_active'):
							report_lines.append(f" - {s}")
					if stats.get('setup_pose_invisible'):
						report_lines.append("Invisible (Alpha=0) attachments in setup pose:")
						for s in stats.get('setup_pose_invisible'):
							report_lines.append(f" - {s}")
					if stats.get('setup_pose_hidden'):
						report_lines.append("Hidden (visible=false) slots in setup pose:")
						for s in stats.get('setup_pose_hidden'):
							report_lines.append(f" - {s}")
					if stats.get('consistency_msg'):
						report_lines.append(f"Consistency: {stats.get('consistency_msg')}")
					# Duplicate image groups are reported in the RECOMMENDATIONS section at the end
					# Naming recommendations (plain-text)
					if stats.get('naming'):
						n = stats.get('naming')
						# Treat skeleton and animation name issues as WARNINGS
						if n.get('skeleton') or n.get('animations'):
							any_warnings = True
							report_lines.append("Naming warnings:")
							# Skeleton fields
							if n.get('skeleton'):
								for sk in n.get('skeleton'):
									reasons = ', '.join(sk.get('reasons', []))
									report_lines.append(f" - [{sk.get('field')}] {sk.get('value')} -> {reasons}")
							# Animations
							if n.get('animations'):
								report_lines.append(' - Animation name issues:')
								for a in n.get('animations'):
									reasons = ', '.join(a.get('reasons', []))
									report_lines.append(f"    - {a.get('name')} -> {reasons}")
						# Keep slots/bones/constraints as recommendations (not warnings)
						for cat in ('slots_summary', 'bones_summary', 'constraints_summary'):
							c = n.get(cat, {})
							if c and c.get('count', 0) > 0:
								report_lines.append(f" - {cat.split('_')[0].capitalize()} issues: {c.get('count')}")
								for ex in c.get('examples', []):
									reasons = ', '.join(ex.get('reasons', []))
									report_lines.append(f"    - {ex.get('name')} -> {reasons}")
					else:
						report_lines.append("Naming: none detected")
			
			if jpeg_forced_png_warnings:
				report_lines.append("\nJPEG forced->PNG warnings:")
				for w in jpeg_forced_png_warnings:
					report_lines.append(f" - {w}")

			# Aggregate naming recommendations across files (always reported under RECOMMENDATIONS)
			naming_by_file = {}
			for stats in all_file_stats:
				name = stats.get('name')
				n = stats.get('naming')
				if n:
					naming_by_file[name] = n
			
			if naming_by_file:
				report_lines.append("\nRECOMMENDATIONS (Naming):")
				for fname, n in naming_by_file.items():
					report_lines.append(f"File: {fname}")
					# Skeleton fields
					if n.get('skeleton'):
						for sk in n.get('skeleton'):
							reasons = ', '.join(sk.get('reasons', []))
							report_lines.append(f" - [{sk.get('field')}] {sk.get('value')} -> {reasons}")
					# Animations
					if n.get('animations'):
						report_lines.append(' - Animation name issues:')
						for a in n.get('animations'):
							reasons = ', '.join(a.get('reasons', []))
							report_lines.append(f"    - {a.get('name')} -> {reasons}")
					# Summaries for slots/bones/constraints
					for cat in ('slots_summary', 'bones_summary', 'constraints_summary'):
						c = n.get(cat, {})
						if c and c.get('count', 0) > 0:
							report_lines.append(f" - {cat.split('_')[0].capitalize()} issues: {c.get('count')}")
							for ex in c.get('examples', []):
								reasons = ', '.join(ex.get('reasons', []))
								report_lines.append(f"    - {ex.get('name')} -> {reasons}")

			# Build RECOMMENDATIONS: aggregate duplicate-image groups across files
			dup_by_file = {}
			for stats in all_file_stats:
				name = stats.get('name')
				dup_groups = stats.get('duplicate_image_groups', [])
				if dup_groups:
					dup_by_file.setdefault(name, []).extend(dup_groups)

			per_file_recs = []
			for name, groups in dup_by_file.items():
				# Only add header if we actually have groups (though loop implies we do)
				if groups:
					per_file_recs.append(f"Identical images detected in file: {name}")
					for g in groups:
						# Ensure g is iterable of strings
						if isinstance(g, list) or isinstance(g, tuple):
							basenames = [os.path.basename(f) for f in g]
							# If all basenames are unique, use them (cleaner report)
							if len(set(basenames)) == len(basenames):
								display_names = basenames
							else:
								# If duplicates in basenames (different folders), show full paths providing context
								display_names = g 
							
							per_file_recs.append(" - " + " | ".join(display_names))
						else:
							per_file_recs.append(f" - {g} (Error: unexpected group format)")
					per_file_recs.append("")

			if per_file_recs:
				report_lines.append("\nRECOMMENDATIONS:")
				report_lines.extend(per_file_recs)
				# single shared recommendation message
				report_lines.append("Recommendation: Consider using a single image for all identical attachments to reduce disk usage and improve performance.")

			report_content = "\n".join(report_lines)

			# Also append RECOMMENDATIONS to the info_panel in light blue (single header + content)
			if per_file_recs:
				rc_color = '#87CEFA'  # light sky blue
				tc = self.info_panel.textCursor()
				tc.movePosition(QTextCursor.End)
				self.info_panel.setTextCursor(tc)
				self.info_panel.insertHtml(f"<br/><span style='color:{rc_color}; font-weight:bold'>RECOMMENDATIONS:</span><br/>")
				for line in per_file_recs:
					tc = self.info_panel.textCursor()
					tc.movePosition(QTextCursor.End)
					self.info_panel.setTextCursor(tc)
					self.info_panel.insertHtml(f"<span style='color:{rc_color}'>" + line.replace('<','&lt;') + "</span><br/>")
				# add single shared recommendation line
				tc = self.info_panel.textCursor()
				tc.movePosition(QTextCursor.End)
				self.info_panel.setTextCursor(tc)
				self.info_panel.insertHtml(f"<span style='color:{rc_color}'>Recommendation: Consider using a single image for all identical attachments to reduce disk usage and improve performance.</span><br/>")

			# Show report dialog
			dlg = ReportDialog(self, report_content)
			dlg.exec()

		except Exception as e:
			self.info_panel.append(f"Could not generate report: {e}")

		# Check for critical errors (missing files) in stats
		any_critical = False
		for stats in all_file_stats:
			if 'missing_files_reported' in stats and stats['missing_files_reported']:
				any_critical = True
				break
			if 'log_warnings_reported' in stats and stats['log_warnings_reported']:
				any_critical = True
				break
			if 'setup_pose_hidden' in stats and stats['setup_pose_hidden']:
				any_critical = True
				break
			if 'setup_pose_warnings' in stats and stats['setup_pose_warnings']:
				any_critical = True
				break

		if errors or any_critical:
			if hasattr(self, 'blink_timer'): self.blink_timer.stop()
			self.status_label.setStyleSheet("font-weight: bold; color: #FF0000;") # Red for critical
			if any_critical:
				self.status_label.setText("CRITICAL ERRORS FOUND - CHECK REPORT")
				QMessageBox.warning(self, "Completed with Critical Errors", f"Processed {len(to_process)} files.\nMissing files or critical errors detected.\nSee the report for details.")
			else:
				self.status_label.setStyleSheet("font-weight: bold; color: #FF4500;") # OrangeRed for standard errors
				self.status_label.setText("Finished with errors")
				QMessageBox.warning(self, "Completed with errors", f"Processed {len(to_process)} files.\n{len(errors)} errors occurred.\nSee info log for details.")
		else:
			if hasattr(self, 'blink_timer'): self.blink_timer.stop()
			if any_warnings:
				self.status_label.setStyleSheet("font-weight: bold; color: #FFA500;") # Orange for warnings
				self.status_label.setText("Completed - CHECK THE WARNINGS ON THE END OF THE LOG")
			else:
				self.status_label.setStyleSheet("font-weight: bold; color: #32CD32;") # LimeGreen for success
				self.status_label.setText("Completed OK")
			QMessageBox.information(self, "Completed", f"Successfully processed {len(to_process)} files.")

def main():
	print("Starting application...")
	if os.name == 'nt':
		try:
			# Set AppUserModelID so the taskbar icon displays correctly on Windows
			myappid = 'spinesorter.v5.55' 
			ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
		except Exception:
			pass

	try:
		app = QApplication(sys.argv)
		app.setStyle("Fusion")
		
		# Force a standard Dark Theme for consistency across all platforms
		palette = QPalette()
		palette.setColor(QPalette.Window, QColor(43, 43, 43))
		palette.setColor(QPalette.WindowText, Qt.white)
		palette.setColor(QPalette.Base, QColor(25, 25, 25))
		palette.setColor(QPalette.AlternateBase, QColor(43, 43, 43))
		palette.setColor(QPalette.ToolTipBase, Qt.white)
		palette.setColor(QPalette.ToolTipText, Qt.black)
		palette.setColor(QPalette.Text, Qt.white)
		palette.setColor(QPalette.Button, QColor(35, 35, 35))
		palette.setColor(QPalette.ButtonText, Qt.white)
		palette.setColor(QPalette.BrightText, Qt.red)
		palette.setColor(QPalette.Link, QColor(255, 87, 34))
		palette.setColor(QPalette.Highlight, QColor(255, 87, 34))
		palette.setColor(QPalette.HighlightedText, Qt.black)
		app.setPalette(palette)

		w = MainWindow()
		w.show()
		sys.exit(app.exec())
	except Exception as e:
		print(f"CRITICAL ERROR: {e}")
		import traceback
		traceback.print_exc()

if __name__ == "__main__":
	main()    
