import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

class SpineSwitcher:
    def __init__(self, root):
        self.root = root
        self.root.title("Spine Version Launcher")
        self.root.geometry("400x250")

        # 1. Locate Spine Executable
        # Default Windows path. Change if you installed elsewhere.
        self.spine_exe = Path(r"C:\Program Files\Spine\Spine.com") 
        # Note: Use Spine.com for CLI; it handles arguments better than Spine.exe
        
        # 2. Locate Spine Data for Version Scanning
        self.spine_data = Path(os.environ['USERPROFILE']) / "Spine"
        self.updates_folder = self.spine_data / "updates"

        # UI
        tk.Label(root, text="Select Version to Launch:", font=("Arial", 10, "bold")).pack(pady=10)
        
        self.version_var = tk.StringVar()
        self.combo = ttk.Combobox(root, textvariable=self.version_var)
        self.combo.pack(pady=5, padx=20, fill='x')
        
        self.refresh_versions()
        
        tk.Button(root, text="LAUNCH SPINE", command=self.launch_spine, 
                  bg="#d35400", fg="white", font=("Arial", 10, "bold"), height=2).pack(pady=20)

    def refresh_versions(self):
        versions = []
        if self.updates_folder.exists():
            versions = [f.name for f in self.updates_folder.iterdir() if f.name[0].isdigit()]
            versions = sorted(versions, reverse=True)
        
        if versions:
            self.combo['values'] = versions
            self.combo.current(0)
        else:
            self.combo['values'] = ["4.1.24", "4.0.64", "3.8.99"] # Common fallbacks
            self.combo.current(0)

    def launch_spine(self):
        version = self.version_var.get().strip()
        if not version:
            return

        if not self.spine_exe.exists():
            messagebox.showerror("Error", f"Spine not found at {self.spine_exe}")
            return

        try:
            # Command: "C:\Program Files\Spine\Spine.com" --update <version>
            subprocess.Popen([str(self.spine_exe), "--update", version])
            self.root.destroy() # Close the switcher after launching
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpineSwitcher(root)
    root.mainloop()