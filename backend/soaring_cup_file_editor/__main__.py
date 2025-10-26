"""Main entry point for Soaring CUP File Editor."""

import tkinter as tk
from soaring_cup_file_editor.gui import MainWindow


def main():
    """Launch the Soaring CUP File Editor application."""
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
