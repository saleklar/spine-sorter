#!/usr/bin/env python3
"""Spine sorter - minimal PySide6 UI

Provides:
- Hardcoded Spine EXE display (C:/Program Files/Spine/Spine.exe)
- Browse button to choose a folder containing .spine files
- Panel listing all .spine files in that folder
- Persistent config stored in the platform AppConfigLocation as JSON
"""
import sys
import os
import json
import subprocess
import time
import re
import ctypes
import zipfile
import io
import errno
# Default Spine JSON versions to populate the JSON-version combo
DEFAULT_VERSIONS = ["4.2.43", "4.3", "4.2", "4.1", "4.0", "3.8"]
try:
	from PIL import Image
except Exception:
	Image = None

# Import PySide6 with a friendly error if it's not installed
try:
	from PySide6.QtCore import QStandardPaths, Qt, QThread, Signal
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
	)
except ModuleNotFoundError:
	print("PySide6 is not installed. Install with: pip install PySide6")
	sys.exit(1)


class SpineScannerThread(QThread):
	versions_found = Signal(list)

	def __init__(self, config, default_spine_exe, parent=None):
		super().__init__(parent)
		self.config = config
		self.default_spine_exe = default_spine_exe

	def _get_file_version_windows(self, path):
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
		
		# Optimization: Check for version.txt in user home (standard Spine behavior)
		home = os.path.expanduser("~")
		candidates_txt = [
			os.path.join(os.path.dirname(exe), "version.txt"), # Local to exe
			os.path.join(home, "Spine", "version.txt"),        # Windows standard
			os.path.join(home, ".spine", "version.txt"),       # Linux standard
			os.path.join(home, "Library", "Application Support", "Spine", "version.txt"), # Mac standard
		]
		
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
		roots = [cfg_dir, r"C:\Program Files", r"C:\Program Files (x86)"]
		seen = set()
		
		# Find candidates
		for root in roots:
			if not root or not os.path.isdir(root):
				continue
			try:
				for name in os.listdir(root):
					if 'spine' in name.lower():
						exe = os.path.join(root, name, 'Spine.exe')
						if os.path.isfile(exe) and exe not in seen:
							candidates.append(exe); seen.add(exe)
			except Exception:
				pass
		
		# Also check root dirs
		for root in roots:
			try:
				exe = os.path.join(root, 'Spine.exe')
				if os.path.isfile(exe) and exe not in seen:
					candidates.append(exe); seen.add(exe)
			except Exception:
				pass

		# Process candidates
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
			
		# Ensure default is present if nothing found
		if not results and cfg:
			results.append((os.path.basename(cfg), cfg))
			
		self.versions_found.emit(results)


class ImageCache:
	def __init__(self, cache_path):
		self.cache_path = cache_path
		self.cache = {}
		self.load()

	def load(self):
		try:
			if os.path.exists(self.cache_path):
				with open(self.cache_path, 'r', encoding='utf-8') as f:
					self.cache = json.load(f)
		except Exception:
			self.cache = {}

	def save(self):
		try:
			with open(self.cache_path, 'w', encoding='utf-8') as f:
				json.dump(self.cache, f, indent=2)
		except Exception:
			pass

	def get(self, path):
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
	def __init__(self):
		self.cache = {} # dir_path -> list of (full_path, basename_lower)

	def scan(self, directory):
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
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Spine Sorter")

		# Configuration
		self.default_spine_exe = r"C:\Program Files\Spine\Spine.exe"
		self.config = {}
		self.config_path = self._make_config_path()
		self._load_config()
		
		self.image_cache = ImageCache(self._make_cache_path())

		central = QWidget()
		layout = QVBoxLayout()

		# Start background scan
		self.scanner_thread = SpineScannerThread(self.config, self.default_spine_exe, self)
		self.scanner_thread.versions_found.connect(self.on_spine_versions_found)
		self.scanner_thread.start()

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
		browse_btn = QPushButton("1. Browse...")
		browse_btn.clicked.connect(self.browse_folder)
		folder_layout.addWidget(folder_label)
		folder_layout.addWidget(self.folder_display)
		folder_layout.addWidget(browse_btn)

		# Output folder selection
		output_layout = QHBoxLayout()
		output_label = QLabel("Output folder:")
		self.output_display = QLineEdit(self.config.get("output_folder", ""))
		output_browse = QPushButton("2. Browse...")
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
		settings_btn.clicked.connect(self.settings_dialog.show)
		combined_folders_layout.addWidget(settings_btn)

		layout.addLayout(combined_folders_layout)
		# layout.addLayout(threshold_layout) # Moved to settings
		self.list_widget = QListWidget()
		

		# Action buttons for the file list
		actions_layout = QHBoxLayout()
		
		self.select_all_cb = QCheckBox("Select all")
		self.select_all_cb.stateChanged.connect(self.toggle_select_all)
		
		self.process_btn = QPushButton("3. Process selected")
		self.process_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
		self.process_btn.clicked.connect(self.process_selected)

		self.stop_btn = QPushButton("Stop")
		self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
		self.stop_btn.clicked.connect(self.stop_process)
		self.stop_btn.setEnabled(False)
		
		# Optional: open exported .spine in Spine automatically
		self.open_after_checkbox = QCheckBox("Open .spine after export")
		self.open_after_checkbox.setChecked(bool(self.config.get("open_after_export", False)))
		self.open_after_checkbox.stateChanged.connect(lambda v: self._save_open_after_config(v))
		
		actions_layout.addWidget(self.select_all_cb)
		actions_layout.addWidget(self.process_btn)
		actions_layout.addWidget(self.stop_btn)
		actions_layout.addWidget(self.open_after_checkbox)

		layout.addLayout(actions_layout)

		# Progress bar
		self.progress_bar = QProgressBar()
		self.progress_bar.setTextVisible(True)
		self.progress_bar.setRange(0, 100)
		self.progress_bar.setValue(0)
		# Make it "big and prominent"
		self.progress_bar.setStyleSheet("""
			QProgressBar { height: 30px; font-size: 14px; font-weight: bold; text-align: center; }
			QProgressBar::chunk { background-color: #4CAF50; }
		""")
		layout.addWidget(self.progress_bar)

		layout.addWidget(QLabel("Spine files in folder:"))
		layout.addWidget(self.list_widget)

		# Info / detailed log panel
		layout.addWidget(QLabel("Info log:"))
		self.info_panel = QTextEdit()
		self.info_panel.setReadOnly(True)
		self.info_panel.setMinimumHeight(160)
		self.info_panel.setStyleSheet("background-color: #1e1e1e; color: white;")
		layout.addWidget(self.info_panel)

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

		# restore json version selection
		jv = self.config.get('spine_json_version')
		if jv:
			self.json_version_combo.addItem(jv)
			self.json_version_combo.setCurrentText(jv)
		# save when edited
		self.json_version_combo.currentTextChanged.connect(lambda v: self._save_json_version(v))

	def diagnose_file(self):
		start = self.output_display.text() or os.path.expanduser("~")
		path, _ = QFileDialog.getOpenFileName(self, "Select .spine file to diagnose", start, "Spine files (*.spine)")
		if path:
			self.info_panel.clear()
			# Use internal validator class instead of external script
			SpinePackageValidator.diagnose(path, log_callback=self.info_panel.append)

	def on_spine_versions_found(self, results):
		"""Callback when background scan finishes."""
		self.spine_combo.clear()
		for disp, exe in results:
			self.spine_combo.addItem(disp, exe)
			
		# restore selected spine exe if in config
		sel = self.config.get('spine_exe_selected')
		if sel:
			# try to select existing item
			for i in range(self.spine_combo.count()):
				if self.spine_combo.itemData(i) == sel:
					self.spine_combo.setCurrentIndex(i)
					break
		
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

	def _save_keep_temp_config(self, v):
		try:
			self.config["keep_temp_files"] = bool(v)
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
		path, _ = QFileDialog.getOpenFileName(self, "Select Spine executable", start, "Executables (*.exe)")
		if path:
			# add to combo if not present
			if path not in [self.spine_combo.itemData(i) for i in range(self.spine_combo.count())]:
				label = os.path.basename(os.path.dirname(path)) or os.path.basename(path)
				self.spine_combo.addItem(f"{label} - {os.path.basename(path)}", path)
				self.spine_combo.setCurrentIndex(self.spine_combo.count()-1)
			# attempt to detect the spine version from the selected executable and prefer it in the JSON-version combo
			try:
				# Use the thread's method (we can instantiate a temporary thread object or just copy the method)
				# Or just use the scanner thread instance we have
				ver = self.scanner_thread.detect_spine_version(path)
				if ver:
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
			from PySide6.QtWidgets import QListWidgetItem

			for name in files:
				if name.lower().endswith(".spine"):
					item = QListWidgetItem(name)
					item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
					item.setCheckState(Qt.Unchecked)
					self.list_widget.addItem(item)
		except Exception as e:
			QMessageBox.warning(self, "Read Error", f"Could not read folder: {e}")

	def toggle_select_all(self, state):
		# Qt.Checked is 2, Qt.Unchecked is 0
		check_state = Qt.Checked if state == 2 else Qt.Unchecked
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			item.setCheckState(check_state)

	def stop_process(self):
		self.stop_requested = True
		self.info_panel.append("<b><font color='red'>Stopping process...</font></b>")
		self.stop_btn.setEnabled(False)

	def _process_single_skeleton(self, found_json, found_info, result_dir, folder, input_path, file_scanner, base_output_root, spine_exe, base_progress, name, errors, results, all_file_stats, jpeg_forced_png_warnings, is_first=True, is_last=True):
		# Collect image file paths from json, atlas/info and by scanning the export folder
		image_paths = set()
		try:
			# parse json for image references (use structured parsing when possible)
			if found_json and os.path.exists(found_json):
				try:
					with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
						obj = json.load(fh)
					def collect_from_json(x):
						if isinstance(x, str):
							if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', x, flags=re.IGNORECASE):
								image_paths.add(x)
						elif isinstance(x, dict):
							for k, v in x.items():
								if isinstance(k, str) and re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
									image_paths.add(k)
								collect_from_json(v)
						elif isinstance(x, list):
							for v in x:
								collect_from_json(v)
					collect_from_json(obj)
					# also collect keys (attachment names) which may be basenames without extension
					# ignore common non-image keys (e.g. 'skins', 'skeleton', 'slots') to reduce noise
					IGNORE_KEYS = {
						'skins', 'skeleton', 'slots', 'bones', 'animations', 'attachment', 'attachments',
						'audio', 'path', 'name', 'width', 'height', 'x', 'y', 'scale', 'scalex', 'scaley',
						'translate', 'translatex', 'translatey', 'rotate', 'rotation', 'rgba', 'color',
						'blend', 'start', 'time', 'delay', 'sequence', 'mode', 'count', 'length', 'hash',
						'icon', 'logo', 'parent', 'value', 'spine'
					}
					def collect_keys(x):
						if isinstance(x, dict):
							for k, v in x.items():
								if isinstance(k, str):
									kl = k.lower()
									# add explicit image filenames
									if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
										image_paths.add(k)
									# add bare keys only if they're not in the ignore list
									elif kl not in IGNORE_KEYS:
										image_paths.add(k)
									
									# Also collect values from 'path' and 'name' properties as they often point to images
									if kl in ['path', 'name'] and isinstance(v, str):
										image_paths.add(v)

								collect_keys(v)
						elif isinstance(x, list):
							for v in x:
								collect_keys(v)
					collect_keys(obj)
				except Exception:
					# fallback to raw text regex if JSON parsing fails
					with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
						data = fh.read()
						for m in re.findall(r'([\w\-/\\]+\.(?:png|jpg|jpeg|webp|bmp|tga))', data, flags=re.IGNORECASE):
							image_paths.add(m)

			# parse any atlas files placed in the export folder
			for f in os.listdir(result_dir):
				if f.lower().endswith('.atlas'):
					atlas_path = os.path.join(result_dir, f)
					with open(atlas_path, 'r', encoding='utf-8', errors='ignore') as ah:
						for line in ah:
							line = line.strip()
							if not line:
								continue
							# atlas files commonly list image names (one per section)
							if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', line, flags=re.IGNORECASE):
								image_paths.add(line)

			# parse any info/text files (found_info) for image names
			if found_info and os.path.exists(found_info):
				with open(found_info, 'r', encoding='utf-8', errors='ignore') as fh:
					for line in fh:
						line = line.strip()
						if not line:
							continue
						if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', line, flags=re.IGNORECASE):
							image_paths.add(line)

			# also include any image files physically present in the export folder (recursive)
			for root, dirs, files in os.walk(result_dir):
				for fn in files:
					if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', fn, flags=re.IGNORECASE):
						# store relative path to result_dir so later resolution can join correctly
						rel = os.path.relpath(os.path.join(root, fn), result_dir)
						image_paths.add(rel)
		except Exception as e:
			errors.append(f"{name}: error parsing exports: {e}")

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
		for ip in image_paths:
			# absolute path check (must be a file)
			if os.path.isabs(ip) and os.path.isfile(ip):
				resolved.add(ip)
				continue
			# try direct joins first
			found = None
			for d in search_dirs:
				candidate = os.path.join(d, ip)
				# only accept actual files (not directories)
				if os.path.isfile(candidate):
					found = candidate
					break
			if found:
				resolved.add(found)
				continue
			# fallback: search for matching basename in the search_dirs recursively
			base = os.path.basename(ip)
			for d in search_dirs:
				if not d or not os.path.exists(d):
					continue
				for root, dirs, files in os.walk(d):
					for f in files:
						fname_noext = os.path.splitext(f)[0]
						# Allow prefix match to catch sequences (e.g. 'run' matches 'run_00')
						if f.lower() == base.lower() or fname_noext.lower() == base.lower() or fname_noext.lower().startswith(base.lower()):
							resolved.add(os.path.join(root, f))
							# Do NOT break, so we collect all frames of a sequence
					else:
						continue
					# Do NOT break outer loop either, keep searching all subfolders

		# convert to list for further processing and log resolved files
		resolved = list(resolved)
		try:
			if resolved:
				self.info_panel.append("Resolved image files: " + ", ".join(resolved))
		except Exception:
			pass
		
		# Progress update: Resolution done
		self.progress_bar.setValue(base_progress + 20)
		QApplication.processEvents()

		opaque_results = []
		total_resolved = len(resolved)
		for idx, img_path in enumerate(resolved):
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
				else:
					# use configured alpha cutoff (count pixels with alpha >= cutoff as opaque)
					alpha_cutoff = int(self.config.get("alpha_cutoff", 250))
					opaque_count = sum(1 for v in data if v >= alpha_cutoff)
					ratio = opaque_count / total
				# threshold from slider (percentage)
				threshold = float(self.config.get("opacity_threshold", self.opacity_slider.value())) / 100.0
				fully_opaque = (ratio >= threshold)
				# log percentage for visibility
				try:
					self.info_panel.append(f"Opacity for {img_path}: {ratio*100:.2f}% ({opaque_count}/{total})")
				except Exception:
					pass
				opaque_results.append((img_path, fully_opaque))
			except Exception as e:
				errors.append(f"{name}: image analyze failed {img_path}: {e}")

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
			errors.append(f"{name}: could not write result file: {e}")
			self.info_panel.append(f"Could not write result file: {e}")

		# Progress update: Opacity analysis done
		self.progress_bar.setValue(base_progress + 50)
		QApplication.processEvents()

		# --- Sorting algorithm: copy attachments into jpeg/png and rebuild JSON ---
		try:
			if found_json and os.path.exists(found_json):
				# build opaque map (basename or full path -> opaque)
				opaque_map = {}
				for p, ok in opaque_results:
					opaque_map[os.path.normpath(p)] = bool(ok)
					opaque_map[os.path.basename(p)] = bool(ok)

				# load json
				with open(found_json, 'r', encoding='utf-8', errors='ignore') as fh:
					j = json.load(fh)

				# skeleton name
				skeleton_name = os.path.splitext(os.path.basename(found_json))[0]

				# build slot blend map
				slot_blend = {}
				for s in j.get('slots', []):
					slot_blend[s.get('name')] = s.get('blend', 'normal')

				# prepare final output image folders under the chosen output root
				# structure: <output_root>/images/<skeleton>/{jpeg,png}
				output_root = base_output_root
				images_root = os.path.join(output_root, 'images', skeleton_name)
				jpeg_dir = os.path.join(images_root, 'jpeg')
				png_dir = os.path.join(images_root, 'png')
				os.makedirs(jpeg_dir, exist_ok=True)
				os.makedirs(png_dir, exist_ok=True)

				# helper: find source file for an image reference
				def find_source_image(ref_name):
					# Debug: log the reference being searched
					try:
						self.info_panel.append(f"find_source_image: looking for ref '{ref_name}'")
					except Exception:
						pass
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
					
					# prefer an exact match first
					if exact_matches:
						# return all exact matches (could be multiple in different folders)
						# Debug: log exact match
						try:
							self.info_panel.append(f"Exact match found for '{ref_name}': {exact_matches[0]}")
						except Exception:
							pass
						return exact_matches

					# then prefer numeric sequences if found
					if seq_matches:
						seq_matches.sort(key=lambda x: x[0])
						try:
							self.info_panel.append(f"Sequence detected for '{ref_name}': {len(seq_matches)} frames")
						except Exception:
							pass
						# return ordered list of candidates
						return [p for _, p in seq_matches]
					
					# then prefix matches: sort intelligently (numeric suffixes first)
					if prefix_matches:
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
				# helper to process a single skin dict (slot -> attachments)
				def process_skin_dict(skin_dict):
					if not isinstance(skin_dict, dict):
						return skin_dict
					
					# Debug: track first attachment processed
					first_attachment_debug = False
					
					for slot_name, attachments in list(skin_dict.items()):
						if not isinstance(attachments, dict):
							self.info_panel.append(f"Skipping slot {slot_name}: unexpected attachments type {type(attachments)}")
							continue
						for attach_name, attach_val in list(attachments.items()):
							# Debug: log first attachment details
							if not first_attachment_debug:
								try:
									self.info_panel.append(f"Debug Attachment '{attach_name}': {json.dumps(attach_val)}")
									first_attachment_debug = True
								except Exception:
									pass

							# determine referenced image name
							if isinstance(attach_val, dict):
								# prefer explicit path in attachment value; otherwise use the attachment name
								ref = attach_val.get('path') or attach_name
							else:
								# attach_name may include folder-like segments
								ref = attach_name
							
							# find real source file
							src = find_source_image(ref)
							
							# determine blend(s) for this slot
							blend = slot_blend.get(slot_name, 'normal')
							# determine opaque status
							is_opaque = False
							if src:
								# src may be a single path or a list of matches; consider all matches opaque to be opaque
								matches_check = src if isinstance(src, (list, tuple)) else [src]
								vals = []
								for m in matches_check:
									vals.append(bool(opaque_map.get(os.path.normpath(m), opaque_map.get(os.path.basename(m), False))))
								# require all frames/matches to be opaque to treat as opaque
								is_opaque = all(vals) if vals else False
							# If attachment appears in slots, collect those slots and their blends
							slots_found = []
							for skin2 in ALL_SKIN_DICTS:
								for slot2, slot_val in skin2.items():
									try:
										if attach_name in slot_val:
											slots_found.append(slot2)
									except Exception:
										continue

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

							if slots_found and appears_only_in_non_normal:
								base_dest = jpeg_dir
								reason.append("only in non-normal slots")
							elif blend == 'normal' and (not slots_found or all(slot_blend.get(s, 'normal') == 'normal' for s in slots_found)) and is_opaque:
								base_dest = jpeg_dir
								reason.append("normal blend + opaque")
							else:
								base_dest = png_dir
								if not is_opaque: reason.append("transparent")
								if blend != 'normal': reason.append(f"blend={blend}")
								
								# Warning if it was JPEG but forced to PNG
								if is_jpeg_source:
									msg = f"<font color='red'>WARNING:</font> '{attach_name}' was in jpeg folder but forced to PNG due to: Transparent corners and/or edges while using normal mode . You may want to fix transparency and put it back to jpeg folder manualy or change blend mode !!!"
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
								if isinstance(matches, (list, tuple)) and len(matches) > 1:
									try:
										self.info_panel.append(f"Copying sequence of {len(matches)} frames for '{attach_name}' to {base_dest}")
									except Exception:
										pass
								
								# Detect if this is a sequence: multiple matches OR explicit sequence metadata
								is_sequence = False
								try:
									if isinstance(attach_val, dict) and 'sequence' in attach_val:
										is_sequence = True
									elif len(matches) > 1:
										# Only treat as sequence if filenames are different (i.e. frames), not just duplicates of the same file
										filenames = set(os.path.basename(m) for m in matches)
										if len(filenames) > 1:
											is_sequence = True
									elif str(attach_name).endswith('_'):
										is_sequence = True
								except Exception:
									pass
								
								# Extract nested folder structure from ATTACHMENT NAME (the source of truth)
								attach_name_str = str(attach_name).replace('\\', '/')
								nested_folders_str = ""
								base_name = os.path.basename(str(attach_name))
								
								# Remove any family markers (jpeg/png) and skeleton name from the path
								parts = attach_name_str.split('/')
								filtered_parts = []
								for part in parts[:-1]:  # Exclude the last part (basename)
									part_lower = part.lower()
									if part_lower not in ['jpeg', 'png', 'images', 'symbols', 'skeleton'] and part_lower != skeleton_name.lower():
										filtered_parts.append(part)
								
								if filtered_parts:
									nested_folders_str = '/'.join(filtered_parts)
								
								# Ensure sequence subfolder exists
								if is_sequence:
									seq_name = re.sub(r'[_\-]?\d+$', '', base_name)
									# Strip trailing underscore so we don't duplicate folder names like "name_" inside "name"
									seq_name = seq_name.rstrip('_')
									
									# If seq_name is empty (e.g. file was just "00.png"), fallback to base_name
									if not seq_name: seq_name = base_name
									
									if seq_name:
										if not nested_folders_str:
											nested_folders_str = seq_name
										elif not nested_folders_str.lower().endswith(seq_name.lower()):
											nested_folders_str = f"{nested_folders_str}/{seq_name}"

								first_rel = None
								copy_succeeded = False
								
								for idx, m in enumerate(matches):
									if self.stop_requested:
										raise Exception("Process stopped by user")
									QApplication.processEvents()
									
									# Build destination path with nested folder structure
									if nested_folders_str:
										nested_path = nested_folders_str.replace('/', os.path.sep)
										dst = os.path.join(base_dest, nested_path, os.path.basename(m))
									else:
										dst = os.path.join(base_dest, os.path.basename(m))
									
									# Create parent directories if needed
									try:
										os.makedirs(os.path.dirname(dst), exist_ok=True)
									except Exception:
										pass
									
									# Copy the file
									try:
										import shutil
										shutil.copy2(m, dst)
										copy_succeeded = True
										
										# Update stats
										if all_file_stats:
											stats = all_file_stats[-1]
											stats['total'] += 1
											if 'jpeg' in base_dest.lower():
												stats['jpeg'] += 1
											else:
												stats['png'] += 1
									except Exception as e:
										self.info_panel.append(f"Failed to copy {m} -> {dst}: {e}")
										continue
									
									# Build JSON path only once (on first successful copy)
									if first_rel is None:
										family = os.path.basename(base_dest)
										
										if is_sequence:
											# For sequences: use basename without digits and add trailing underscore
											base_no_digits = re.sub(r"\d+$", "", base_name)
											if base_no_digits and not base_no_digits.endswith('_'):
												base_no_digits = base_no_digits + '_'
											# Build JSON path with nested structure
											if nested_folders_str:
												first_rel = f"{skeleton_name}/{family}/{nested_folders_str}/{base_no_digits}".replace('\\', '/')
											else:
												first_rel = f"{skeleton_name}/{family}/{base_no_digits}".replace('\\', '/')
										else:
											# For static: use basename WITHOUT extension
											name_no_ext = os.path.splitext(os.path.basename(m))[0]
											if nested_folders_str:
												first_rel = f"{skeleton_name}/{family}/{nested_folders_str}/{name_no_ext}".replace('\\', '/')
											else:
												first_rel = f"{skeleton_name}/{family}/{name_no_ext}".replace('\\', '/')
										
										# Clean up any duplicate family tokens
										first_rel = first_rel.replace('/jpeg/jpeg/', '/jpeg/').replace('/png/png/', '/png/')
								
								# Update JSON with the path if ANY file was successfully copied
								if first_rel and copy_succeeded:
									if isinstance(attach_val, dict):
										attach_val['path'] = first_rel
									else:
										attachments[attach_name] = {'path': first_rel}
							else:
								# src is None: no files found, but check if this is a declared sequence OR a placeholder
								is_sequence = False
								try:
									if isinstance(attach_val, dict) and 'sequence' in attach_val:
										is_sequence = True
									elif str(attach_name).endswith('_'):
										is_sequence = True
								except Exception:
									pass
								
								# Also treat as placeholder if the name contains 'placeholder'
								is_placeholder = 'placeholder' in os.path.basename(str(attach_name)).lower()

								if is_sequence or is_placeholder:
									# For declared sequences or placeholders with no files found, create placeholder using attachment name structure
									family = os.path.basename(base_dest)
									
									# Extract nested folders from ATTACHMENT NAME
									attach_name_str = str(attach_name).replace('\\', '/')
									nested_folders_str = ""
									base_name = os.path.basename(str(attach_name))
									
									# Remove any family markers (jpeg/png) and skeleton name from the path
									parts = attach_name_str.split('/')
									filtered_parts = []
									for part in parts[:-1]:  # Exclude the last part (basename)
										part_lower = part.lower()
										if part_lower not in ['jpeg', 'png', 'images', 'symbols', 'skeleton'] and part_lower != skeleton_name.lower():
											filtered_parts.append(part)
									
									if filtered_parts:
										nested_folders_str = '/'.join(filtered_parts)
									
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
										first_rel = f"{skeleton_name}/{family}/{nested_folders_str}/{base_no_digits}".replace('\\', '/')
									else:
										first_rel = f"{skeleton_name}/{family}/{base_no_digits}".replace('\\', '/')
									first_rel = first_rel.replace('/jpeg/jpeg/', '/jpeg/').replace('/png/png/', '/png/')
									
									# Create placeholder file ONLY if no real files were found
									try:
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
									
									# Update JSON
									if isinstance(attach_val, dict):
										attach_val['path'] = first_rel
									else:
										attachments[attach_name] = {'path': first_rel}
					return skin_dict

				if isinstance(skins, dict):
					for skin_name, skin in list(skins.items()):
						if not isinstance(skin, dict):
							self.info_panel.append(f"Skipping skin {skin_name}: unexpected type {type(skin)}")
							continue
						skins[skin_name] = process_skin_dict(skin)
				elif isinstance(skins, list):
					# preserve list shape: process each element which may be a dict mapping skinName->skinDict or a skinDict directly
					new_list = []
					for item in skins:
						if isinstance(item, dict):
							# detect if item is {skinName: {..}} or a skin dict (slot->attachments)
							# if any value is a dict, treat as mapping skinName->skinDict
							if any(isinstance(v, dict) for v in item.values()):
								new_item = {}
								for k, v in item.items():
									if isinstance(v, dict):
										new_item[k] = process_skin_dict(v)
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

				# normalize skeleton images path (remove leading './') so Spine can resolve images inside archive
				skel = j.get('skeleton')
				if isinstance(skel, dict):
					# ensure skeleton.images points to the images folder relative to the JSON
					# Use 'images/' instead of './images/' to be safer with different Spine versions
					# Try './images/' again as it is standard for relative paths
					skel['images'] = './images/'
					self.info_panel.append(f"Set skeleton.images to: {skel['images']}")
				# save modified json into the output root
				new_json_path = os.path.join(output_root, os.path.splitext(os.path.basename(found_json))[0] + '.json')
				
				# Debug: Verify bones before writing
				final_bones = len(j.get('bones', []))
				self.info_panel.append(f"Final JSON check: {final_bones} bones. Writing to {new_json_path}")
				
				with open(new_json_path, 'w', encoding='utf-8') as nj:
					json.dump(j, nj, indent=2)
				self.info_panel.append(f"Wrote sorted json: {new_json_path}")

				# Progress update: JSON written
				self.progress_bar.setValue(base_progress + 90)
				QApplication.processEvents()

				# create a .spine package using Spine CLI (binary format)
				spine_pkg = os.path.join(output_root, os.path.splitext(name)[0] + '.spine')
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

						cmd = [spine_exe, '-i', abs_json, '-o', abs_pkg, '--import']
						self.info_panel.append(f"Running: {' '.join(cmd)}")
						
						# Run synchronously
						proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
						
						if proc.returncode == 0:
							self.info_panel.append(f"Successfully created binary .spine file: {spine_pkg}")
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
				if is_last and not self.keep_temp_cb.isChecked():
					try:
						# Remove the temporary export folder (spine_temp_...)
						if result_dir and os.path.isdir(result_dir) and 'spine_temp_' in os.path.basename(result_dir):
							import shutil
							shutil.rmtree(result_dir, ignore_errors=True)
							self.info_panel.append(f"Cleaned up temp folder: {result_dir}")
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
								subprocess.Popen([spine_exe, spine_pkg])
							else:
								if not spine_exe:
									self.info_panel.append("Spine executable not configured; cannot open.")
								elif not os.path.exists(spine_pkg):
									self.info_panel.append("Spine package not found; cannot open.")
					except Exception as e:
						self.info_panel.append(f"Could not open in Spine: {e}")
		except Exception as e:
			self.info_panel.append(f"Sorting step failed: {e}")






	def process_selected(self):
		self.stop_requested = False
		# use selected Spine executable from dropdown (fall back to config/default)
		spine_exe = None
		try:
			spine_exe = self.spine_combo.currentData()
		except Exception:
			pass
		if not spine_exe:
			spine_exe = self.config.get('spine_exe_selected') or self.config.get("spine_exe", self.default_spine_exe)
		if not os.path.isfile(spine_exe):
			QMessageBox.warning(self, "Spine not found", f"Spine executable not found:\n{spine_exe}")
			return

		folder = self.folder_display.text()
		if not folder or not os.path.isdir(folder):
			QMessageBox.information(self, "No folder", "Please select a folder containing .spine files first.")
			return

		to_process = []
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			if item.checkState() == Qt.Checked:
				to_process.append(item.text())

		if not to_process:
			QMessageBox.information(self, "No files selected", "Please check one or more .spine files to process.")
			return
		
		# Update UI for processing state
		self.process_btn.setEnabled(False)
		self.stop_btn.setEnabled(True)
		self.progress_bar.setRange(0, len(to_process) * 100)
		self.progress_bar.setValue(0)
		
		# List to collect warnings about JPEGs forced to PNG
		jpeg_forced_png_warnings = []
		# List to collect statistics for each file
		all_file_stats = []
			
		file_scanner = FileScanner()

		# clear and start info log
		self.info_panel.clear()
		self.info_panel.append(f"Starting processing of {len(to_process)} file(s)")
		# log current threshold settings
		try:
			cur_thresh = int(self.config.get("opacity_threshold", self.opacity_slider.value()))
			cur_alpha = int(self.config.get("alpha_cutoff", self.alpha_cutoff_spin.value()))
			self.info_panel.append(f"Using opacity threshold: {cur_thresh}%  alpha cutoff: {cur_alpha}")
		except Exception:
			pass

		if Image is None:
			QMessageBox.warning(self, "Missing dependency", "Pillow is required to analyze images. Install with: pip install Pillow")
			self.process_btn.setEnabled(True)
			self.stop_btn.setEnabled(False)
			return

		timestamp = int(time.time())
		results = []
		errors = []
		
		for i, name in enumerate(to_process):
			if self.stop_requested:
				self.info_panel.append("Process stopped by user.")
				break

			base_progress = i * 100
			self.progress_bar.setValue(base_progress)
			QApplication.processEvents()
			
			# Initialize stats for this file
			file_stats = {'name': name, 'jpeg': 0, 'png': 0, 'total': 0}
			all_file_stats.append(file_stats)
			
			input_path = os.path.join(folder, name)
			
			# Ensure input is the checked .spine file
			if not input_path.lower().endswith('.spine'):
				errors.append(f"Skipped (not a .spine file): {input_path}")
				self.info_panel.append(f"Skipped non-.spine input: {input_path}")
				continue
			if not os.path.isfile(input_path):
				errors.append(f"Missing: {input_path}")
				continue

			# Determine base output root and create a timestamped temporary export folder
			base_output_root = self.output_display.text() or os.path.expanduser("~")
			os.makedirs(base_output_root, exist_ok=True)
			
			# Create temp export dir
			result_dir = os.path.join(base_output_root, f"spine_temp_{timestamp}_{i}")
			os.makedirs(result_dir, exist_ok=True)

			self.info_panel.append(f"\nProcessing: {name}")
			self.info_panel.append(f"Exporting JSON to: {result_dir}")

			# Run Spine export
			export_settings = os.path.abspath("default_export.json")
			if not os.path.exists(export_settings):
				try:
					with open(export_settings, 'w') as f:
						f.write('{"class": "export-json", "name": "JSON", "extension": ".json", "format": "JSON", "prettyPrint": false, "nonessential": true, "cleanUp": false, "packAtlas": null, "packSource": "attachments", "warnings": true}')
				except:
					pass

			cmd = [
				spine_exe, 
				'-i', input_path, 
				'-o', result_dir, 
				'-e', export_settings if os.path.exists(export_settings) else 'json'
			]
			
			try:
				self.info_panel.append(f"Running export command: {' '.join(cmd)}")
				# Use subprocess.run for reliability (avoids buffer deadlocks)
				proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
				
				if proc.returncode != 0:
					self.info_panel.append(f"Spine export failed: {proc.stderr}")
					errors.append(f"{name}: export failed")
					continue
			except Exception as e:
				errors.append(f"{name}: {e}")
				self.info_panel.append(f"Export error: {e}")
				continue

			# Find all exported JSONs
			found_jsons = []
			found_info = None
			for f in os.listdir(result_dir):
				if f.lower().endswith('.json'):
					found_jsons.append(os.path.join(result_dir, f))
				elif f.lower().endswith('.txt') and 'opaque' not in f:
					found_info = os.path.join(result_dir, f)
			
			if not found_jsons:
				errors.append(f"{name}: no JSON exported")
				self.info_panel.append("No JSON found in export folder.")
				continue

			# Sort JSONs to ensure deterministic order
			found_jsons.sort()
			
			self.info_panel.append(f"Found {len(found_jsons)} skeleton(s) to process.")

			# Process each skeleton
			for idx, f_json in enumerate(found_jsons):
				is_first = (idx == 0)
				is_last = (idx == len(found_jsons) - 1)
				
				self.info_panel.append(f"Processing skeleton {idx+1}/{len(found_jsons)}: {os.path.basename(f_json)}")
				
				self._process_single_skeleton(
					f_json, found_info, result_dir, folder, input_path, file_scanner,
					base_output_root, spine_exe, base_progress, name, errors, results, 
					all_file_stats, jpeg_forced_png_warnings,
					is_first=is_first, is_last=is_last
				)

		# Cleanup and Finish
		self.progress_bar.setValue(len(to_process) * 100)
		self.process_btn.setEnabled(True)
		self.stop_btn.setEnabled(False)
		
		# Display statistics
		self.info_panel.append("\n<font color='lightgreen'>--- Processing Statistics ---</font>")
		for stats in all_file_stats:
			if stats['total'] > 0:
				self.info_panel.append(f"<font color='lightgreen'>File: {stats['name']}</font>")
				self.info_panel.append(f"<font color='lightgreen'>  Total images copied: {stats['total']}</font>")
				self.info_panel.append(f"<font color='lightgreen'>  JPEG images: {stats['jpeg']}</font>")
				self.info_panel.append(f"<font color='lightgreen'>  PNG images: {stats['png']}</font>")
		
		if errors:
			QMessageBox.warning(self, "Completed with errors", f"Processed {len(to_process)} files.\n{len(errors)} errors occurred.\nSee info log for details.")
		else:
			QMessageBox.information(self, "Completed", f"Successfully processed {len(to_process)} files.")

def main():
	print("Starting application...")
	try:
		app = QApplication(sys.argv)
		w = MainWindow()
		w.show()
		sys.exit(app.exec())
	except Exception as e:
		print(f"CRITICAL ERROR: {e}")
		import traceback
		traceback.print_exc()

if __name__ == "__main__":
	main()
