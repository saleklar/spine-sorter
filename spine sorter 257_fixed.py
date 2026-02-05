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
# Default Spine JSON versions to populate the JSON-version combo
DEFAULT_VERSIONS = ["4.2.43", "4.3", "4.2", "4.1", "4.0", "3.8"]
try:
	from PIL import Image
except Exception:
	Image = None

# Import PySide6 with a friendly error if it's not installed
try:
	from PySide6.QtCore import QStandardPaths, Qt
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
	)
except ModuleNotFoundError:
	print("PySide6 is not installed. Install with: pip install PySide6")
	sys.exit(1)


class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Spine Sorter")

		# Configuration
		self.default_spine_exe = r"C:\Program Files\Spine\Spine.exe"
		self.config = {}
		self.config_path = self._make_config_path()
		self._load_config()

		central = QWidget()
		layout = QVBoxLayout()

		# Spine exe (hardcoded display)
		exe_layout = QHBoxLayout()
		exe_label = QLabel("Spine EXE:")
		self.exe_display = QLineEdit(self.config.get("spine_exe", self.default_spine_exe))
		self.exe_display.setReadOnly(True)
		exe_layout.addWidget(exe_label)
		exe_layout.addWidget(self.exe_display)

		# CLI template edit (user-editable command template)

		layout.addLayout(exe_layout)

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
		layout.addLayout(version_layout)

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
		layout.addLayout(verjson_layout)


		# Folder selection for Spine files
		folder_layout = QHBoxLayout()
		folder_label = QLabel("Spine files folder:")
		self.folder_display = QLineEdit(self.config.get("spine_folder", ""))
		browse_btn = QPushButton("Browse...")
		browse_btn.clicked.connect(self.browse_folder)
		folder_layout.addWidget(folder_label)
		folder_layout.addWidget(self.folder_display)
		folder_layout.addWidget(browse_btn)

		# Output folder selection
		output_layout = QHBoxLayout()
		output_label = QLabel("Output folder:")
		self.output_display = QLineEdit(self.config.get("output_folder", ""))
		output_browse = QPushButton("Browse...")
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
		# default from config or 98
		init_thresh = int(self.config.get("opacity_threshold", 98))
		self.opacity_slider.setValue(init_thresh)
		self.opacity_spin = QSpinBox()
		self.opacity_spin.setRange(0, 100)
		self.opacity_spin.setValue(init_thresh)
		# alpha cutoff (0-255)
		alpha_label = QLabel("Alpha cutoff:")
		self.alpha_cutoff_spin = QSpinBox()
		self.alpha_cutoff_spin.setRange(0, 255)
		self.alpha_cutoff_spin.setValue(int(self.config.get("alpha_cutoff", 250)))

		# keep slider and spinbox in sync
		self.opacity_slider.valueChanged.connect(lambda v: self.opacity_spin.setValue(v))
		self.opacity_spin.valueChanged.connect(lambda v: self.opacity_slider.setValue(v))

		# save config when changed
		self.opacity_slider.valueChanged.connect(lambda v: self._save_opacity_config(v))
		self.alpha_cutoff_spin.valueChanged.connect(lambda v: self._save_alpha_config(v))

		threshold_layout.addWidget(threshold_label)
		threshold_layout.addWidget(self.opacity_slider)
		threshold_layout.addWidget(self.opacity_spin)
		threshold_layout.addWidget(alpha_label)
		threshold_layout.addWidget(self.alpha_cutoff_spin)

		# File list panel (folder -> output -> threshold)
		layout.addLayout(folder_layout)
		layout.addLayout(output_layout)
		layout.addLayout(threshold_layout)
		self.list_widget = QListWidget()
		

		# Action buttons for the file list
		actions_layout = QHBoxLayout()
		select_all_btn = QPushButton("Select all")
		select_all_btn.clicked.connect(self.select_all)
		deselect_all_btn = QPushButton("Deselect all")
		deselect_all_btn.clicked.connect(self.deselect_all)
		process_btn = QPushButton("Process selected")
		process_btn.clicked.connect(self.process_selected)
		# Optional: open exported .spine in Spine automatically
		self.open_after_checkbox = QCheckBox("Open .spine after export")
		self.open_after_checkbox.setChecked(bool(self.config.get("open_after_export", False)))
		self.open_after_checkbox.stateChanged.connect(lambda v: self._save_open_after_config(v))
		actions_layout.addWidget(select_all_btn)
		actions_layout.addWidget(deselect_all_btn)
		actions_layout.addWidget(process_btn)
		actions_layout.addWidget(self.open_after_checkbox)

		layout.addLayout(actions_layout)
		layout.addWidget(QLabel("Spine files in folder:"))
		layout.addWidget(self.list_widget)

		# Info / detailed log panel
		layout.addWidget(QLabel("Info log:"))
		self.info_panel = QTextEdit()
		self.info_panel.setReadOnly(True)
		self.info_panel.setMinimumHeight(160)
		layout.addWidget(self.info_panel)

		central.setLayout(layout)
		self.setCentralWidget(central)

		# Populate initial file list
		if self.folder_display.text():
			self.refresh_file_list()

		# populate spine versions dropdown
		self.scan_spine_versions()
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

	# export settings UI removed — using default export settings (no export JSON)

	def _make_config_path(self):
		loc = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
		if not loc:
			loc = os.path.join(os.path.expanduser("~"), ".pyside_spine_app")
		os.makedirs(loc, exist_ok=True)
		return os.path.join(loc, "config.json")

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
				ver = self.detect_spine_version(path)
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


	def detect_spine_version(self, spine_exe, timeout=3.0):
		"""Try to run the Spine executable to determine its version string.
		Returns a short version like '4.2.43' or None on failure."""
		exe = str(spine_exe)
		candidates = [[exe, '--version'], [exe, '-v'], [exe, 'version']]
		ver_re = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
		for cmd in candidates:
			try:
				p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
				out = (p.stdout or "") + "\n" + (p.stderr or "")
				m = ver_re.search(out)
				if m:
					return m.group(1)
			except Exception:
				continue
		return None

	def scan_spine_versions(self):
		"""Scan common Program Files locations for Spine installations and populate the combo."""
		self.spine_combo.clear()
		candidates = []
		# include configured exe dir first
		cfg = self.config.get('spine_exe', self.default_spine_exe)
		cfg_dir = os.path.dirname(cfg)
		roots = [cfg_dir, r"C:\Program Files", r"C:\Program Files (x86)"]
		seen = set()
		for root in roots:
			if not root or not os.path.isdir(root):
				continue
			for name in os.listdir(root):
				# look for folders with 'spine' in the name
				if 'spine' in name.lower():
					exe = os.path.join(root, name, 'Spine.exe')
					if os.path.isfile(exe) and exe not in seen:
						candidates.append(exe); seen.add(exe)
		# also check the root dir for a direct Spine.exe
		for root in roots:
			exe = os.path.join(root, 'Spine.exe')
			if os.path.isfile(exe) and exe not in seen:
				candidates.append(exe); seen.add(exe)

		# populate combo
		for exe in candidates:
			label = os.path.basename(os.path.dirname(exe)) or os.path.basename(exe)
			# try to detect the spine version for nicer labels
			try:
				ver = self.detect_spine_version(exe)
			except Exception:
				ver = None
			if ver:
				disp = f"{label} ({ver}) - {os.path.basename(exe)}"
			else:
				disp = f"{label} - {os.path.basename(exe)}"
			self.spine_combo.addItem(disp, exe)
		# ensure there's at least the default
		if not candidates:
			self.spine_combo.addItem(os.path.basename(cfg), cfg)
		# set tooltip with full path for each
		for i in range(self.spine_combo.count()):
			self.spine_combo.setItemData(i, self.spine_combo.itemData(i))

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

	def select_all(self):
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			item.setCheckState(Qt.Checked)

	def deselect_all(self):
		for i in range(self.list_widget.count()):
			item = self.list_widget.item(i)
			item.setCheckState(Qt.Unchecked)

	def process_selected(self):
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
			return

		timestamp = int(time.time())
		results = []
		errors = []
		for name in to_process:
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
			# Use a timestamped temp folder so both exported JSON and opaque results are colocated
			result_dir = os.path.join(base_output_root, f"spine_temp_{timestamp}")
			os.makedirs(result_dir, exist_ok=True)

			# Run fixed Spine CLI using selected spine file and the temporary result_dir as output
			ran = False
			try:
				last_stdout = last_stderr = ""
				self.info_panel.append(f"Processing: {name}")
				cmd = [spine_exe, '-i', input_path, '-o', result_dir, '-e', 'json']
				self.info_panel.append(f"Running fixed CLI: {' '.join(cmd)}")
				self.info_panel.append(f"Temporary export folder: {result_dir}")
				self.info_panel.append(f"Working directory: {os.getcwd()}")
				proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
				last_stdout, last_stderr = proc.stdout, proc.stderr
				self.info_panel.append(f"--- STDOUT ---\n{last_stdout}")
				self.info_panel.append(f"--- STDERR ---\n{last_stderr}")
				ran = True
			except Exception as e:
				errors.append(f"{name}: failed to run Spine CLI: {e}")
				self.info_panel.append(f"Failed to run CLI: {e}")

			# Wait a short while for exported files to appear in the temporary result_dir
			found_json = None
			found_info = None
			for _ in range(15):
				for f in os.listdir(result_dir):
					lf = f.lower()
					if lf.endswith('.json') and not found_json:
						found_json = os.path.join(result_dir, f)
					if (lf.endswith('.atlas') or lf.endswith('.txt') or 'info' in lf) and not found_info:
						found_info = os.path.join(result_dir, f)
				if found_json or found_info:
					break
				time.sleep(1)

			if not (found_json or found_info):
				# allow maybe Spine exported next to .spine file; look there
				base = os.path.splitext(input_path)[0]
				alt_json = base + '.json'
				alt_atlas = base + '.atlas'
				if os.path.exists(alt_json):
					found_json = alt_json
				if os.path.exists(alt_atlas):
					found_info = alt_atlas

			if not (found_json or found_info):
				msg = f"No exported json/info for {name} (expected in {result_dir})"
				msg += f"\nCommand: {' '.join(cmd)}"
				msg += f"\nWorking directory: {os.getcwd()}"
				if 'last_stdout' in locals() and last_stdout:
					msg += "\n--- stdout ---\n" + last_stdout
				if 'last_stderr' in locals() and last_stderr:
					msg += "\n--- stderr ---\n" + last_stderr
				errors.append(msg)
				self.info_panel.append(msg)
				# Also show in a popup for immediate visibility
				QMessageBox.warning(self, "Spine CLI output", msg)
				continue

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
							if f.lower() == base.lower() or fname_noext.lower() == base.lower():
								resolved.add(os.path.join(root, f))
								break
						else:
							continue
						break
			# convert to list for further processing and log resolved files
			resolved = list(resolved)
			try:
				if resolved:
					self.info_panel.append("Resolved image files: " + ", ".join(resolved))
			except Exception:
				pass

			opaque_results = []
			for img_path in resolved:
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
					# Prefer the skeleton name embedded in the exported JSON (internal_skeleton_name).
					# Fall back to the project/spine filename (`skeleton_name`) if the JSON name isn't available.
					final_skeleton_dir = internal_skeleton_name or skeleton_name
					images_root = os.path.join(output_root, 'images', final_skeleton_dir)
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
						# prefer numeric sequences if found
						if seq_matches:
							seq_matches.sort(key=lambda x: x[0])
							try:
								self.info_panel.append(f"Sequence detected for '{ref_name}': {len(seq_matches)} frames")
							except Exception:
								pass
							# return ordered list of candidates
							return [p for _, p in seq_matches]
						# then prefer an exact match
						if exact_matches:
							# return all exact matches (could be multiple in different folders)
							return exact_matches
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
						for slot_name, attachments in list(skin_dict.items()):
							if not isinstance(attachments, dict):
								self.info_panel.append(f"Skipping slot {slot_name}: unexpected attachments type {type(attachments)}")
								continue
							for attach_name, attach_val in list(attachments.items()):
								# determine referenced image name
								if isinstance(attach_val, dict):
									# prefer explicit path in attachment value; otherwise use the last path component
									ref = attach_val.get('path') or os.path.basename(attach_name)
								else:
									# attach_name may include folder-like segments (e.g. 'h1_particles/jpeg/h1_particles_')
									ref = os.path.basename(attach_name)
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
								dest_dir = None
								appears_only_in_non_normal = False
								if slots_found:
									appears_only_in_non_normal = all(slot_blend.get(s, 'normal') != 'normal' for s in slots_found)

								if slots_found and appears_only_in_non_normal:
									dest_dir = jpeg_dir
								elif blend == 'normal' and (not slots_found or all(slot_blend.get(s, 'normal') == 'normal' for s in slots_found)) and is_opaque:
									dest_dir = jpeg_dir
								else:
									dest_dir = png_dir
								# copy file(s) if found
								if src:
									matches = src if isinstance(src, (list, tuple)) else [src]
									if isinstance(matches, (list, tuple)) and len(matches) > 1:
										try:
											self.info_panel.append(f"Copying sequence of {len(matches)} frames for '{attach_name}' to {dest_dir}")
										except Exception:
											pass
									first_rel = None
									for m in matches:
										dst = os.path.join(dest_dir, os.path.basename(m))
										try:
											import shutil
											shutil.copy2(m, dst)
										except Exception as e:
											self.info_panel.append(f"Failed to copy {m} -> {dst}: {e}")
										if first_rel is None:
											# Build path for attachment JSON; detect and handle sequences
											family = os.path.basename(dest_dir)
											rep_fname = os.path.basename(matches[0]) if matches else os.path.basename(m)
											first_rel = f"{skeleton_name}/{family}/{rep_fname}".replace('\\', '/')
											# detect declared sequence
											is_sequence = False
											try:
												if isinstance(attach_val, dict) and 'sequence' in attach_val:
													is_sequence = True
												elif str(attach_name).endswith('_'):
													is_sequence = True
											except Exception:
												pass
											if is_sequence:
												# for declared sequences, use sequence basename in JSON
												bn = os.path.splitext(rep_fname)[0]
												base_no_digits = re.sub(r"\d+$", "", bn)
												if base_no_digits and not base_no_digits.endswith('_'):
													base_no_digits = base_no_digits + '_'
												first_rel = f"{skeleton_name}/{family}/{base_no_digits}".replace('\\', '/')
												# create placeholder file for the sequence basename
												try:
													ph_dst = os.path.join(dest_dir, base_no_digits)
													if not os.path.exists(ph_dst):
														with open(ph_dst, 'wb') as ph:
															pass
												except Exception:
													pass
											# clean up duplicate family tokens
											first_rel = first_rel.replace('/jpeg/jpeg/', '/jpeg/').replace('/png/png/', '/png/')
									# update JSON
									if first_rel:
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

					# normalize skeleton images path (remove leading './') so Spine can resolve images inside archive
					skel = j.get('skeleton')
					if isinstance(skel, dict):
						# ensure skeleton.images points to the images folder relative to the JSON
						skel['images'] = './images/'
					# save modified json into the output root
					new_json_path = os.path.join(output_root, os.path.splitext(os.path.basename(found_json))[0] + '_sorted.json')
					with open(new_json_path, 'w', encoding='utf-8') as nj:
						json.dump(j, nj, indent=2)
					self.info_panel.append(f"Wrote sorted json: {new_json_path}")

					# create a .spine package in the output folder root (JSON + images)
					try:
						import zipfile
						spine_pkg = os.path.join(output_root, os.path.splitext(name)[0] + '_sorted.spine')
						with zipfile.ZipFile(spine_pkg, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
							# add json using the package base name so Spine can find the project JSON inside the .spine
							pkg_json_name = os.path.splitext(os.path.basename(spine_pkg))[0] + '.json'
							zf.write(new_json_path, arcname=pkg_json_name.replace(os.path.sep, '/'))
							# add images under images/..
							for root, dirs, files in os.walk(images_root):
								for f in files:
									full = os.path.join(root, f)
									arc = os.path.relpath(full, output_root).replace(os.path.sep, '/')
									zf.write(full, arcname=arc)
						self.info_panel.append(f"Wrote new spine package: {spine_pkg}")
						# Validate package using included tool
						try:
							validator = os.path.join(os.path.dirname(__file__), 'tools', 'validate_spine_package.py')
							if os.path.exists(validator):
								self.info_panel.append(f"Validating package with: {validator}")
								proc = subprocess.run([sys.executable, validator, spine_pkg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
								if proc.stdout:
									self.info_panel.append(proc.stdout)
								if proc.stderr:
									self.info_panel.append(proc.stderr)
								if proc.returncode != 0:
									QMessageBox.warning(self, "Package validation", f"Validation reported issues. See Info log for details.")
							else:
								self.info_panel.append("Validator not found; skipping validation.")
						except Exception as e:
							self.info_panel.append(f"Validation step failed: {e}")

						# Optionally open the generated .spine in Spine
						try:
							if self.config.get("open_after_export"):
								# Use subprocess.Popen to avoid blocking the UI
								subprocess.Popen([spine_exe, spine_pkg])
								self.info_panel.append(f"Opened in Spine: {spine_pkg}")
						except Exception as e:
							self.info_panel.append(f"Could not open in Spine: {e}")
					except Exception as e:
						self.info_panel.append(f"Could not write spine package: {e}")
			except Exception as e:
				self.info_panel.append(f"Sorting step failed: {e}")

		msg = []
		if results:
			msg.append(f"Wrote {len(results)} opaque result file(s);")
			msg.extend(results[:10])
			for r in results:
				self.info_panel.append(f"Result: {r}")
		if errors:
			msg.append("Errors:")
			msg.extend(errors[:20])
			for e in errors:
				self.info_panel.append(f"Error: {e}")
		QMessageBox.information(self, "Process complete", "\n".join(msg))

		if errors:
			QMessageBox.warning(self, "Process errors", "Some files failed to start:\n" + "\n".join(errors))
		else:
			QMessageBox.information(self, "Processing", f"Started {len(to_process)} file(s) with Spine.")


def main():
	app = QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
